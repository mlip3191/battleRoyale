"""Loadouts: one choice per fighter that leans a direction and costs something elsewhere (#283).

A loadout is plain data (see `LOADOUTS` in constants.py). `apply_loadout` returns a copy of a stat
sheet with its attack force, attack rate, top speed and armor changed by code, before the engine
runs; the engine itself knows nothing about loadouts, so results stay a pure function of the sheets.

The number rule: the multipliers are assumptions, not sourced facts, and every changed stat says
so. Attack force, attack rate and speed become `derived` (computed by code from the sheet's own
value and the loadout's multiplier, with the base value in the note); armor becomes an
`assumption`, as the sheet rules require for a behavioral stat. A loadout with a firearm,
explosive or modern vehicle is not offered here: D-07 and D-38 block those as fighters.
"""

from dataclasses import dataclass

from app.models.stats import StatName, StatSheet, StatValue
from app.research.sheet_hash import compute_sheet_hash
from app.simulation import constants as c


@dataclass(frozen=True)
class Loadout:
    """One loadout's data, read from `constants.LOADOUTS`."""

    id: str
    lean: str  # attack, defense, speed or balanced
    label: str  # shown to the user and used in narration
    force_mul: float
    rate_mul: float
    speed_mul: float
    armor_add: float


def loadout(loadout_id: str) -> Loadout:
    """The loadout with this id (a KeyError names the known ones)."""
    if loadout_id not in c.LOADOUTS:
        raise KeyError(f"unknown loadout {loadout_id!r}; known: {', '.join(sorted(c.LOADOUTS))}")
    data = c.LOADOUTS[loadout_id]
    return Loadout(
        id=loadout_id,
        lean=loadout_id,
        label=str(data["label"]),
        force_mul=float(data["force_mul"]),
        rate_mul=float(data["rate_mul"]),
        speed_mul=float(data["speed_mul"]),
        armor_add=float(data["armor_add"]),
    )


def all_loadouts() -> list[Loadout]:
    return [loadout(loadout_id) for loadout_id in c.LOADOUTS]


def _scaled(stat: StatValue, factor: float, why: str) -> StatValue:
    """A copy of a stat multiplied by `factor` (the range scales with it).

    A sourced stat becomes `derived` (code computed it from the sheet's value and the multiplier);
    an estimate stays the estimate it was.
    """
    data = stat.model_dump()
    data["value"] = stat.value * factor
    data["low"] = None if stat.low is None else stat.low * factor
    data["high"] = None if stat.high is None else stat.high * factor
    note = (
        f"{why}: base {stat.value:g} {stat.unit} times {factor:g} (the multiplier is an "
        "assumption, not a sourced figure)"
    )
    if stat.is_estimate:
        # A number computed from an estimate is still an estimate: keep its method and low
        # confidence so the sheet's estimate count and the number rule stay honest.
        data.update(note=note)
    else:
        data.update(method="derived", source=None, note=note)
    return StatValue.model_validate(data)


def _armor_with(stat: StatValue, add: float, why: str) -> StatValue:
    """An armor value moved by `add` and kept within 0 to 1, labeled an assumption."""
    clip = lambda x: min(max(x, 0.0), 1.0)  # noqa: E731
    data = stat.model_dump()
    data["value"] = clip(stat.value + add)
    data["low"] = None if stat.low is None else clip(stat.low + add)
    data["high"] = None if stat.high is None else clip(stat.high + add)
    data.update(
        method="assumption",
        is_estimate=True,
        source=None,
        confidence="low",
        note=f"{why}: base {stat.value:g} plus {add:g}, an assumption, not a sourced figure",
    )
    return StatValue.model_validate(data)


def apply_loadout(sheet: StatSheet, chosen: Loadout) -> StatSheet:
    """A copy of `sheet` with the loadout's changes applied and every changed stat labeled.

    Only attack force, attack rate, top speed and armor change; mass, size, reach, endurance and
    the behavioral stats keep the sheet's own values. Inert objects have no use for a loadout and
    are returned unchanged.
    """
    if sheet.body == "inert":
        return sheet
    why = f"{chosen.label}"
    stats = dict(sheet.stats)
    stats[StatName.ATTACK_FORCE] = _scaled(stats[StatName.ATTACK_FORCE], chosen.force_mul, why)
    stats[StatName.ATTACK_RATE] = _scaled(stats[StatName.ATTACK_RATE], chosen.rate_mul, why)
    stats[StatName.SPEED] = _scaled(stats[StatName.SPEED], chosen.speed_mul, why)
    stats[StatName.ARMOR] = _armor_with(stats[StatName.ARMOR], chosen.armor_add, why)
    data = sheet.model_dump()
    data["stats"] = {name: stat.model_dump() for name, stat in stats.items()}
    data["display_name"] = f"{sheet.display_name} with {chosen.label}"
    data["sheet_hash"] = compute_sheet_hash(stats)
    return StatSheet.model_validate(data)
