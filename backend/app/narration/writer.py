"""The LLM announcer writer: intro, play-by-play, and outro scripts, checked line by line (A06).

The model only writes words. Code gives it the compact fact list (display names from the stat
sheets, never the user's raw text), fills every outro number into placeholders, and checks every
reply: the Script shape, speakers, line counts and lengths, at_event indexes, and the number
guard. An invalid reply is regenerated once; a second invalid reply, or any provider error, falls
back to the matching template script (fallback=True). Each script falls back on its own, and the
writer never raises because of the model.
"""

import asyncio
import json
import logging
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from app.models.narration import Script, ScriptLine
from app.models.simulation import FairFight, FightEvent, SimulationResult
from app.models.stats import StatSheet
from app.narration.facts import FACTOR_WORDS, NarrationFacts, build_facts, fact_lines
from app.narration.number_guard import FoundNumber, find_unsupported_numbers
from app.narration.templates import (
    MAX_BEATS,
    MAX_LINE,
    MIN_BEATS,
    _hint,
    fair_fight_line,
    intro_script,
    mask_names,
    outro_script,
    play_by_play_script,
)
from app.providers.base import ChatLLM, ChatMessage
from app.providers.registry import get_provider

logger = logging.getLogger(__name__)

Kind = Literal["intro", "play_by_play", "outro"]

PROMPTS_DIR = Path(__file__).parents[2] / "prompts"
# The prompt file (and mock fixture) for each script.
PROMPT_NAMES: dict[Kind, str] = {
    "intro": "announcer_intro",
    "play_by_play": "play_by_play",
    "outro": "outro",
}
# Allowed number of lines per script (PRODUCT_SPEC tone guide; the outro has four parts + sign-off).
LINE_COUNTS: dict[Kind, tuple[int, int]] = {
    "intro": (4, 8),
    "play_by_play": (MIN_BEATS, MAX_BEATS),
    "outro": (4, 6),
}
SPEAKERS = ("announcer", "color_commentator")
PLACEHOLDER = re.compile(r"\{([A-Za-z_]+)\}")
# "55%%" or "55% percent" after a percentage placeholder: keep one percent sign.
_EXTRA_PERCENT = re.compile(r"(\d%)\s*(?:%|per ?cent\b)", re.I)
MAX_REASON_CHARS = 300

# What each outro placeholder means, as told to the model (values are filled in by code).
PLACEHOLDER_HELP = {
    "winner": "the winning fighter's name",
    "loser": "the losing fighter's name",
    "win_pct": "how often the winner won, with the percent sign",
    "red_win_pct": "how often the red-corner fighter won, with the percent sign",
    "blue_win_pct": "how often the blue-corner fighter won, with the percent sign",
    "draw_pct": "how often it was a draw, with the percent sign",
    "runs": "how many fights were simulated",
    "deciding_factor": "the deciding factor, in words",
    "fair_fight": "the whole fair-fight sentence, written by code",
    "fair_side": "the fighter whose count makes it a fair fight",
    "fair_count": "how many of that fighter make it a coin flip",
    "fair_win_pct": "how often they win at that count, with the percent sign",
}


class ScriptRejected(ValueError):
    """A reply that cannot be used; the message says why and goes back to the model on the retry."""


# A prompt template, read fresh so edits apply without a restart.
def load_prompt(prompt_name: str) -> str:
    """The text of backend/prompts/<prompt_name>.md."""
    return (PROMPTS_DIR / f"{prompt_name}.md").read_text(encoding="utf-8")


# --- Outro placeholders -------------------------------------------------------------------


def outro_placeholders(facts: NarrationFacts) -> dict[str, str]:
    """The placeholder values the outro may use for this battle (only those that exist)."""
    red, blue = facts.fighters
    names = [red.display_name, blue.display_name]
    values = {
        "red_win_pct": f"{facts.win_pct[0]}%",
        "blue_win_pct": f"{facts.win_pct[1]}%",
        "draw_pct": f"{facts.draw_pct}%",
        "runs": f"{facts.runs:,}",
        "deciding_factor": FACTOR_WORDS.get(
            facts.deciding_factor, facts.deciding_factor.replace("_", " ")
        ),
        "fair_fight": fair_fight_line(facts, names).text,
    }
    if facts.outcome in ("win_0", "win_1"):
        side = int(facts.outcome[-1])
        values["winner"] = names[side]
        values["loser"] = names[1 - side]
        values["win_pct"] = f"{facts.win_pct[side]}%"
    if facts.fair_count is not None and facts.fair_side is not None:
        values["fair_side"] = names[facts.fair_side]
        values["fair_count"] = f"{facts.fair_count:,}"
        if facts.fair_win_pct is not None:
            values["fair_win_pct"] = f"{facts.fair_win_pct}%"
    return values


def required_placeholders(facts: NarrationFacts) -> list[tuple[str, ...]]:
    """Placeholders the outro must use; each tuple is satisfied by any one of its names."""
    verdict: list[tuple[str, ...]] = []
    if facts.outcome in ("win_0", "win_1"):
        verdict = [("winner",), ("win_pct",)]
    elif facts.outcome == "draw":
        verdict = [("draw_pct",)]
    return [*verdict, ("deciding_factor",), ("fair_fight", "fair_count")]


# Put code's values into the model's placeholders; any unknown name makes the reply invalid.
def fill_placeholders(text: str, values: dict[str, str]) -> str:
    """ "{winner} won {win_pct} of the time" -> "Gray wolf won 55% of the time"."""
    unknown = sorted({name for name in PLACEHOLDER.findall(text) if name not in values})
    if unknown:
        raise ScriptRejected(f"unknown placeholder(s): {', '.join('{' + u + '}' for u in unknown)}")
    filled = PLACEHOLDER.sub(lambda m: values[m.group(1)], text)
    return _EXTRA_PERCENT.sub(r"\1", filled)


# --- Checking a script --------------------------------------------------------------------


# The numbers in a line the inputs do not back, reading the fighters' names as plain words.
def unsupported_numbers(text: str, facts: NarrationFacts) -> list[FoundNumber]:
    """Like find_unsupported_numbers, but a name such as "Three-toed sloth" is never a number."""
    names = [f.display_name for f in facts.fighters]
    return find_unsupported_numbers(mask_names(text, names), facts.allowed)


def check_script(script: Script, facts: NarrationFacts, log_len: int) -> list[str]:
    """Every problem with a script (empty list = usable). Works on LLM and template scripts."""
    kind: Kind = script.kind
    low, high = LINE_COUNTS[kind]
    problems = []
    if not low <= len(script.lines) <= high:
        problems.append(f"{kind} needs {low} to {high} lines, got {len(script.lines)}")
    for n, line in enumerate(script.lines):
        problems += [f"line {n}: {p}" for p in _line_problems(line, facts)]
    problems += _event_problems(script, log_len)
    legend = any(f.is_legend for f in facts.fighters)
    if kind == "intro" and legend and not any("legend" in ln.text.lower() for ln in script.lines):
        problems.append('a mythical fighter is in this fight: say its stats come from "legend"')
    return problems


# Problems with one line's text: empty, too long, leftover braces, or numbers nobody gave it.
def _line_problems(line: ScriptLine, facts: NarrationFacts) -> list[str]:
    problems = []
    if not line.text.strip():
        problems.append("empty text")
    if len(line.text) > MAX_LINE:
        problems.append(f"{len(line.text)} characters (max {MAX_LINE})")
    if "{" in line.text or "}" in line.text:
        problems.append("curly braces left in the text")
    bad = unsupported_numbers(line.text, facts)
    if bad:
        problems.append("numbers not in the fact list: " + ", ".join(repr(b.text) for b in bad))
    return problems


# at_event rules: play-by-play lines point at real events in order; other scripts point at none.
def _event_problems(script: Script, log_len: int) -> list[str]:
    events = [line.at_event for line in script.lines]
    if script.kind != "play_by_play" or log_len == 0:
        return [] if all(e is None for e in events) else [f"{script.kind} lines take no at_event"]
    indexes = [e for e in events if e is not None and 0 <= e < log_len]
    if len(indexes) != len(events):
        return [f"every at_event must be an index from 0 to {log_len - 1}"]
    if indexes != sorted(indexes):
        return ["at_event must never go backwards"]
    return []


# --- Reading a reply ----------------------------------------------------------------------


# The list of line objects in a JSON reply (a ```json fence around it is tolerated).
def _reply_items(reply: object) -> list[Any]:
    if not isinstance(reply, str):
        raise ScriptRejected("the reply was not text")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ScriptRejected(f"the reply is not valid JSON ({error.msg})") from error
    if not isinstance(data, dict) or not isinstance(data.get("lines"), list):
        raise ScriptRejected('the reply must be a JSON object {"lines": [...]}')
    return data["lines"]


# One reply item as a ScriptLine: placeholders filled (outro), spaces tidied, shape validated.
def _read_line(kind: Kind, item: object, values: dict[str, str], n: int) -> ScriptLine:
    if not isinstance(item, dict):
        raise ScriptRejected(f"line {n} is not an object")
    item = dict(item)
    if kind != "play_by_play":
        item.pop("at_event", None)  # intro and outro are not synced to fight events
    text = item.get("text")
    if isinstance(text, str):
        text = fill_placeholders(text, values) if kind == "outro" else text
        item["text"] = " ".join(
            unicodedata.normalize("NFKC", text).replace("\u200b", "").replace("\u00ad", "").split()
        )
    try:
        return ScriptLine.model_validate(item)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise ScriptRejected(f"line {n}: {where}: {first['msg']}") from error


def read_reply(kind: Kind, reply: object, facts: NarrationFacts, log_len: int) -> Script:
    """Turn a model reply into a checked Script (fallback=False), or raise ScriptRejected."""
    items = _reply_items(reply)
    values = outro_placeholders(facts) if kind == "outro" else {}
    lines = [_read_line(kind, item, values, n) for n, item in enumerate(items)]
    if kind == "outro":
        raw = [item.get("text", "") for item in items if isinstance(item, dict)]
        used = {name for text in raw if isinstance(text, str) for name in PLACEHOLDER.findall(text)}
        groups = required_placeholders(facts)
        missing = [" or ".join(group) for group in groups if not used & set(group)]
        if missing:
            raise ScriptRejected(f"the outro must use these placeholders: {', '.join(missing)}")
    script = Script(kind=kind, lines=lines, fallback=False)
    problems = check_script(script, facts, log_len)
    if problems:
        raise ScriptRejected("; ".join(problems))
    return script


# --- Talking to the model -----------------------------------------------------------------


# How many beats to ask for: one per event, kept between MIN_BEATS and MAX_BEATS.
def beat_target(log_len: int) -> int:
    """8 for a short log, one per event up to 20."""
    return max(MIN_BEATS, min(MAX_BEATS, log_len))


# One event as a compact prompt line: index | t | type | side | group_size | hint.
def _event_line(i: int, event: FightEvent, facts: NarrationFacts) -> str:
    who = facts.fighters[event.side].display_name
    hint = _hint(event, "-", use_hint=True)
    return f"{i} | {event.t:g} | {event.type} | {who} | {event.group_size} | {hint}"


# The task-specific part of the user message: counts, the log, or the placeholders.
def _task_lines(kind: Kind, facts: NarrationFacts, log: Sequence[FightEvent]) -> list[str]:
    low, high = LINE_COUNTS[kind]
    if kind == "intro":
        return [f"TASK: write the intro in {low} to {high} lines."]
    if kind == "play_by_play":
        return [
            "EVENT LOG (index | t | type | side | group_size | hint):",
            *(_event_line(i, e, facts) for i, e in enumerate(log)),
            "",
            f"TASK: write exactly {beat_target(len(log))} beats; every at_event is an index "
            f"from 0 to {len(log) - 1}, never going backwards.",
        ]
    values = outro_placeholders(facts)
    must = [" or ".join("{" + n + "}" for n in group) for group in required_placeholders(facts)]
    return [
        "PLACEHOLDERS you may use (code fills them in):",
        *(f"{{{name}}}: {PLACEHOLDER_HELP[name]}" for name in values),
        "",
        f"You must use: {', '.join(must)}.",
        f"TASK: write the outro in {low} to {high} lines, with no numbers of your own.",
    ]


def build_messages(
    kind: Kind, facts: NarrationFacts, log: Sequence[FightEvent]
) -> list[ChatMessage]:
    """System prompt from the file, then the fact list (display names only) and the task."""
    user = ["FACT LIST:", *fact_lines(facts), "", *_task_lines(kind, facts, log)]
    return [
        {"role": "system", "content": load_prompt(PROMPT_NAMES[kind])},
        {"role": "user", "content": "\n".join(user)},
    ]


def reply_schema(kind: Kind, log_len: int) -> dict[str, Any]:
    """JSON schema for {"lines": [{"speaker", "text", "at_event"?}]} (at_event: play-by-play)."""
    low, high = LINE_COUNTS[kind]
    props: dict[str, Any] = {
        "speaker": {"type": "string", "enum": list(SPEAKERS)},
        "text": {"type": "string", "minLength": 1, "maxLength": MAX_LINE},
    }
    required = ["speaker", "text"]
    if kind == "play_by_play":
        props["at_event"] = {"type": "integer", "minimum": 0, "maximum": max(log_len - 1, 0)}
        required.append("at_event")
    item = {"type": "object", "properties": props, "required": required}
    item["additionalProperties"] = False
    lines = {"type": "array", "minItems": low, "maxItems": high, "items": item}
    return {
        "type": "object",
        "properties": {"lines": lines},
        "required": ["lines"],
        "additionalProperties": False,
    }


# Ask for one script, regenerating once if the reply is invalid; the template on any failure.
async def write_one(
    kind: Kind,
    chat: ChatLLM,
    facts: NarrationFacts,
    result: SimulationResult,
    template: Script,
) -> Script:
    """The model's script if a reply passes every check within two tries, else `template`."""
    log = result.representative_log
    prompt_name = PROMPT_NAMES[kind]
    messages = build_messages(kind, facts, log)
    schema = reply_schema(kind, len(log))
    for attempt in range(2):
        try:
            reply = await chat.complete(messages, prompt_name=prompt_name, json_schema=schema)
        except Exception as error:  # timeout, connection, missing mock fixture: never fatal
            logger.warning("%s: chat call failed (%s); using the template", prompt_name, error)
            return template
        try:
            return read_reply(kind, reply, facts, len(log))
        except ScriptRejected as error:
            reason = str(error)[:MAX_REASON_CHARS]
            logger.info("%s: reply %d rejected: %s", prompt_name, attempt + 1, reason)
            messages = [
                *messages,
                {"role": "assistant", "content": str(reply)},
                {
                    "role": "user",
                    "content": f"That reply was rejected: {reason}\n"
                    "Write it again, following every rule. Reply with JSON only.",
                },
            ]
    logger.warning("%s: no valid reply after a retry; using the template", prompt_name)
    return template


async def write_scripts(
    stat_sheets: Sequence[StatSheet],
    result: SimulationResult,
    fair_fight: FairFight | None = None,
    *,
    chat: ChatLLM | None = None,
    counts: Sequence[int] | None = None,
) -> list[Script]:
    """Intro, play-by-play, and outro, in broadcast order; each falls back to its template alone.

    `chat` defaults to the registry's chat provider; `counts` (from the Matchup) sets each side's
    fighter count, as in build_facts.
    """
    facts = build_facts(stat_sheets, result, fair_fight, counts)
    templates: dict[Kind, Script] = {
        "intro": intro_script(facts),
        "play_by_play": play_by_play_script(facts, result),
        "outro": outro_script(facts),
    }
    if chat is None:
        try:
            chat = get_provider("chat")
        except Exception as error:  # e.g. live mode with a missing setting
            logger.warning("chat provider unavailable (%s); using template scripts", error)
            return list(templates.values())
    provider: ChatLLM = chat

    # Empty log: nothing to sync captions to, so the template's standoff lines are used.
    async def one(kind: Kind) -> Script:
        if kind == "play_by_play" and not result.representative_log:
            return templates[kind]
        return await write_one(kind, provider, facts, result, templates[kind])

    kinds: tuple[Kind, ...] = ("intro", "play_by_play", "outro")
    return list(await asyncio.gather(*(one(kind) for kind in kinds)))
