"""Why did it happen? One-at-a-time sensitivity, then a template sentence (no language model).

For each stat, plus "numbers" and "terrain", we make that one factor equal for both sides,
re-run the fight with the same random seed, and see how much the favorite's results move. The
biggest mover is the deciding factor. Using the same seed for the baseline and each re-run means
a factor that does not matter changes nothing at all, instead of adding noise.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models.matchup import Matchup
from app.models.stats import ASSUMABLE_STATS, StatName, StatSheet
from app.simulation import constants as c
from app.simulation.terrain import modifier

if TYPE_CHECKING:
    from app.simulation.engine import RunOutcome

Simulate = Callable[[Matchup, list[StatSheet], bool, int], "list[RunOutcome]"]
"""simulate(matchup, sheets, use_terrain, runs) -> outcomes, with the seed fixed by the caller."""

# How each stat reads in the explanation: (label, lower-case label, unit).
_STAT_TEXT: dict[StatName, tuple[str, str, str]] = {
    StatName.MASS: ("Size", "its size", " kg"),
    StatName.SIZE: ("Size", "its size", " m"),
    StatName.SPEED: ("Speed", "its speed", " m/s"),
    StatName.ATTACK_FORCE: ("Strength", "its strength", " N"),
    StatName.ATTACK_RATE: ("Attack rate", "its attack rate", " attacks per second"),
    StatName.REACH: ("Reach", "its reach", " m"),
    StatName.ARMOR: ("Armor", "its armor", ""),
    StatName.ENDURANCE: ("Stamina", "its stamina", " s"),
    StatName.AGGRESSION: ("Aggression", "its aggression", ""),
    StatName.GROUP_TACTICS: ("Teamwork", "its teamwork", ""),
}


@dataclass(frozen=True)
class Decision:
    """The deciding factor and the sentence that explains it."""

    factor: "StatName | str"
    explainer: str


def fmt(value: float) -> str:
    """Round a number to 3 significant figures without exponent notation."""
    if value == 0:
        return "0"
    from decimal import Decimal

    text = format(Decimal(f"{value:.3g}"), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _favorite(outcomes: "list[RunOutcome]") -> int:
    wins = [sum(o.winner == s for o in outcomes) for s in (0, 1)]
    return 1 if wins[1] > wins[0] else 0


def _score(outcomes: "list[RunOutcome]", fav: int, count: int) -> tuple[float, float]:
    """The favorite's win share and its average share of fighters left standing."""
    n = len(outcomes)
    won = sum(o.winner == fav for o in outcomes) / n
    left = sum(o.survivors[fav] for o in outcomes) / n / count
    return won, left


def _equalized(sheets: list[StatSheet], name: StatName) -> list[StatSheet] | None:
    """Both sheets with `name` set to the average of the two (None if already equal)."""
    a, b = sheets[0].stats[name], sheets[1].stats[name]
    lows = [s.low if s.low is not None else s.value for s in (a, b)]
    highs = [s.high if s.high is not None else s.value for s in (a, b)]
    if a.value == b.value and lows[0] == lows[1] and highs[0] == highs[1]:
        return None
    update = {
        "value": (a.value + b.value) / 2,
        "low": sum(lows) / 2,
        "high": sum(highs) / 2,
    }
    return [
        sheet.model_copy(
            update={"stats": {**sheet.stats, name: sheet.stats[name].model_copy(update=update)}}
        )
        for sheet in sheets
    ]


def decide(
    matchup: Matchup,
    sheets: list[StatSheet],
    base: "list[RunOutcome]",
    simulate: Simulate,
) -> Decision:
    """Find the deciding factor of a fight whose baseline outcomes are `base`."""
    n = min(c.DECIDING_RUNS, len(base))
    base = base[:n]
    fav = _favorite(base)
    base_won, base_left = _score(base, fav, matchup.fighters[fav].count)
    cache: dict[str, tuple[float, float]] = {}  # factor -> (signed effect, size of effect)

    def effect(factor: str, variant: Matchup, variant_sheets: list[StatSheet], terrain: bool):
        if factor not in cache:
            outcomes = simulate(variant, variant_sheets, terrain, n)
            won, left = _score(outcomes, fav, variant.fighters[fav].count)
            signed = (base_won - won) + c.SURVIVOR_WEIGHT * (base_left - left)
            cache[factor] = (signed, abs(signed))
        return cache[factor]

    for name in StatName:
        variant_sheets = _equalized(sheets, name)
        if variant_sheets is not None:
            effect(name.value, matchup, variant_sheets, True)

    counts = [f.count for f in matchup.fighters]
    if counts[0] != counts[1]:
        even = matchup.model_copy(deep=True)
        for f in even.fighters:
            f.count = min(counts)
        effect("numbers", even, sheets, True)

    mods = [modifier(matchup.terrain, s.habitat) for s in sheets]
    if mods[0] != mods[1]:
        effect("terrain", matchup, sheets, False)

    if not cache:
        return Decision(StatName.MASS, _explain_even())
    factor = max(cache, key=lambda k: cache[k][1])
    signed, size = cache[factor]
    key: StatName | str = StatName(factor) if factor in {s.value for s in StatName} else factor
    wins = [sum(o.winner == side for o in base) for side in (0, 1)]
    if len(base) - wins[0] - wins[1] > max(wins):
        return Decision(key, _explain_stalemate())  # most runs were draws: nobody "won"
    if size < c.MIN_EFFECT:
        return Decision(key, _explain_even())
    return Decision(key, _explain(key, matchup, sheets, fav, signed >= 0))


def _explain_stalemate() -> str:
    return "A stalemate: neither side could finish the other before the time limit."


def _explain_even() -> str:
    return "Too close to call: no single stat or circumstance made a clear difference."


def _explain(
    key: "StatName | str", matchup: Matchup, sheets: list[StatSheet], fav: int, helped: bool
) -> str:
    """A code template; every number comes straight from the stat sheets or the matchup."""
    foe = 1 - fav
    fav_name, foe_name = sheets[fav].display_name, sheets[foe].display_name
    counts = (matchup.fighters[fav].count, matchup.fighters[foe].count)

    if key == "numbers":
        return (
            f"Numbers decided it: {counts[0]} {fav_name} against {counts[1]} {foe_name}. "
            "A crowd can wear down even a tougher fighter, and a lone fighter can only face "
            "so many at once."
        )
    if key == "terrain":
        terrain = matchup.terrain.value.replace("_", " ")
        who = fav_name if helped else foe_name
        return (
            f"The ground decided it: the {terrain} suits the {who} "
            f"({sheets[fav if helped else foe].habitat.value} mover) better."
        )

    label, lower, unit = _STAT_TEXT[key]
    vf = fmt(sheets[fav].stats[key].value)
    vo = fmt(sheets[foe].stats[key].value)
    pair = f"{fav_name} ({vf}{unit}) against {foe_name} ({vo}{unit})"
    if helped:
        text = f"{label} decided it: {pair}."
    else:
        text = f"{fav_name} came out ahead in spite of {lower}: {pair}."
    if key in ASSUMABLE_STATS:
        text += " This rests on an assumption: behavior and armor are judgments, not measurements."
    return text
