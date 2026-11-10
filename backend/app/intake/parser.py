"""Pipeline step 1: free text -> IntakeResult. The model proposes; code rules decide (A02).

Safety checks (A04) live in app/safety and run inside parse_matchup; the HTTP endpoint plus
pending clarifications (D08) live elsewhere.
"""

import asyncio
import json
import re
from pathlib import Path

from pydantic import ValidationError

from app.config import get_settings
from app.intake.llm_io import CALL_ERRORS, as_data, data_block
from app.intake.llm_io import INPUT_END as INPUT_END  # re-exported for tests and golden checks
from app.intake.llm_io import INPUT_START as INPUT_START
from app.intake.rules import (
    IRREGULAR_PLURALS,
    MULTIPLIERS,
    SCALES,
    UNCHANGED,
    UNITS,
    clamp_count,
    find_size_reference,
    map_terrain,
    normalize_entity,
    read_count,
)
from app.intake.schema import Clarification, ParsedFighter, ParsedMatchup
from app.models.matchup import FighterRequest, IntakeResult, Matchup
from app.models.terrain import Terrain
from app.providers.base import ChatLLM, ChatMessage
from app.providers.registry import get_provider
from app.safety import (
    SafetyUnavailable,
    SafetyVerdict,
    blocked_result,
    check_parsed_sides,
    check_text_rules,
    classify_text,
)

PROMPT_NAME = "intake_parse"
PROMPT_PATH = Path(__file__).parents[2] / "prompts" / f"{PROMPT_NAME}.md"
MAX_TEXT_CHARS = 500
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

REPHRASE_QUESTION = "Sorry, we couldn't make out that matchup. Could you put it another way?"
EXAMPLE_OPTIONS = [
    "a grizzly bear vs 6 gray wolves",
    "a dozen house cats vs a golden retriever",
    "a toaster vs a goose",
]
TERRAIN_PHRASES = {
    Terrain.OPEN_FIELD: " on an open field",
    Terrain.FOREST: " in the forest",
    Terrain.WATER: " in the water",
    Terrain.SHORELINE: " on the shoreline",
    Terrain.URBAN: " in the city",
    Terrain.MOUNTAIN: " on the mountain",
}
SINGULAR_TO_PLURAL = {singular: plural for plural, singular in IRREGULAR_PLURALS.items()}


class ModelReplyError(ValueError):
    """The model's reply could not be used; the message is fed back to it on the retry."""


class IntakeUnavailable(RuntimeError):
    """Every model call failed because the provider was unavailable; no reply came back at all.

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
# Raises IntakeUnavailable when no attempt got a reply at all (the provider is down).
async def ask_model(chat: ChatLLM, text: str) -> ParsedMatchup | None:
    messages = build_messages(text)
    schema = ParsedMatchup.model_json_schema()
    outage: Exception | None = None
    got_reply = False
    for attempt in range(2):
        try:
            reply = await chat.complete(messages, prompt_name=PROMPT_NAME, json_schema=schema)
        except CALL_ERRORS as error:
            outage = error
            continue  # the call itself failed: the retry sends the same messages
        got_reply = True
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
    if not got_reply:
        raise IntakeUnavailable("The chat provider is unavailable; no reply came back.") from outage
    return None


# --- Wording ------------------------------------------------------------------------------


# Plural of a lowercase name's last word: "gray wolf" -> "gray wolves".
def plural(entity: str) -> str:
    *head, last = entity.split(" ")
    if last in SINGULAR_TO_PLURAL:
        last = SINGULAR_TO_PLURAL[last]
    elif last in UNCHANGED:
        pass
    elif last.endswith(("s", "x", "ch", "sh")):
        last += "es"
    elif len(last) > 1 and last.endswith("y") and last[-2] not in "aeiou":
        last = last[:-1] + "ies"
    else:
        last += "s"
    return " ".join([*head, last])


# "a goose", "an ant", "12 house cats".
def describe(count: int, entity: str) -> str:
    if count == 1:
        return f"{'an' if entity[:1] in 'aeiou' else 'a'} {entity}"
    return f"{count:,} {plural(entity)}"


# Swap one side's words in the user's text for new words, ignoring case.
def _replace_side(text: str, raw: str, new: str) -> str:
    return re.sub(re.escape(raw.strip()), new, text, count=1, flags=re.I)


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
        joke = f"Zero {plural(entity)} means nobody shows up to the fight!"
    else:
        joke = f"Fighters come in whole numbers only. Part of a {entity} can't put up a fight!"
    options = [_replace_side(text, fighter.raw, describe(n, entity)) for n in (1, 2)]
    return clarify(f"How many {plural(entity)} should fight?", options, f"{joke} How many?")


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


# One side, with every number decided by code; the second value lists its assumptions.
def build_fighter(fighter: ParsedFighter, max_count: int) -> tuple[FighterRequest, list[str]]:
    entity = normalize_entity(fighter.entity) or normalize_entity(fighter.raw)
    notes: list[str] = []
    count = read_count(fighter.raw).count
    if count is None:
        count = 1
        notes.append(f"Assumed 1 {entity}, since no number was given.")
    count, clamp_note = clamp_count(count, entity, max_count)
    if clamp_note:
        notes.append(clamp_note)
    variant = (fighter.variant or "").strip()[:MAX_VARIANT_CHARS]
    variant = None if not variant or has_number(variant) else variant  # number rule
    request = FighterRequest(
        entity=entity,
        count=count,
        variant=variant,
        size_reference=find_size_reference(fighter.raw),
        raw=fighter.raw.strip(),
    )
    return request, notes


# Model notes worth showing: short, non-empty, number-free (number rule), a few at most.
def _model_notes(parsed: ParsedMatchup) -> list[str]:
    notes = [n.strip() for n in parsed.assumptions if n.strip() and not has_number(n)]
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


# Free text -> IntakeResult (ok, clarify with one question, or blocked). Never raises for bad
# input; raises IntakeUnavailable when the chat provider or the safety classifier is down (an
# outage, not the user's wording; safety fails closed). Safety (A04): code rules run on the text
# before any model call, the classifier runs alongside the parse call, and an ok reading is
# checked again side by side. safety_chat defaults to the chat provider.
async def parse_matchup(
    text: str, *, chat: ChatLLM | None = None, safety_chat: ChatLLM | None = None
) -> IntakeResult:
    text = text.strip()
    if not text:
        return clarify("Who's fighting? Name two sides.", EXAMPLE_OPTIONS)
    if len(text) > MAX_TEXT_CHARS:
        return clarify("That's a long one! Can you sum up the matchup in one sentence?", [])
    rules = check_text_rules(text)
    if not rules.allowed:
        return blocked_result(rules)
    safety_chat = safety_chat or get_provider("chat")
    try:
        parsed, verdict = await parse_and_classify(text, chat or get_provider("chat"), safety_chat)
        if not verdict.allowed:
            return blocked_result(verdict)
        result = read_matchup(text, parsed)
        if result.matchup is not None:
            sides = await check_parsed_sides(result.matchup.fighters, text, chat=safety_chat)
            if not sides.allowed:
                return blocked_result(sides)
    except SafetyUnavailable as error:
        raise IntakeUnavailable("The safety check is unavailable; nothing may pass.") from error
    return result


# The model's reading -> IntakeResult (ok or clarify), with every number decided by code.
def read_matchup(text: str, parsed: ParsedMatchup | None) -> IntakeResult:
    if parsed is None:
        return clarify(REPHRASE_QUESTION, EXAMPLE_OPTIONS)
    if len(parsed.fighters) > 2:
        return too_many_sides(parsed.fighters)
    for fighter in parsed.fighters:
        problem = read_count(fighter.raw).problem
        if problem:
            return not_whole(text, fighter, problem)
    if parsed.needs_clarification or len(parsed.fighters) < 2:
        return vague(parsed)
    max_count = get_settings().sim_max_count
    built = [build_fighter(f, max_count) for f in parsed.fighters]
    terrain, terrain_note = map_terrain(parsed.terrain)
    notes = _model_notes(parsed) + [n for _, side_notes in built for n in side_notes]
    if terrain_note:
        notes.append(terrain_note)
    fighters = [request for request, _ in built]
    matchup = Matchup(
        fighters=fighters, terrain=terrain, raw_text=text, assumptions=list(dict.fromkeys(notes))
    )
    return IntakeResult(status="ok", matchup=matchup, message=ok_message(fighters, terrain))
