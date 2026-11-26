"""Pipeline step 1: free text -> IntakeResult. The model proposes; code rules decide (A02).

Safety checks (A04) live in app/safety and run inside parse_matchup; the HTTP endpoint plus
pending clarifications (D08) live elsewhere.
"""

import asyncio
import json
import re
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from app.config import get_settings
from app.intake.llm_io import CALL_ERRORS, as_data, data_block
from app.intake.llm_io import INPUT_END as INPUT_END  # re-exported for tests and golden checks
from app.intake.llm_io import INPUT_START as INPUT_START
from app.intake.rules import (
    ARTICLES,
    COUNT_FILLERS,
    GROUP_WORDS,
    MAX_COUNT_FILLERS,
    MULTIPLIERS,
    SCALES,
    UNITS,
    clamp_count,
    find_size_reference,
    map_terrain,
    normalize_entity,
    read_count,
    singular_word,
    terrain_in_text,
    tidy_numbers,
    without_group,
)
from app.intake.schema import Clarification, ParsedFighter, ParsedMatchup
from app.intake.steps import PARSE, intake_step
from app.models.matchup import FighterRequest, IntakeResult, Matchup
from app.models.terrain import Terrain
from app.providers.base import ChatLLM, ChatMessage
from app.providers.registry import get_intake_chat
from app.research.seed_fighters import (
    DEFAULT_KINDS,
    named_kind_words,
    picked_default,
    seed_habitat,
    spoken_name,
)
from app.safety import (
    SafetyUnavailable,
    SafetyVerdict,
    blocked_result,
    check_parsed_sides,
    check_text_rules,
    classify_text,
    cleaned_matchup,
)
from app.text import pluralize

PROMPT_NAME = "intake_parse"
PROMPT_PATH = Path(__file__).parents[2] / "prompts" / f"{PROMPT_NAME}.md"
MAX_TEXT_CHARS = 500
# Past this length, a read that fails or times out asks for a shorter matchup (#362).
# 200 is a heuristic, not a measured limit: about twice a wordy one-sentence matchup.
LONG_TEXT_CHARS = 200
LONG_TEXT_QUESTION = "That's a long one! Can you sum up the matchup in one sentence?"
MAX_VARIANT_CHARS = 60
MAX_MODEL_ASSUMPTIONS = 3
MAX_NOTE_CHARS = 200
# Words that separate the sides of a matchup in the user's text.
SIDE_SPLIT = re.compile(r"\s+(?:vs\.?|versus|v\.|against)\s+", re.I)
# Spelled-out numbers the number rule catches in model-written text, as whole words. Left out on
# purpose: "a"/"an" (articles), "no"/"none" (negation), "pair"/"couple" and fraction words
# (common in descriptions), and "one" ("one swarm", "each one"), all too common in normal prose.
_BIG_NUMBERS = set(SCALES) | (set(MULTIPLIERS) - {"pair", "couple"})  # thousand, hundred, dozen
NUMBER_WORDS = (
    (set(UNITS) - {"one"}) | _BIG_NUMBERS | {f"{w}s" for w in _BIG_NUMBERS} | {"zero"}
)  # "hundreds", "thousands" count too
# Model notes about its own output or about counts never reach the card (#475): the user should
# only see notes about their matchup, and code owns counts (it writes its own "Assumed 1 ..."
# note). Whole words, any case. Left out on purpose because real matchups use them: "field"
# ("open field terrain"), "object" ("a toaster is an object"), "model" ("a model rocket"),
# "output" ("power output"), "array" ("a solar array"), and "key".
INTERNAL_NOTE = re.compile(
    r"\b(?:"
    r"schemas?|json|formats?|formatted|formatting|prompts?|instructions?|top[\s-]level"
    r"|null|parse|parsed|parser|parsing|tokens?|language\s+model"
    r"|counts?|counted|quantity|quantities|defaulted|numbers?"
    r")\b",
    re.I,
)

REPHRASE_QUESTION = "Sorry, we couldn't make out that matchup. Could you put it another way?"
COMMON_KIND_NOTE = "Still not sure which kind you meant, so we'll use the most common one."
# Names the fighter code picked for a bare kind (#168), from the same table research uses.
DEFAULT_KIND_NOTE = "Not sure which {kind}, so we used the {pick}."
# Says so when the fighter we kept isn't the words the user typed (#500): "kimono dragon" -> dragon.
MISREAD_NOTE = "We read '{raw}' as {used}. Not what you meant? Edit it and fight again."
EXAMPLE_OPTIONS = [
    "a grizzly bear vs 6 gray wolves",
    "a dozen house cats vs a golden retriever",
    "a toaster vs a goose",
]
# Said when no place was typed and the sides can't share the arena (#619, ARCHITECTURE section 14).
SHORELINE_NOTE = "No place given, so they meet on the shoreline."
TERRAIN_PHRASES = {
    Terrain.OPEN_FIELD: " on an open field",
    Terrain.FOREST: " in the forest",
    Terrain.WATER: " in the water",
    Terrain.SHORELINE: " on the shoreline",
    Terrain.URBAN: " in the city",
    Terrain.MOUNTAIN: " on the mountain",
    Terrain.SKY: " in the sky",
}


class ModelReplyError(ValueError):
    """The model's reply could not be used; the message is fed back to it on the retry."""


class IntakeUnavailable(RuntimeError):
    """A model call failed (provider error, network, timeout) and no attempt gave a usable reply.

    Raised instead of the "please rephrase" result so an outage isn't blamed on the user's wording
    (issue #142 item 4). The API layer maps it to a "try again in a moment" response (D08).
    """


# --- Prompt -------------------------------------------------------------------------------


# The prompt template, read fresh so edits apply without a restart.
def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


# System prompt plus the user's text wrapped as data; the text appears nowhere else.
def build_messages(text: str) -> list[ChatMessage]:
    return [
        {"role": "system", "content": load_prompt()},
        {"role": "user", "content": data_block(text)},
    ]


# --- Talking to the model -----------------------------------------------------------------


# Lowercase with single spaces and no hyphens, so "raw" phrases match however the model spaced
# them ("main-battle tank" and "main battle tank" are the same words).
def _squash(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").split())


# The sides the user typed, split on "vs", "versus", "v." or "against": "a dragon vs a tank" -> 2.
def typed_sides(text: str) -> list[str]:
    parts = SIDE_SPLIT.split(text.strip())
    return [part.strip() for part in parts if part.strip()]


# Drop a ```json fence some models wrap around JSON.
def _strip_fence(reply: str) -> str:
    match = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", reply, re.S)
    return match.group(1) if match else reply


# Turn reply text into a ParsedMatchup, checking each side's words come from the user's text.
def read_reply(reply: str, text: str) -> ParsedMatchup:
    try:
        parsed = ParsedMatchup.model_validate(json.loads(_strip_fence(reply)))
    except (json.JSONDecodeError, ValidationError) as error:
        raise ModelReplyError(f"The reply was not valid JSON for the schema: {error}") from error
    data = _squash(as_data(text))
    for index, fighter in enumerate(parsed.fighters):
        if not fighter.raw.strip() or _squash(fighter.raw) not in data:
            raise ModelReplyError(
                f"fighters[{index}].raw must be copied exactly from the user's request; "
                f"{fighter.raw!r} is not in it."
            )
        if not normalize_entity(fighter.entity) and not normalize_entity(fighter.raw):
            raise ModelReplyError(f"fighters[{index}].entity must name the fighter.")
    sides = typed_sides(text)
    # A repeated raw is fine only if the user typed it that many times too ("a wolf vs a wolf").
    raws = [_squash(fighter.raw) for fighter in parsed.fighters]
    typed = [_squash(as_data(side)) for side in sides]
    if any(raws.count(raw) > max(1, typed.count(raw)) for raw in raws):
        raise ModelReplyError("Two fighters have the same raw; each side must have its own words.")
    if len(sides) >= 2 and len(parsed.fighters) < len(sides):
        raise ModelReplyError(
            f"The request names {len(sides)} sides ({'; '.join(sides)}) but fighters lists "
            f"{len(parsed.fighters)}. List every side, including vehicles, machines, objects, "
            "and mythical creatures."
        )
    return parsed


# Ask the model, retrying once with the problem described; None if the replies were unusable.
# Raises IntakeUnavailable when any call failed and no reply was usable, so a provider error
# isn't blamed on the user's wording; only all-replies-unusable means "please rephrase".
@intake_step(PARSE)
async def ask_model(chat: ChatLLM, text: str) -> ParsedMatchup | None:
    messages = build_messages(text)
    schema = ParsedMatchup.model_json_schema()
    outage: Exception | None = None
    for attempt in range(2):
        try:
            reply = await chat.complete(messages, prompt_name=PROMPT_NAME, json_schema=schema)
        except CALL_ERRORS as error:
            outage = error
            continue  # the call itself failed: the retry sends the same messages
        try:
            return read_reply(reply, text)
        except ModelReplyError as error:
            if attempt == 0:
                problem = str(error)[: MAX_NOTE_CHARS * 3]
                messages = [
                    *messages,
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": f"{problem}\nReply again with JSON only."},
                ]
    if outage is not None:
        raise IntakeUnavailable(
            "The chat provider failed and no usable reply came back."
        ) from outage
    return None


# --- Wording ------------------------------------------------------------------------------


# "a goose", "an ant", "12 house cats".
def describe(count: int, entity: str) -> str:
    if count == 1:
        return f"{'an' if entity[:1] in 'aeiou' else 'a'} {entity}"
    return f"{count:,} {pluralize(entity)}"


# Swap one side's words in the user's text for new words, ignoring case.
def _replace_side(text: str, raw: str, new: str) -> str:
    return re.sub(re.escape(raw.strip()), new, text, count=1, flags=re.I)


# With no place typed, a water-only fighter against a land-only one meets on the shoreline, so
# neither is stranded (#619). Habitats come from the seed list; a fighter not on it, or two sides
# that can share the arena, leave the default alone.
def meets_on_the_shoreline(fighters: Sequence[FighterRequest]) -> bool:
    habitats = {seed_habitat(f.entity, f.variant, f.raw) for f in fighters}
    return habitats == {"water", "land"}


# Friendly message once the matchup is understood.
def ok_message(fighters: list[FighterRequest], terrain: Terrain) -> str:
    sides = " vs ".join(describe(f.count, f.entity) for f in fighters)
    sentence = f"{sides}{TERRAIN_PHRASES.get(terrain, '')}. Let's get ready to rumble!"
    return sentence[0].upper() + sentence[1:]


# --- Results ------------------------------------------------------------------------------


# A clarifying question with 2-4 tidy options (examples fill in when the model gave too few).
def clarify(question: str, options: list[str], message: str | None = None) -> IntakeResult:
    tidy: list[str] = []
    for option in (o.strip() for o in options):
        if option and option not in tidy and len(option) <= MAX_NOTE_CHARS:
            tidy.append(option)
    if len(tidy) < 2:
        tidy = EXAMPLE_OPTIONS
    return IntakeResult(
        status="clarify", question=question, options=tidy[:4], message=message or question
    )


# More than two sides: offer each pair as a two-sided matchup.
def too_many_sides(fighters: list[ParsedFighter]) -> IntakeResult:
    raws = [f.raw.strip() for f in fighters]
    pairs = [f"{a} vs {b}" for i, a in enumerate(raws) for b in raws[i + 1 :]]
    return clarify(
        "Our arena only fits two sides for now. Which two should fight? "
        '(Group a pack together, like "3 wolves", to make it one side.)',
        pairs,
    )


# A fraction or zero on one side: a joke, then the same matchup with whole numbers.
def not_whole(text: str, fighter: ParsedFighter, problem: str) -> IntakeResult:
    entity = normalize_entity(fighter.entity) or normalize_entity(fighter.raw)
    if problem == "zero":
        joke = f"Zero {pluralize(entity)} means nobody shows up to the fight!"
    else:
        joke = f"Fighters come in whole numbers only. Part of a {entity} can't put up a fight!"
    options = [_replace_side(text, fighter.raw, describe(n, entity)) for n in (1, 2)]
    return clarify(f"How many {pluralize(entity)} should fight?", options, f"{joke} How many?")


# A missing opponent or a fighter too vague to research.
def vague(parsed: ParsedMatchup) -> IntakeResult:
    asked = parsed.needs_clarification or Clarification(question="", options=[])
    if len(parsed.fighters) == 1:
        side = parsed.fighters[0].raw.strip()
        question = asked.question or f"Who should {side} fight?"
        fallback = [f"{side} vs {other}" for other in ("a gray wolf", "a house cat", "a goose")]
        return clarify(question, asked.options or fallback)
    return clarify(asked.question or REPHRASE_QUESTION, asked.options)


# True if model-written text holds a digit or a spelled-out number ("four thousand"); such text
# is dropped so the model never sets a number. Whole words only: "often" and "weight" are fine.
def has_number(text: str) -> bool:
    if any(ch.isdigit() for ch in text):
        return True
    return any(word in NUMBER_WORDS for word in re.findall(r"[a-z]+", text.lower()))


# Text without model names that hold a digit after a letter ("m1", "t72", "b2"), which are names,
# not numbers (#561).
def _no_names(text: str) -> str:
    return re.sub(r"\b[a-z]+\d[a-z0-9]*\b", " ", text.lower())


# One side, with every number decided by code; the second value lists its assumptions.
def build_fighter(fighter: ParsedFighter, max_count: int) -> tuple[FighterRequest, list[str]]:
    entity = without_group(normalize_entity(fighter.entity) or normalize_entity(fighter.raw))
    notes: list[str] = []
    reading = read_count(fighter.raw)
    count = reading.count
    if count is None:
        count = 1
        notes.append(f"Assumed 1 {entity}, since no number was given.")
    elif reading.group:
        notes.append(
            f"Assumed {count:,} {pluralize(entity)} for '{reading.group}', since no number "
            "was given."
        )
    elif reading.multiplied:  # "2 packs of 5" -> 10: both numbers typed, code multiplied (#573)
        notes.append(f"We read '{reading.multiplied}' as {count:,}.")
    count, clamp_note = clamp_count(count, entity, max_count)
    if clamp_note:
        notes.append(clamp_note)
    variant = (fighter.variant or "").strip()[:MAX_VARIANT_CHARS]
    variant = None if not variant or has_number(variant) else variant  # number rule
    if variant is None and entity in DEFAULT_KINDS:
        # The model dropped a named kind ("a polar bear" read as "bear"): keep the user's word.
        # A product name like "m1" is the user's word, not a number, so only a count blocks it.
        named = named_kind_words(entity, _GROUP_PHRASE.sub("", fighter.raw))  # never "packs"
        variant = named[:MAX_VARIANT_CHARS] if named and not has_number(_no_names(named)) else None
    request = FighterRequest(
        entity=entity,
        count=count,
        variant=variant,
        size_reference=find_size_reference(fighter.raw),
        raw=fighter.raw.strip(),
    )
    return request, notes


# Model notes worth showing: short, non-empty, number-free (number rule), only about the
# matchup (no talk of the schema, format or counts, #475), a few at most.
def _model_notes(parsed: ParsedMatchup) -> list[str]:
    notes = [
        n.strip()
        for n in parsed.assumptions
        if n.strip() and not has_number(n) and not INTERNAL_NOTE.search(n)
    ]
    return [n[:MAX_NOTE_CHARS] for n in notes][:MAX_MODEL_ASSUMPTIONS]


# Parse and classify at the same time. A block from the classifier wins as soon as it arrives
# (the parse call is cancelled); otherwise both finish. Any error cancels whatever is running.
async def parse_and_classify(
    text: str, chat: ChatLLM, safety_chat: ChatLLM
) -> tuple[ParsedMatchup | None, SafetyVerdict]:
    parse = asyncio.create_task(ask_model(chat, text))
    safety = asyncio.create_task(classify_text(text, chat=safety_chat))
    try:
        done, _ = await asyncio.wait({parse, safety}, return_when=asyncio.FIRST_COMPLETED)
        if safety in done and not safety.result().allowed:
            return None, safety.result()
        return await parse, await safety
    finally:
        for task in (parse, safety):
            task.cancel()  # no effect on a finished task
        await asyncio.gather(parse, safety, return_exceptions=True)


# The question for a matchup too long to read: sum it up in one sentence.
def too_long() -> IntakeResult:
    return clarify(LONG_TEXT_QUESTION, [])


# Free text -> IntakeResult (ok, clarify with one question, or blocked). Never raises for bad
# input; raises IntakeUnavailable when the chat provider or the safety classifier is down (an
# outage, not the user's wording; safety fails closed). Safety (A04): code rules run on the text
# before any model call, the classifier runs alongside the parse call, and an ok reading is
# checked again side by side. safety_chat defaults to the intake chat (short timeout, #169).
# ask=False is for the answer to a question (D08): a still-vague fighter is accepted with a note.
async def parse_matchup(
    text: str,
    *,
    chat: ChatLLM | None = None,
    safety_chat: ChatLLM | None = None,
    ask: bool = True,
) -> IntakeResult:
    text = text.strip()
    if not text:
        return clarify("Who's fighting? Name two sides.", EXAMPLE_OPTIONS)
    if len(text) > MAX_TEXT_CHARS:
        return too_long()
    text, number_notes = tidy_numbers(text)  # "1e3" and "-3" become counts we can read (#561)
    rules = check_text_rules(text)
    if not rules.allowed:
        refused = blocked_result(rules)
        cleaned = cleaned_matchup(text) if rules.instructions else None
        # The matchup without its instructions, as a chip the user can pick (#621).
        return refused.model_copy(update={"options": [cleaned]}) if cleaned else refused
    safety_chat = safety_chat or get_intake_chat()
    try:
        parsed, verdict = await parse_and_classify(text, chat or get_intake_chat(), safety_chat)
        if not verdict.allowed:
            return blocked_result(verdict)
        result = read_matchup(text, parsed, ask=ask, notes=number_notes)
        if result.matchup is not None:
            sides = await check_parsed_sides(result.matchup.fighters, text, chat=safety_chat)
            if not sides.allowed:
                return blocked_result(sides)
    except SafetyUnavailable as error:
        raise IntakeUnavailable("The safety check is unavailable; nothing may pass.") from error
    return result


# One note per bare kind that research will replace with its default fighter (#168), e.g.
# "Not sure which bear, so we used the grizzly bear."
def default_kind_notes(fighters: list[FighterRequest]) -> list[str]:
    return [
        DEFAULT_KIND_NOTE.format(kind=kind, pick=pick) for kind, pick in _default_picks(fighters)
    ]


# Each bare kind and the default fighter it becomes, as spoken: ("bear", "grizzly bear").
def _default_picks(fighters: list[FighterRequest]) -> list[tuple[str, str]]:
    picks = []
    for fighter in fighters:
        pick = picked_default(fighter.entity, fighter.variant, fighter.raw)
        if pick is not None:
            # The table's own word, so "bears" reads "Not sure which bear".
            kind = next(word for word, slug in DEFAULT_KINDS.items() if slug == pick.id)
            picks.append((kind, spoken_name(pick.display_name)))
    return picks


# True when a model note says what a default-kind note already says (#621): "Assumed gray
# wolves." next to "Not sure which wolf, so we used the gray wolf." It must name every word of
# the pick, so a note about something else ("Assumed it is night.") stays.
def _repeats_pick(note: str, pick: str) -> bool:
    words = {singular_word(w) for w in re.findall(r"[a-z]+", note.lower())}
    return set(_name_words(pick)) <= words


# A name's words, singular, no hyphens or articles: "Main-battle tanks" -> main, battle, tank.
def _name_words(name: str) -> list[str]:
    words = normalize_entity(name).replace("-", " ").split()
    return [singular_word(w) for w in words if w not in ARTICLES]


# Country tags that may drop without changing the fighter: "US Navy SEALs" -> navy seal (D-69).
_IGNORED_TYPED_WORDS = {"us", "usa", "uk"}


# A side's raw without its trailing battlefield: "6 gray wolves in a forest" -> "6 gray wolves".
def _without_place(raw: str) -> str:
    place = terrain_in_text(raw)
    return raw[: raw.lower().rfind(place.lower())].rstrip() if place else raw


# A group phrase in a side's words, "swarm of " in "a swarm of bees": its count is noted already.
# Small words after "of" go too, so "about" in "a pack of about 12 wolves" is not a name, and
# the plural "colonies" counts as a group word (#573).
_GROUP_PHRASE = re.compile(
    rf"\b(?:{'|'.join(GROUP_WORDS)}|colonies)s?\s+of\s+"
    rf"(?:(?:{'|'.join(sorted(COUNT_FILLERS))})\s+){{0,{MAX_COUNT_FILLERS}}}",
    re.I,
)


# A fighter's words as kept, for the card: no articles or hyphens, and never singularized, so a
# name like "Abrams" keeps its "s" (#561).
def _kept_words(fighter: FighterRequest) -> str:
    names = (fighter.variant or "", fighter.entity)
    words = [w for name in names for w in name.lower().replace("-", " ").split()]
    return " ".join(dict.fromkeys(w for w in words if w not in ARTICLES))


# One note per side whose typed words didn't all make it into the fighter we kept (#500), e.g.
# "We read 'kimono dragon' as dragon." Code-built, so a typed number in raw is fine here.
def misread_notes(fighters: list[FighterRequest]) -> list[str]:
    notes = []
    for fighter in fighters:
        raw = _without_place(fighter.raw).strip()
        words = _name_words(_GROUP_PHRASE.sub("", raw))
        typed = [w for w in words if w not in _IGNORED_TYPED_WORDS]
        used = list(dict.fromkeys(_name_words(fighter.variant or "") + _name_words(fighter.entity)))
        if not typed or not used or set(typed) <= set(used):
            continue
        kept = _kept_words(fighter)
        room = max(1, MAX_NOTE_CHARS - len(MISREAD_NOTE.format(raw="", used=kept)))
        if len(raw) > room:
            raw = raw[: room - 1].rstrip() + "…"
        notes.append(MISREAD_NOTE.format(raw=raw, used=kept))
    return notes


# The model's reading -> IntakeResult (ok or clarify), with every number decided by code.
# ask=False accepts a still-vague fighter with a note instead of asking again. notes are code
# notes from before the model call (tidy_numbers), shown first.
def read_matchup(
    text: str, parsed: ParsedMatchup | None, *, ask: bool = True, notes: Sequence[str] = ()
) -> IntakeResult:
    if parsed is None:
        return clarify(REPHRASE_QUESTION, EXAMPLE_OPTIONS)
    if len(parsed.fighters) > 2:
        return too_many_sides(parsed.fighters)
    for fighter in parsed.fighters:
        problem = read_count(fighter.raw).problem
        if problem:
            return not_whole(text, fighter, problem)
    if len(parsed.fighters) < 2 or (ask and parsed.needs_clarification):
        return vague(parsed)
    max_count = get_settings().sim_max_count
    built = [build_fighter(f, max_count) for f in parsed.fighters]
    typed_place = terrain_in_text(text)
    terrain, terrain_note = map_terrain(parsed.terrain or typed_place)
    if terrain == Terrain.ARENA and terrain_note is None and typed_place:
        # a plain "arena" (or none) never hides a typed place; an unknown word keeps its note
        typed, typed_note = map_terrain(typed_place)
        if typed != Terrain.ARENA:
            terrain, terrain_note = typed, typed_note
    fighters = [request for request, _ in built]
    if (
        terrain == Terrain.ARENA
        and terrain_note is None
        and not typed_place
        and not parsed.terrain
        and meets_on_the_shoreline(fighters)
    ):
        terrain, terrain_note = Terrain.SHORELINE, SHORELINE_NOTE  # a typed place always wins
    spoken_picks = [pick for _, pick in _default_picks(fighters)]
    # One note per fighter: a model note that repeats a default-kind pick gives way to it (#621).
    model_notes = [
        n for n in _model_notes(parsed) if not any(_repeats_pick(n, p) for p in spoken_picks)
    ]
    notes = list(notes) + model_notes + [n for _, side_notes in built for n in side_notes]
    if terrain_note:
        notes.append(terrain_note)
    picks = default_kind_notes(fighters)
    notes += picks + misread_notes(fighters)
    if parsed.needs_clarification and not picks:
        notes.append(COMMON_KIND_NOTE)
    matchup = Matchup(
        fighters=fighters, terrain=terrain, raw_text=text, assumptions=list(dict.fromkeys(notes))
    )
    return IntakeResult(status="ok", matchup=matchup, message=ok_message(fighters, terrain))
