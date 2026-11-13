"""Template scripts that need no language model: intro, play-by-play, and outro.

Every number is filled in by code from NarrationFacts, and every line that can carry a number
(intro, play-by-play, and outro) is run through the number guard, falling back to a number-free
stand-in if it fails. Play-by-play lines also carry the engine's text_hint, which the same guard
checks. Every Script comes back with fallback=True.
"""

import re
from collections.abc import Sequence
from decimal import Decimal

from app.models.narration import Script, ScriptLine
from app.models.simulation import EventType, FightEvent, SimulationResult
from app.narration.facts import FACTOR_WORDS, KG_TO_LB, MPS_TO_KMH, FighterFacts, NarrationFacts
from app.narration.number_guard import AllowedNumbers, find_unsupported_numbers
from app.text import PROPER_FIRST_WORDS as PROPER_FIRST_WORDS  # shared since #258
from app.text import counted_name

MAX_LINE = 200
MAX_HINT = 60
MIN_BEATS = 8
MAX_BEATS = 20
# Stands in for a fighter's name while the number guard reads a line ("Three-toed sloth").
NAME_MASK = "Fighter"

# Events worth keeping when a long log is cut down to the beat limit.
KEY_EVENTS = {EventType.KO, EventType.FLEE, EventType.RETREAT, EventType.STALEMATE, EventType.END}

# Deadpan reactions for when a short log means an event is mentioned again.
REACTIONS = (
    "Let's look at that one again, folks.",
    "I have seen a lot of fights. I have not seen that.",
    "Textbook. Absolute textbook.",
    "The crowd does not know what to do with itself.",
    "You cannot teach that. You simply cannot.",
    "Somewhere a nature documentary just got jealous.",
    "Hold on to your popcorn.",
)


# A number as an announcer says it: thousands separators, at most one decimal, small values kept.
def fmt(value: float) -> str:
    """6000 -> "6,000"; 43.2 -> "43.2"; 1.0 -> "1"; 0.04 -> "0.04"; 2.5e-6 -> "0.0000025"."""
    if abs(value) >= 100:
        return f"{round(value):,}"
    if 0 < abs(value) < 1:
        return format(Decimal(f"{value:.2g}"), "f")
    return f"{value:.1f}".rstrip("0").rstrip(".")


# Keep a line within the limit: shorten the fighters' names first, so the sentence stays whole.
def fit(text: str, names: Sequence[str] = ()) -> str:
    """Text within MAX_LINE: drop trailing words of long names, then cut at a word boundary."""
    for name in names:
        while len(text) > MAX_LINE and name in text and " " in name:
            short = name.rsplit(" ", 1)[0].rstrip(" -")
            text, name = text.replace(name, short), short
    if len(text) <= MAX_LINE:
        return text
    return text[: MAX_LINE - 1].rsplit(" ", 1)[0] + "…"


# One script line, length-checked.
def line(
    speaker: str, text: str, at_event: int | None = None, names: Sequence[str] = ()
) -> ScriptLine:
    """A ScriptLine within the length limit (names are shortened first if it is too long)."""
    text = fit(text, names)
    return ScriptLine.model_validate({"speaker": speaker, "text": text, "at_event": at_event})


# Hide the fighters' names from the number guard, so "Three-toed sloth" is not read as 3 (#259).
def mask_names(text: str, names: Sequence[str]) -> str:
    """Replace each name and its plural, in any case, with NAME_MASK; other words are untouched."""
    forms = {form for name in names if name for form in (name, plural(name))}
    for form in sorted(forms, key=len, reverse=True):  # longer forms first (plural before singular)
        pattern = rf"(?<!\w){re.escape(form)}(?!\w)"
        text = re.sub(pattern, NAME_MASK, text, flags=re.IGNORECASE)
    return text


# The text if every number in it is allowed (fighters' names aside); otherwise the safe stand-in.
def guarded(text: str, safe: str, allowed: AllowedNumbers, names: Sequence[str] = ()) -> str:
    """Run a built line through the number guard; fall back to `safe` if it fails."""
    return safe if find_unsupported_numbers(mask_names(text, names), allowed) else text


# A guarded, length-checked line: the text if its numbers pass, otherwise the number-free stand-in.
def safe_line(
    speaker: str, text: str, safe: str, facts: NarrationFacts, names: Sequence[str] = ()
) -> ScriptLine:
    """A ScriptLine whose numbers all pass the guard (`safe` must contain no numbers).
    The fighters' names in `facts` are always masked for the guard, plus any extra `names`."""
    masked = [*(f.display_name for f in facts.fighters), *names]
    return line(speaker, guarded(text, safe, facts.allowed, masked), names=names)


# How a side is named in the broadcast, with its count when more than one fights.
def team_name(f: FighterFacts) -> str:
    """ "Dragon" or "Gray wolf, 6 of them" (or "1,000 of them")."""
    return f"{f.display_name}, {f.count:,} of them" if f.count > 1 else f.display_name


# The tale-of-the-tape line: mass and top speed, flagged as legend or estimate.
def tape_line(f: FighterFacts) -> str:
    """One line of stats for a fighter, with the honesty labels the number rule needs."""
    return _tape(f, _tape_body(f))


# The tape line with no stats at all, used when the real one fails the number guard.
def safe_tape_line(f: FighterFacts) -> str:
    """ "Gray wolf keeps its numbers to itself." (legend wording kept for mythical fighters)."""
    return _tape(f, "keeps its numbers to itself")


# Wrap a tape body in the fighter's name, with the legend label when it applies.
def _tape(f: FighterFacts, body: str) -> str:
    if f.is_legend:
        return f"{f.display_name}, according to legend, {body}. Legend numbers are estimates."
    return f"{f.display_name} {body}."


# The stats part of a tape line: mass and top speed, each flagged when it is an estimate.
def _tape_body(f: FighterFacts) -> str:
    mass, speed = f.stat("mass_kg"), f.stat("top_speed_mps")
    parts = []
    if mass is not None:
        est = "an estimated " if mass.is_estimate else ""
        lb = fmt(mass.value * KG_TO_LB) if mass.unit == "kg" else None
        lb_text = f" ({lb} pounds)" if lb else ""
        parts.append(f"weighs in at {est}{fmt(mass.value)} {_unit(mass.unit)}{lb_text}")
    if speed is not None and speed.value == 0:
        parts.append("does not move. At all")
    elif speed is not None:
        est = "an estimated " if speed.is_estimate else ""
        kmh = fmt(speed.value * MPS_TO_KMH) if speed.unit == "m/s" else fmt(speed.value)
        unit = "km/h" if speed.unit == "m/s" else _unit(speed.unit)
        parts.append(f"tops out at {est}{kmh} {unit}")
    return " and ".join(parts) if parts else "keeps its numbers to itself"


# Spoken name for a stored unit.
def _unit(unit: str) -> str:
    return {"kg": "kilograms", "m": "meters", "m/s": "meters per second", "s": "seconds"}.get(
        unit, unit
    )


def intro_script(facts: NarrationFacts) -> Script:
    """The intro: 4 to 8 lines about who is fighting, grounded only in the stat sheets."""
    red, blue = facts.fighters
    names = [red.display_name, blue.display_name]
    red_in, blue_in = "In the red corner: {}!", "And in the blue corner: {}!"
    lines = [
        line("announcer", "Good evening, fight fans, and welcome to Battle Royale!"),
        safe_line(
            "announcer",
            red_in.format(team_name(red)),
            red_in.format(red.display_name),
            facts,
            names,
        ),
        safe_line("color_commentator", tape_line(red), safe_tape_line(red), facts, names),
        safe_line(
            "announcer",
            blue_in.format(team_name(blue)),
            blue_in.format(blue.display_name),
            facts,
            names,
        ),
        safe_line("color_commentator", tape_line(blue), safe_tape_line(blue), facts, names),
    ]
    if red.body == "inert" or blue.body == "inert":
        lines.append(line("color_commentator", "Yes, it is an object. We take it seriously."))
    lines.append(line("announcer", "The science is in. The simulation has spoken. Let's fight!"))
    return Script(kind="intro", lines=lines, fallback=True)


# Choose which events get a beat: all of a short log, or key moments plus an even spread.
def pick_events(log: list[FightEvent]) -> list[int]:
    """Event indices to narrate, in order; repeats fill a log shorter than MIN_BEATS."""
    n = len(log)
    if n == 0:
        return []
    if n <= MAX_BEATS:
        chosen = list(range(n))
    else:
        keep = {0, n - 1} | {i for i, e in enumerate(log) if e.type in KEY_EVENTS}
        keep = set(sorted(keep, key=lambda i: (i not in (0, n - 1), i))[:MAX_BEATS])
        step = n / MAX_BEATS
        for k in range(MAX_BEATS):
            if len(keep) >= MAX_BEATS:
                break
            keep.add(int(k * step))
        chosen = sorted(keep)
    extra = [chosen[i % len(chosen)] for i in range(max(0, MIN_BEATS - len(chosen)))]
    return sorted(chosen + extra)


# A short neutral hint from the engine, kept to letters and spaces and at most MAX_HINT long.
def _hint(event: FightEvent, default: str, use_hint: bool) -> str:
    cleaned = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]", " ", event.text_hint)).strip()
    if len(cleaned) > MAX_HINT:
        head = cleaned[: MAX_HINT + 1]
        cleaned = head.rsplit(" ", 1)[0] if " " in head else head[:MAX_HINT]
    return cleaned if cleaned and use_hint else default


# One play-by-play line for an event.
def beat_text(event: FightEvent, facts: NarrationFacts, use_hint: bool = True) -> str:
    """What the announcer says about one event (PG: knockouts and retreats, no gore)."""
    f = facts.fighters[event.side]
    who = (
        f"{f.display_name}, all {event.group_size:,} of them,"
        if event.group_size > 1
        else f.display_name
    )
    match event.type:
        case EventType.APPROACH:
            return f"{who} closes in. Here we go!"
        case EventType.ATTACK:
            return f"{who} goes on the attack: {_hint(event, 'here it comes', use_hint)}!"
        case EventType.HIT:
            return f"{who} connects: {_hint(event, 'a solid hit', use_hint)}! That one landed!"
        case EventType.MISS:
            return f"{who} swings and misses: {_hint(event, 'nothing but air', use_hint)}."
        case EventType.KO:
            return f"{who} goes down! That is a knockout!"
        case EventType.RETREAT:
            return f"{who} backs off to catch a breath."
        case EventType.FLEE:
            return f"{who} has seen enough and heads for the exit!"
        case EventType.STALEMATE:
            return "Nobody is giving an inch. We have a stalemate!"
        case _:
            return "And that is the fight!"


def play_by_play_script(facts: NarrationFacts, result: SimulationResult) -> Script:
    """Play-by-play: 8 to 20 beats, each pointing at a real event in the representative log."""
    log = result.representative_log
    lines: list[ScriptLine] = []
    seen: set[int] = set()
    names = [f.display_name for f in facts.fighters]
    for n, idx in enumerate(pick_events(log)):
        if idx in seen:
            text = REACTIONS[len(lines) % len(REACTIONS)]
            lines.append(line("color_commentator", text, idx))
            continue
        seen.add(idx)
        speaker = "announcer" if n % 3 != 2 else "color_commentator"
        safe = beat_text(log[idx], facts, use_hint=False)
        text = guarded(beat_text(log[idx], facts), safe, facts.allowed, names)
        lines.append(line(speaker, text, idx, names))
    if not lines:  # no events at all: the sides never engaged, so nothing to sync to
        standoff = ["They size each other up.", "Nobody moves.", "Still nobody moves."]
        lines = [line("announcer", standoff[i % 3]) for i in range(MIN_BEATS)]
    return Script(kind="play_by_play", lines=lines, fallback=True)


# The fair-fight line: the count that makes it a coin flip, "none found", or "not run tonight".
def fair_fight_line(facts: NarrationFacts, names: Sequence[str] = ()) -> ScriptLine:
    """Never claims "no count makes this fair" unless the fair-fight check actually ran."""
    safe = "Want a fair fight? We have a count that makes it a coin flip."
    if facts.fair_count is not None and facts.fair_side is not None:
        if facts.fair_win_pct is None:  # a count with no probability: never say "None%"
            return safe_line("color_commentator", safe, safe, facts)
        count = facts.fair_count
        varied = counted_name(facts.fighters[facts.fair_side].display_name, count)
        verb = "makes" if count == 1 else "make"
        text = (
            f"Want a fair fight? About {count} {varied} {verb} it a coin flip, "
            f"winning {facts.fair_win_pct}% of the time."
        )
        return safe_line("color_commentator", text, safe, facts, names)
    if facts.fair_ran:
        text = "Want a fair fight? No count makes this one fair."
    else:
        text = "Want a fair fight? We didn't run the fair-fight check tonight."
    return safe_line("color_commentator", text, text, facts)


def outro_script(facts: NarrationFacts) -> Script:
    """The outro: verdict, win percentage, deciding factor, and the fair-fight line."""
    red, blue = facts.fighters
    names = [red.display_name, blue.display_name]
    factor = FACTOR_WORDS.get(facts.deciding_factor, facts.deciding_factor.replace("_", " "))
    if facts.outcome in ("win_0", "win_1"):
        side = 0 if facts.outcome == "win_0" else 1
        winner = facts.fighters[side]
        won = (
            f"{winner.display_name} won {facts.win_pct[side]}% of {facts.runs:,} simulated fights."
        )
        lines = [
            safe_line(
                "announcer",
                f"Your winner: {team_name(winner)}!",
                f"Your winner: {winner.display_name}!",
                facts,
                names,
            ),
            safe_line(
                "color_commentator", won, f"{winner.display_name} takes the win.", facts, names
            ),
        ]
    elif facts.outcome == "draw":
        lines = [
            line("announcer", "It's a draw! Nobody takes the belt tonight!"),
            safe_line(
                "color_commentator",
                f"{facts.draw_pct}% of simulated fights ended even.",
                "Plenty of simulated fights ended even.",
                facts,
            ),
        ]
    else:
        lines = [
            line("announcer", "No contest! These two never even met."),
            safe_line(
                "color_commentator",
                f"{names[0]} and {names[1]} cannot engage.",
                "These two cannot engage.",
                facts,
                names,
            ),
        ]
    lines.append(
        safe_line(
            "announcer",
            f"The deciding factor: {factor}.",
            "The deciding factor: the science.",
            facts,
        )
    )
    lines.append(fair_fight_line(facts, names))
    lines.append(line("announcer", "That's all from the arena. Good night, everybody!"))
    return Script(kind="outro", lines=lines, fallback=True)


def template_scripts(facts: NarrationFacts, result: SimulationResult) -> list[Script]:
    """All three template scripts, in broadcast order, each with fallback=True."""
    return [intro_script(facts), play_by_play_script(facts, result), outro_script(facts)]
