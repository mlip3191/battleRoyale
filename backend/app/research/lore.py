"""On-demand mythical creatures (G09, #39): model a legend that isn't in mythical.yaml.

The chat model reads the creature's Wikipedia article and picks real fighters as analogs,
abilities from the fixed list, and the sentence that justifies them (D-41). It never sets a
number. Code then checks every choice: the analogs are real fighters we have, the abilities are
on the list, the quote is in the article word for word, and any number of heads is in the
quote. Each ability needs a backing word in the quote or is dropped, and a giant analog needs
the quote to say the creature is big (#391). Anything that fails is blocked as "nonsense"; an
outage gives no sheet, never a guess.

When the model answers found false it also picks one reason from a fixed list (#403). Code maps
the two harmless reasons (a real animal, an object or machine) to "not a legend", which falls
back to an all-estimate sheet (#401); every other reason, and a missing or invalid one, stays
blocked. The model only picks a label; it never sets a number. A name with no Wikipedia article
is asked about too, with the name alone and a marker in place of the article: found false goes
through the same reason check, and found true is blocked because there is no text to check a
quote against.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.intake.llm_io import CALL_ERRORS, data_block
from app.models.stats import LoreProfile
from app.providers.base import ChatLLM, ChatMessage
from app.research.evidence_check import normalize_text, quote_in_passage
from app.research.mythical import Creature
from app.research.seed_fighters import fighter_slug, load_seed_fighters
from app.research.sources import SourceDocument, SourceError, fetch_article
from app.safety.media_names import safe_media_name

logger = logging.getLogger(__name__)

PROMPT_NAME = "lore_extract"
PROMPT_PATH = Path(__file__).parents[2] / "prompts" / f"{PROMPT_NAME}.md"
ATTEMPTS = 2
MAX_ARTICLE_CHARS = 12_000  # sent to the model; the quote is checked against the whole article
MAX_QUOTE_CHARS = 300
HEAD_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
}  # fmt: skip

# Words in the quote that back each power (#391); a power without one is dropped.
POWER_WORDS = {
    "flight": r"fl(?:y|ies|ying|ight|ew)|wings?|winged|soar(?:s|ing)?",
    "breath_weapon": r"breath\w*|breathes?|fire|flames?|fiery|spits?|spews?",
    "regeneration": r"regenerat\w*|regrow\w*|heal\w*|reviv\w*|resurrect\w*|reborn|rebirth|"
    r"back to life|ashes",
    "extra_heads": r"heads|\w+-headed",
}
# Fighters of a tonne or more (fixed here: mock-mode builder sheets hold placeholder masses).
# A legend may only be this big when its quote says so (#391).
GIANT_ANALOGS = {
    "African elephant",
    "Hippopotamus",
    "Tyrannosaurus rex",
    "Triceratops",
    "Great white shark",
    "Main battle tank",
    "Bulldozer",
    "Pickup truck",
}
BIG_WORDS = r"big|large|huge|giant\w*|enormous|massive|colossal|monstrous|immense"
NO_ARTICLE = "(no Wikipedia article was found)"  # sent in place of the article text (#403)
# Why the model answers found false (#403). Only the first two mean "a plausible fighter, just not
# a legend"; the rest, and anything else, are refusals. Fixed here and in prompts/lore_extract.md.
NOT_A_LEGEND_REASONS = frozenset({"real_animal", "object_or_machine", "generic_kind"})
REFUSAL_REASONS = frozenset({"person", "deity", "named_character", "weapon", "nonsense"})


class LoreReply(BaseModel):
    """The model's choices for one creature, or found false."""

    model_config = ConfigDict(extra="ignore", use_attribute_docstrings=True)

    found: bool
    """True when the article supports a choice of analogs."""
    body_analog: str | None = None
    """The real fighter whose body the legend describes, named as the list writes it."""
    size_analog: str | None = None
    """A real fighter whose size matches the legend, or null."""
    abilities: list[str] = []
    """Only from: flight, breath_weapon, regeneration, extra_heads."""
    heads: int | None = None
    """How many heads, only with extra_heads and only when the quote states it."""
    quote: str | None = None
    """The sentence that supports the choices, copied word for word."""
    reason: Any = None  # Any on purpose: a wrongly typed reason must fail closed, not raise
    """Only with found false: why (real_animal, object_or_machine, person, deity,
    named_character, weapon or nonsense). Code checks it; anything else is a refusal."""


@dataclass(frozen=True)
class LoreOutcome:
    """A creature to build, a block (the request is nonsense), "not a legend" (a plausible real
    fighter: fall back to estimates), or none of these (a service is down: try again later)."""

    creature: Creature | None = None
    blocked: bool = False
    not_a_legend: bool = False
    kind: str | None = None
    """With not_a_legend: the fixed reason ("real_animal" or "object_or_machine") (#453)."""


UNAVAILABLE = LoreOutcome()
NONSENSE = LoreOutcome(blocked=True)
NOT_A_LEGEND = LoreOutcome(not_a_legend=True)  # with no reason (a bare "not a legend")


class _TextOnly(HTMLParser):
    """Collects an HTML page's visible text, skipping scripts and styles."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


# An article's HTML as plain text, so a quote can be checked against what readers see.
def article_text(html: str) -> str:
    parser = _TextOnly()
    parser.feed(html)
    return normalize_text(" ".join(parser.parts))


# Real fighters the model may pick, by their lowercase names (the seed list, not legends).
def real_fighters() -> dict[str, str]:
    return {f.display_name.lower(): f.display_name for f in load_seed_fighters()}


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


# System prompt plus the creature, the fighters to choose from, and the article as data.
def build_messages(name: str, text: str, fighters: list[str]) -> list[ChatMessage]:
    request = (
        f"Creature: {name}\nReal fighters you may choose from: {', '.join(fighters)}\n\n"
        f"Article:\n{text[:MAX_ARTICLE_CHARS]}"
    )
    return [
        {"role": "system", "content": load_prompt()},
        {"role": "user", "content": data_block(request)},
    ]


# Ask the model twice at most; None when no usable reply came back.
async def ask_model(chat: ChatLLM, messages: list[ChatMessage]) -> LoreReply | None:
    schema = LoreReply.model_json_schema()
    for _ in range(ATTEMPTS):
        try:
            reply = await chat.complete(messages, prompt_name=PROMPT_NAME, json_schema=schema)
        except CALL_ERRORS as error:
            logger.warning("Lore call failed (%s).", type(error).__name__)
            continue
        text = reply.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        try:
            return LoreReply.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError):
            continue
    return None


# True when the quote states this number of heads, in digits or in words.
def heads_in_quote(heads: int, quote: str) -> bool:
    # The number must name the heads ("three heads", "nine-headed", "3 heads"), so a stray
    # "three" elsewhere ("one of three versions") doesn't count.
    names = [str(heads), *(w for w, n in HEAD_WORDS.items() if n == heads)]
    pattern = rf"\b(?:{'|'.join(names)})[\s-]+head(?:s|ed)?\b"  # not "three headlands"
    return re.search(pattern, quote, flags=re.IGNORECASE) is not None


# True when one of `words` (a regex alternation) appears in the quote as a whole word.
def _says(words: str, quote: str) -> bool:
    return re.search(rf"\b(?:{words})\b", quote, flags=re.IGNORECASE) is not None


# The powers the quote backs: a known power without a backing word is dropped (and logged);
# an unknown one is kept so the fixed-list check still blocks it.
def backed_powers(abilities: list[str], quote: str) -> list[str]:
    kept = [a for a in abilities if a not in POWER_WORDS or _says(POWER_WORDS[a], quote)]
    if dropped := [a for a in abilities if a not in kept]:
        logger.warning("Dropped lore powers the quote doesn't back: %s.", ", ".join(dropped))
    return kept


# The model's reply as a lore profile, or None when code can't verify every choice.
def verified_lore(
    reply: LoreReply, text: str, source: dict[str, str | datetime]
) -> LoreProfile | None:
    fighters = real_fighters()
    body = fighters.get((reply.body_analog or "").strip().lower())
    size = fighters.get((reply.size_analog or "").strip().lower()) if reply.size_analog else None
    quote = (reply.quote or "").strip()
    if not reply.found or body is None or (reply.size_analog and size is None):
        logger.warning("Rejected lore: not found, or an analog isn't a real fighter we have.")
        return None
    if not quote or len(quote) > MAX_QUOTE_CHARS or not quote_in_passage(quote, text):
        logger.warning("Rejected lore: the quote isn't in the article.")
        return None
    if reply.heads is not None and not heads_in_quote(reply.heads, quote):
        logger.warning("Rejected lore: the number of heads isn't in the quote.")
        return None
    if (size or body) in GIANT_ANALOGS and not _says(BIG_WORDS, quote):
        logger.warning("Rejected lore: a giant analog, but the quote never says it's big.")
        return None
    try:
        return LoreProfile.model_validate(
            {
                "body_analog": body,
                "size_analog": size,
                "abilities": backed_powers(reply.abilities, quote),
                "heads": reply.heads,
                "source": {**source, "quote": quote},
            }
        )
    except ValidationError:  # an ability off the list, or heads without extra_heads
        logger.warning("Rejected lore: abilities or heads don't fit the fixed rules.")
        return None


# The legend's article: "<Name> (mythology)" first, because a bare name such as "Hydra" can land
# on a disambiguation page (#324); the bare name when there's no such article.
async def fetch_legend_article(client: httpx.AsyncClient, name: str) -> SourceDocument | None:
    bare = name.strip()
    for title in (f"{bare[:1].upper()}{bare[1:]} (mythology)", bare):
        article = await fetch_article(client, title)
        if article is not None:
            return article
    return None


# What a found-false answer means: "not a legend" only for a stated harmless reason (#403),
# otherwise a block, so a missing, unknown or oddly typed reason fails closed.
def outcome_for_not_found(reason: object) -> LoreOutcome:
    if isinstance(reason, str) and reason.strip().lower() in NOT_A_LEGEND_REASONS:
        return LoreOutcome(not_a_legend=True, kind=reason.strip().lower())  # the reason goes on
    return NONSENSE


# The creature for a legend not in mythical.yaml, a block, "not a legend", or nothing when a
# service is down. With no article the model is still asked, with the name alone (#403, PM).
async def lore_for(name: str, client: httpx.AsyncClient, chat: ChatLLM) -> LoreOutcome:
    try:
        article = await fetch_legend_article(client, name)
    except (SourceError, httpx.HTTPError) as error:
        logger.warning("Could not fetch the article for %r (%s).", name, error)
        return UNAVAILABLE
    text = NO_ARTICLE
    if article is not None:
        text = article_text(article.body.decode("utf-8", errors="replace"))
    reply = await ask_model(chat, build_messages(name, text, sorted(real_fighters().values())))
    if reply is None:
        return UNAVAILABLE
    if not reply.found:
        return outcome_for_not_found(reply.reason)
    if article is None:  # a legend claimed with no article: no text to check a quote against
        return NONSENSE
    source = {
        "title": article.title,
        "url": article.url,
        "retrieved_at": article.retrieved_at,
        "license": article.license,
    }
    lore = verified_lore(reply, text, source)
    if lore is None:
        return NONSENSE
    slug = fighter_slug(name)
    display = name.strip()[:1].upper() + name.strip()[1:]
    media = safe_media_name(name) or "mythical creature"
    return LoreOutcome(creature=Creature(slug, display, media, lore))
