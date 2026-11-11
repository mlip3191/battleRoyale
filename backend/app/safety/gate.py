"""The safety gate: code rules, then the classifier and the Wikidata name check, on the request
and on what intake read.

parse_matchup (intake) runs check_text_rules before any model call, classify_text alongside the
parse call, and check_parsed_sides on the model's reading. check_matchup runs every layer on a
Matchup that never went through intake (for the battle API, A05). Any block wins; the Wikidata
layer fails open and never overrides a rules or classifier block.
"""

import asyncio
import re
from collections.abc import Awaitable, Sequence
from typing import Protocol

from app.intake.rules import singular_word
from app.models.matchup import Matchup
from app.providers.base import ChatLLM
from app.providers.registry import get_provider
from app.safety.classify import classify_text
from app.safety.rules import check_text_rules, check_variant_rules
from app.safety.verdict import ALLOWED, SafetyVerdict
from app.safety.wikidata import WikidataCache, WikidataLookup, check_names, lookup_query

# Model-written words that only describe a fighter, so they never need a second classifier call.
PLAIN_DESCRIPTORS = frozenset(
    "a an the of like sized adult male female wild domestic common average typical standard "
    "regular full grown healthy large small big giant medium modern ancient young old".split()
)


class Side(Protocol):
    """One side as intake read it (ParsedFighter or FighterRequest)."""

    raw: str
    entity: str
    variant: str | None


# Lowercase singular words: "Gray Wolves" -> {"gray", "wolf"}.
def _words(text: str) -> set[str]:
    return {singular_word(w) for w in re.findall(r"[a-z]+", text.lower())}


# The size reference as a name, if any (the model may send a number there; code ignores it).
def _size_reference(fighter: Side) -> str:
    value = getattr(fighter, "size_reference", None)
    return value if isinstance(value, str) else ""


# One side as a short phrase: "grizzly bear (adult male)", "duck (sized like a horse)".
def _describe(fighter: Side) -> str:
    notes = [fighter.variant or "", ""]
    if _size_reference(fighter):
        notes[1] = f"sized like a {_size_reference(fighter)}"
    shown = [note for note in notes if note]
    return f"{fighter.entity} ({', '.join(shown)})" if shown else fighter.entity


# The sides as one short line for the classifier: "grizzly bear (adult male) vs gray wolf".
def describe_sides(fighters: Sequence[Side]) -> str:
    return " vs ".join(_describe(f) for f in fighters if f.entity)


# True if the model's entity, variant, or size reference uses words the user never typed
# ("a wolf" -> "godzilla"). Those words were never classified, so they need their own call.
def adds_new_words(fighters: Sequence[Side], text: str) -> bool:
    typed = _words(text)
    for fighter in fighters:
        written = _words(f"{fighter.entity} {fighter.variant or ''} {_size_reference(fighter)}")
        if written - typed - PLAIN_DESCRIPTORS:
            return True
    return False


# Code rules on every side's raw, entity, variant, and size reference; the first block wins.
def check_side_rules(fighters: Sequence[Side]) -> SafetyVerdict:
    for fighter in fighters:
        for verdict in (
            check_text_rules(fighter.raw),
            check_text_rules(fighter.entity),
            check_variant_rules(fighter.variant),
            check_text_rules(_size_reference(fighter)),
        ):
            if not verdict.allowed:
                return verdict
    return ALLOWED


# The entity as a name to look up. The model writes entities in lowercase, so its casing says
# nothing: when every entity word was typed by the user (singular or plural), the name is "a" plus
# those words as the user typed them, and the user's casing decides ("moose" from "a moose
# <<<...>>>" is "a moose", a common noun; from "a Moose" it is "a Moose"). Otherwise it is the
# bare entity, read as a proper name ("napoleon" from "the short emperor").
def entity_name(entity: str, raw: str) -> str:
    typed = {singular_word(w.lower()): w for w in re.findall(r"[A-Za-z0-9']+", raw)}
    words = [singular_word(w) for w in re.findall(r"[a-z0-9']+", entity.lower())]
    if words and all(w in typed for w in words):
        return "a " + " ".join(typed[w] for w in words)
    return entity


# Names for the Wikidata check: each side's raw text, plus its entity (see entity_name) when that
# names something else. The variant is never looked up: in "a dog named Napoleon" the fighter is
# the dog.
def wikidata_names(fighters: Sequence[Side]) -> list[str]:
    names: list[str] = []
    for fighter in fighters:
        names.append(fighter.raw)
        if not fighter.entity:
            continue
        name = entity_name(fighter.entity, fighter.raw)
        if lookup_query(name)[0] != lookup_query(fighter.raw)[0]:
            names.append(name)
    return names


# Run safety checks at the same time; if one raises, cancel the rest before re-raising.
async def _run_together(*checks: Awaitable[SafetyVerdict]) -> list[SafetyVerdict]:
    tasks = [asyncio.ensure_future(check) for check in checks]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        # Cancel the rest and await them (errors swallowed) so none outlives us, then re-raise.
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


# The first block in order (classifier before Wikidata), else ALLOWED.
def _first_block(verdicts: Sequence[SafetyVerdict]) -> SafetyVerdict:
    return next((v for v in verdicts if not v.allowed), ALLOWED)


# After intake parsed text: code rules on both sides, then, at the same time, the Wikidata name
# check and (if the model added words the user never typed) the classifier on its reading.
# Wikidata fails open; a classifier outage raises SafetyUnavailable.
async def check_parsed_sides(
    fighters: Sequence[Side],
    text: str,
    *,
    chat: ChatLLM,
    wikidata_lookup: WikidataLookup | None = None,
    wikidata_cache: WikidataCache | None = None,
) -> SafetyVerdict:
    verdict = check_side_rules(fighters)
    if not verdict.allowed:
        return verdict
    checks = [check_names(wikidata_names(fighters), lookup=wikidata_lookup, cache=wikidata_cache)]
    if adds_new_words(fighters, text):
        checks.insert(0, classify_text(describe_sides(fighters), chat=chat))
    return _first_block(await _run_together(*checks))


# Every layer on a Matchup that skipped intake: code rules on the request and both sides, then
# the classifier on the request and on the sides and the Wikidata name check, all at the same
# time. Wikidata fails open; a classifier outage raises SafetyUnavailable.
async def check_matchup(
    matchup: Matchup,
    *,
    chat: ChatLLM | None = None,
    wikidata_lookup: WikidataLookup | None = None,
    wikidata_cache: WikidataCache | None = None,
) -> SafetyVerdict:
    for verdict in (check_text_rules(matchup.raw_text), check_side_rules(matchup.fighters)):
        if not verdict.allowed:
            return verdict
    chat = chat or get_provider("chat")
    verdicts = await _run_together(
        classify_text(matchup.raw_text, chat=chat),
        classify_text(describe_sides(matchup.fighters), chat=chat),
        check_names(wikidata_names(matchup.fighters), lookup=wikidata_lookup, cache=wikidata_cache),
    )
    return _first_block(verdicts)
