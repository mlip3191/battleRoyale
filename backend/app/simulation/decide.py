"""Why did it happen? One-at-a-time sensitivity, then a template sentence (no language model).

For each stat, plus "numbers" and "terrain", we make that one factor equal for both sides,
re-run the fight with the same random seed, and see how much the favorite's results move. The
biggest mover is the deciding factor. Using the same seed for the baseline and each re-run means
a factor that does not matter changes nothing at all, instead of adding noise.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.matchup import Matchup
from app.models.stats import ASSUMABLE_STATS, StatName, StatSheet
from app.simulation import constants as c
from app.simulation.fighters import effective_habitat, venom_resistance
from app.simulation.terrain import modifier

if TYPE_CHECKING:
    from app.simulation.engine import RunOutcome

Simulate = Callable[..., "list[RunOutcome]"]
"""simulate(matchup, sheets, use_terrain, runs, scaled=True) -> outcomes.

The seed is fixed by the caller; `scaled=False` drops any size-reference scaling.
"""

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
    scales: tuple[float, float] = (1.0, 1.0),
) -> Decision:
    """Find the deciding factor of a fight whose baseline outcomes are `base`."""
    n = min(c.DECIDING_RUNS, len(base))
    base = base[:n]
    fav = _favorite(base)
    base_won, base_left = _score(base, fav, matchup.fighters[fav].count)
    cache: dict[str, tuple[float, float]] = {}  # factor -> (signed effect, size of effect)

    def effect(
        factor: str,
        variant: Matchup,
        variant_sheets: list[StatSheet],
        terrain: bool,
        scaled: bool = True,
    ) -> tuple[float, float]:
        if factor not in cache:
            outcomes = simulate(variant, variant_sheets, terrain, n, scaled)
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

    if scales != (1.0, 1.0):
        # A size reference ('horse-sized duck') matters on its own: drop the scaling and re-run.
        effect("scaling", matchup, sheets, True, scaled=False)

    mods = [modifier(matchup.terrain, effective_habitat(s)) for s in sheets]
    if mods[0] != mods[1]:
        effect("terrain", matchup, sheets, False)

    if any(s.lore and s.lore.abilities for s in sheets):
        effect("abilities", matchup, [_without_abilities(s) for s in sheets], True)

    if any("venom" in s.weapons for s in sheets):
        effect("venom", matchup, [_without_venom(s) for s in sheets], True)
        if any(venom_resistance(s) > 0 for s in sheets):
            effect("resistance", matchup, [_without_resistance(s) for s in sheets], True)

    # When nothing mattered (or the fight was a stalemate), the factor named below is only a
    # placeholder: the UI and the announcer must rely on the explainer text, not the factor name.
    if not cache:
        return Decision(StatName.MASS, _explain_even())
    factor = max(cache, key=lambda k: cache[k][1])
    signed, size = cache[factor]
    stat_names = {s.value for s in StatName}
    key: StatName | str = StatName(factor) if factor in stat_names else factor
    # Scaling is reported as size; venom and resistance as attack force (D-44: no new contract
    # value), with the sentence naming venom or resistance.
    shown = {"scaling": StatName.MASS, "venom": StatName.ATTACK_FORCE}.get(factor, key)
    if factor == "resistance":
        shown = StatName.ATTACK_FORCE
    wins = [sum(o.winner == side for o in base) for side in (0, 1)]
    draws_from_venom = factor in ("venom", "resistance")  # a poisoned survivor makes a draw
    if len(base) - wins[0] - wins[1] > max(wins) and not draws_from_venom:
        return Decision(shown, _explain_stalemate())  # most runs were draws: nobody "won"
    if size < c.MIN_EFFECT:
        if base_won >= 0.9:
            return Decision(shown, _explain_comfortable(sheets[fav].display_name))
        return Decision(shown, _explain_even())
    return Decision(shown, _explain(key, matchup, sheets, fav, signed >= 0))


def _explain_scaling(matchup: Matchup, sheets: list[StatSheet], fav: int, helped: bool) -> str:
    """Size decided it because of the size references; quotes only sheet values and counts."""

    def side(i: int) -> str:
        fighter, sheet = matchup.fighters[i], sheets[i]
        mass = fmt(sheet.stats[StatName.MASS].value)
        crowd = f"{fighter.count} " if fighter.count > 1 else ""
        if fighter.size_reference:
            return (
                f"{crowd}{sheet.display_name} ({mass} kg normally, "
                f"scaled to {fighter.size_reference} size)"
            )
        return f"{crowd}{sheet.display_name} ({mass} kg)"

    pair = f"{side(fav)} against {side(1 - fav)}"
    if helped:
        return f"Size decided it: after scaling, {pair}."
    return f"{sheets[fav].display_name} came out ahead in spite of the scaling: {pair}."


def _without_abilities(sheet: StatSheet) -> StatSheet:
    """The same fighter with every legendary power removed (for the sensitivity check)."""
    if sheet.lore is None or not sheet.lore.abilities:
        return sheet
    lore = sheet.lore.model_copy(update={"abilities": [], "heads": None})
    return sheet.model_copy(update={"lore": lore})


def _without_venom(sheet: StatSheet) -> StatSheet:
    """The same fighter with its venom removed (for the sensitivity check)."""
    if "venom" not in sheet.weapons:
        return sheet
    weapons = [w for w in sheet.weapons if w != "venom"] or ["teeth"]
    return sheet.model_copy(update={"weapons": weapons})


def _without_resistance(sheet: StatSheet) -> StatSheet:
    """The same fighter with no venom resistance (a fighter id the table does not list)."""
    if venom_resistance(sheet) == 0:
        return sheet
    return sheet.model_copy(update={"fighter_id": "unresisted"})


def _explain_stalemate() -> str:
    return "A stalemate: neither side could finish the other before the time limit."


def _explain_comfortable(fav_name: str) -> str:
    return f"{fav_name} wins comfortably: no single stat or circumstance was decisive."


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
        pair = f"{counts[0]} {fav_name} against {counts[1]} {foe_name}"
        if not helped:
            return (
                f"{fav_name} came out ahead in spite of the head count: {pair}. "
                "A crowd can wear down even a tougher fighter, but here it was not enough."
            )
        return (
            f"Numbers decided it: {pair}. "
            "A crowd can wear down even a tougher fighter, and a lone fighter can only face "
            "so many at once."
        )
    if key == "venom":
        biter = next(i for i in (fav, foe) if "venom" in sheets[i].weapons)
        if biter == fav or not helped:
            return (
                f"{sheets[biter].display_name}'s venom decided it: a poisoned survivor dies "
                "minutes after the fight, so a fighter can lose the brawl and still take its "
                "foe with it."
            )
        return f"{fav_name} came out ahead in spite of {foe_name}'s venom."
    if key == "resistance":
        holder = next(i for i in (fav, foe) if venom_resistance(sheets[i]) > 0)
        who = sheets[holder].display_name
        if holder == fav:
            return (
                f"{who}'s venom resistance decided it: it shrugs off bites that would kill others."
            )
        return f"{fav_name} came out ahead in spite of {who}'s venom resistance."
    if key == "abilities":
        owner = fav if helped else foe
        powers = sheets[owner].lore.abilities if sheets[owner].lore else []
        names = ", ".join(p.value.replace("_", " ") for p in powers)
        if helped:
            return f"Legendary powers decided it: according to legend, {fav_name} has {names}."
        return (
            f"{fav_name} came out ahead in spite of {foe_name}'s legendary powers "
            f"(according to legend: {names})."
        )
    if key == "scaling":
        return _explain_scaling(matchup, sheets, fav, helped)
    if key == "terrain":
        terrain = matchup.terrain.value.replace("_", " ")
        if not helped:
            mover = effective_habitat(sheets[foe]).value
            return (
                f"{fav_name} came out ahead in spite of the ground: the {terrain} suits "
                f"the {foe_name} ({mover} mover) better."
            )
        mover = effective_habitat(sheets[fav]).value
        return f"The ground decided it: the {terrain} suits the {fav_name} ({mover} mover) better."

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
