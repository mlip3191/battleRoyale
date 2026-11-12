"""The compact fact list a script is written from, and the numbers a script may say.

Everything here comes from the stat sheets, the simulation result, and the fair-fight result,
never from the user's raw text. Names use the stat sheet's display_name, re-checked against the
allowlist (letters, digits, spaces, hyphens; ARCHITECTURE "Security").

Side counts: SimulationResult has no per-side fighter count, so `counts` is an optional argument
(from the Matchup); without it, a side's count is the largest group_size seen in the log.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.models.simulation import FairFight, SimulationResult
from app.models.stats import SAFE_NAME, StatSheet
from app.narration.number_guard import AllowedNumbers

MAX_NAME_LEN = 60

# Unit conversions a script may use: stored unit -> factors to other units.
KG_TO_LB = 2.20462
M_TO_FT = 3.28084
MPS_TO_KMH = 3.6
MPS_TO_MPH = 2.23694
CONVERSIONS: dict[str, tuple[float, ...]] = {
    "kg": (KG_TO_LB, 0.001),  # pounds, tonnes
    "m": (M_TO_FT,),  # feet
    "m/s": (MPS_TO_KMH, MPS_TO_MPH),  # km/h, mph
    "s": (1 / 60,),  # minutes
    "N": (0.001,),  # kilonewtons
}

# Rubric stats on a 0-1 scale are assumptions, not measurements or probabilities.
RUBRIC_UNIT = "0-1"

# Plain words for a deciding factor (matches #218's templates).
FACTOR_WORDS = {
    "mass_kg": "sheer mass",
    "size_m": "size",
    "top_speed_mps": "speed",
    "attack_force_n": "hitting power",
    "attacks_per_s": "attack rate",
    "reach_m": "reach",
    "armor_0_1": "armor",
    "endurance_s": "endurance",
    "aggression_0_1": "aggression",
    "group_tactics_0_1": "teamwork",
    "numbers": "numbers",
    "terrain": "the terrain",
    "habitat": "habitat",
    "abilities": "special abilities",
}

# Plain labels for stat names in the fact list.
STAT_WORDS = {
    "mass_kg": "mass",
    "size_m": "size",
    "top_speed_mps": "top speed",
    "attack_force_n": "attack force",
    "attacks_per_s": "attack rate",
    "reach_m": "reach",
    "armor_0_1": "armor",
    "endurance_s": "endurance",
    "aggression_0_1": "aggression",
    "group_tactics_0_1": "teamwork",
}


@dataclass(frozen=True)
class StatFact:
    """One stat as the announcer may quote it."""

    name: str
    value: float
    unit: str
    is_estimate: bool


@dataclass(frozen=True)
class FighterFacts:
    """One side: who it is and its stats."""

    side: int
    display_name: str
    category: str
    body: str
    has_lore: bool
    count: int
    stats: tuple[StatFact, ...]

    @property
    def is_legend(self) -> bool:
        """Mythical fighters' stats are introduced as legend."""
        return self.category == "mythical" or self.has_lore

    def stat(self, name: str) -> StatFact | None:
        """The stat with this name, if the sheet has it."""
        return next((s for s in self.stats if s.name == name), None)


@dataclass(frozen=True)
class NarrationFacts:
    """Everything a script may mention, plus the numbers it may say."""

    fighters: tuple[FighterFacts, ...]
    runs: int
    win_pct: tuple[int, int]
    draw_pct: int
    outcome: str
    deciding_factor: str
    mean_duration_s: float
    mean_survivors: tuple[float, float]
    fair_ran: bool
    fair_count: int | None
    fair_win_pct: int | None
    fair_side: int | None
    allowed: AllowedNumbers


def safe_name(name: str, side: int) -> str:
    """The name if it passes the allowlist; otherwise a cleaned version or a neutral stand-in."""
    if len(name) <= MAX_NAME_LEN and SAFE_NAME.fullmatch(name):
        return name
    cleaned = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 -]", " ", name)).strip(" -")
    cleaned = cleaned[:MAX_NAME_LEN].strip(" -")
    if cleaned and SAFE_NAME.fullmatch(cleaned):
        return cleaned
    return "Red corner fighter" if side == 0 else "Blue corner fighter"


# A number and its usual roundings: 1 and 2 decimals always; whole numbers only from 10 up (so
# 2.4 m does not allow "2"); 2 and 3 significant figures from 100 up; 2 significant figures under 1.
# A non-zero value never rounds to 0, so "weighs 0 kilograms" is never allowed.
def _roundings(x: float) -> set[float]:
    out = {x, round(x, 1), round(x, 2)}
    if abs(x) >= 10:
        out.add(round(x))
    if abs(x) >= 100:
        out |= {float(f"{x:.2g}"), float(f"{x:.3g}")}
    if 0 < abs(x) < 1:
        out.add(float(f"{x:.2g}"))
    return {float(v) for v in out if v or not x}


# Every way a stat value may be said: as stored, converted, and rounded.
def _stat_numbers(value: float, unit: str) -> set[float]:
    out = _roundings(value)
    for factor in CONVERSIONS.get(unit, ()):
        out |= _roundings(value * factor)
    return out


# A probability as a whole-number percentage.
def pct(p: float) -> int:
    """0.38 -> 38."""
    return round(p * 100)


# Odds ratios a script may quote ("about three to two") from a pair of win probabilities.
def _odds(probs: Sequence[float]) -> set[float]:
    out = {p / (1 - p) for p in probs if 0 < p < 1} | {(1 - p) / p for p in probs if 0 < p < 1}
    if len(probs) == 2 and all(p > 0 for p in probs):
        out |= {probs[0] / probs[1], probs[1] / probs[0]}
    return out


# Largest group of fighters that acted together for each side in the representative fight.
def _max_group(result: SimulationResult) -> tuple[int, int]:
    sizes = [1, 1]
    for event in result.representative_log:
        sizes[event.side] = max(sizes[event.side], event.group_size)
    return sizes[0], sizes[1]


# The facts for one side, with a safe name and the count to announce.
def _fighter(sheet: StatSheet, side: int, count: int) -> FighterFacts:
    stats = tuple(
        StatFact(str(name), stat.value, stat.unit, stat.is_estimate)
        for name, stat in sheet.stats.items()
    )
    return FighterFacts(
        side=side,
        display_name=safe_name(sheet.display_name, side),
        category=sheet.category,
        body=str(sheet.body),
        has_lore=sheet.lore is not None,
        count=count,
        stats=stats,
    )


# Every number the scripts may say, built from the same inputs as the facts.
def _allowed(
    sheets: Sequence[StatSheet],
    result: SimulationResult,
    fair: FairFight | None,
    facts_counts: Sequence[int],
) -> AllowedNumbers:
    values: set[float] = set()
    percents: set[float] = set()
    for side, sheet in enumerate(sheets):
        # Digits from the name the fact list shows, not the raw one.
        values |= {float(d) for d in re.findall(r"\d+", safe_name(sheet.display_name, side))}
        # Only sourced values: no code-made sampling bounds, and rubric stats never as percents.
        for stat in sheet.stats.values():
            values |= _stat_numbers(stat.value, stat.unit)
    # Percentages come only from real probabilities.
    probs = [*result.win_prob, result.draw_prob, *(b for ci in result.win_prob_ci95 for b in ci)]
    for p in probs:
        values |= _roundings(p)
        percents |= _roundings(p * 100)
    values |= _stat_numbers(result.mean_duration_s, "s")
    values |= {float(result.runs)} | {float(c) for c in facts_counts}
    values |= {float(e.group_size) for e in result.representative_log}
    for survivors in result.mean_survivors:
        values |= _roundings(survivors)
    odds = _odds(result.win_prob)
    # The fair fight counts only when it found a count, the same rule build_facts uses.
    if fair is not None and fair.count is not None:
        values.add(float(fair.count))
    if fair is not None and fair.count is not None and fair.win_prob_at_count is not None:
        values |= _roundings(fair.win_prob_at_count)
        percents |= _roundings(fair.win_prob_at_count * 100)
        odds |= _odds([fair.win_prob_at_count])
    return AllowedNumbers(frozenset(values), frozenset(percents), frozenset(odds))


def build_facts(
    sheets: Sequence[StatSheet],
    result: SimulationResult,
    fair_fight: FairFight | None = None,
    counts: Sequence[int] | None = None,
) -> NarrationFacts:
    """The compact fact list for the two sides of a battle (side 0 first)."""
    if len(sheets) != 2:
        raise ValueError("narration needs exactly two stat sheets, side 0 first")
    side_counts = tuple(counts) if counts is not None else _max_group(result)
    fighters = tuple(_fighter(s, i, side_counts[i]) for i, s in enumerate(sheets))
    has_fair = fair_fight is not None and fair_fight.count is not None
    fair_p = fair_fight.win_prob_at_count if fair_fight is not None else None
    return NarrationFacts(
        fighters=fighters,
        runs=result.runs,
        win_pct=(pct(result.win_prob[0]), pct(result.win_prob[1])),
        draw_pct=pct(result.draw_prob),
        outcome=result.outcome,
        deciding_factor=str(result.deciding_factor),
        mean_duration_s=result.mean_duration_s,
        mean_survivors=result.mean_survivors,
        fair_ran=fair_fight is not None,
        fair_count=fair_fight.count if has_fair and fair_fight is not None else None,
        fair_win_pct=pct(fair_p) if has_fair and fair_p is not None else None,
        fair_side=fair_fight.varied_side if has_fair and fair_fight is not None else None,
        allowed=_allowed(sheets, result, fair_fight, side_counts),
    )


def fact_lines(facts: NarrationFacts) -> list[str]:
    """The fact list as short text lines, for a prompt (part 2) or for debugging."""
    names = [f.display_name for f in facts.fighters]
    lines = []
    for f in facts.fighters:
        legend = ", according to legend" if f.is_legend else ""
        lines.append(f"{f.display_name} x{f.count} ({f.category}, {f.body}{legend})")
        for s in f.stats:
            lines.append(f"  {f.display_name} {STAT_WORDS.get(s.name, s.name)}: {_stat_text(s)}")
    factor = FACTOR_WORDS.get(facts.deciding_factor, facts.deciding_factor.replace("_", " "))
    lines.append(
        f"result: {_outcome_text(facts.outcome, names)}; "
        f"{names[0]} wins {facts.win_pct[0]}%, {names[1]} wins {facts.win_pct[1]}%, "
        f"draw {facts.draw_pct}%, {facts.runs} runs; deciding factor: {factor}; "
        f"mean duration {facts.mean_duration_s:g} s"
    )
    if facts.fair_count is not None and facts.fair_side is not None:
        # A count without a probability still names the count, never "None%".
        fair = f"fair fight: {names[facts.fair_side]} x{facts.fair_count}"
        if facts.fair_win_pct is not None:
            fair += f" wins {facts.fair_win_pct}% of the time"
        lines.append(fair)
    elif facts.fair_ran:
        lines.append("fair fight: checked, and no count makes this one fair")
    return lines


# A stat's value and unit, tagged as an assumption (0-1 rubric) or an estimate.
def _stat_text(s: StatFact) -> str:
    if s.unit == RUBRIC_UNIT:
        return f"{s.value:g} on a 0-1 scale (assumption)"
    estimate = " (estimate)" if s.is_estimate else ""
    return f"{s.value:g} {s.unit}{estimate}"


# The outcome in plain words, using display names instead of side numbers.
def _outcome_text(outcome: str, names: Sequence[str]) -> str:
    if outcome.startswith("win_"):
        return f"{names[int(outcome[-1])]} wins"
    return outcome.replace("_", " ")
