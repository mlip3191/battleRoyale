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
from functools import lru_cache
from pathlib import Path

import yaml

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


def at_tier(chosen: Loadout, tier: int) -> Loadout:
    """The loadout at tier 1 to 5: every change scaled by `LOADOUT_TIER_SCALE[tier]`.

    A higher tier deepens the trade-off: the gains grow and so do the costs, so a higher tier is
    a bigger commitment, not a strictly better set of stats.
    """
    if tier not in c.LOADOUT_TIER_SCALE:
        raise ValueError(f"tier must be one of {sorted(c.LOADOUT_TIER_SCALE)}, got {tier}")
    scale = c.LOADOUT_TIER_SCALE[tier]
    return Loadout(
        id=chosen.id,
        lean=chosen.lean,
        label=chosen.label if tier == 1 else f"{chosen.label} tier {tier}",
        force_mul=1.0 + (chosen.force_mul - 1.0) * scale,
        rate_mul=1.0 + (chosen.rate_mul - 1.0) * scale,
        speed_mul=1.0 + (chosen.speed_mul - 1.0) * scale,
        armor_add=chosen.armor_add * scale,
    )


ITEMS_FILE = Path(__file__).resolve().parents[3] / "data" / "loadouts" / "items.yaml"
DEFAULT_ARCHETYPE = "warrior"


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict]:
    return yaml.safe_load(ITEMS_FILE.read_text("utf-8"))


def archetype_of(sheet: StatSheet) -> str:
    """The kind of fighter a sheet is, which decides what its gear is and how heavy it is."""
    if sheet.body == "machine" or sheet.category in ("vehicle", "machine"):
        return "machine"
    hoofed_weapons = set(_catalog()["hoofed"]["covers_weapons"])
    if sheet.category == "mammal" and hoofed_weapons & set(sheet.weapons):
        return "hoofed"
    for name, data in _catalog().items():
        if sheet.category in data["covers"]:
            return name
    return DEFAULT_ARCHETYPE


def item_name(archetype: str, lean: str, tier: int) -> str:
    """The name of the item for this archetype, loadout and tier, e.g. "razor claws"."""
    if archetype not in _catalog():
        raise KeyError(f"unknown archetype {archetype!r}; known: {', '.join(sorted(_catalog()))}")
    _check_kit({lean: tier})
    return str(_catalog()[archetype]["items"][lean][tier - 1])


Kit = dict[str, int]
"""A fighter's loadouts: the loadout id and the tier it is at (1 to 5); absent means not carried."""

MAX_TIER = max(c.LOADOUT_TIER_SCALE)


def _check_kit(kit: Kit) -> None:
    for lean, tier in kit.items():
        if lean not in c.LOADOUTS:
            raise KeyError(f"unknown loadout {lean!r}; known: {', '.join(sorted(c.LOADOUTS))}")
        if tier not in c.LOADOUT_TIER_SCALE:
            raise ValueError(f"tier must be one of {sorted(c.LOADOUT_TIER_SCALE)}, got {tier}")


def kit_points(kit: Kit) -> int:
    """Points spent on a kit: one per tier of each loadout (adding is tier 1, upgrading is +1)."""
    return sum(kit.values())


def kit_load(kit: Kit, archetype: str = DEFAULT_ARCHETYPE) -> float:
    """How much weight the kit carries (each loadout adds its archetype's weight per tier)."""
    weight = c.LOADOUT_ARCHETYPES[archetype]["load"]
    return sum(weight[lean] * tier for lean, tier in kit.items())


def add_or_upgrade(kit: Kit, lean: str) -> Kit:
    """The kit after one choice: add the loadout at tier 1, or upgrade it by one tier.

    Raises ValueError if that loadout is already at the top tier, so a choice is always real.
    """
    _check_kit({lean: 1})
    tier = kit.get(lean, 0)
    if tier >= MAX_TIER:
        raise ValueError(f"{lean} is already at tier {MAX_TIER}")
    return {**kit, lean: tier + 1}


def available_choices(kit: Kit) -> list[str]:
    """The loadouts that can still be added or upgraded."""
    return [lean for lean in c.LOADOUTS if kit.get(lean, 0) < MAX_TIER]


def kit_effect(kit: Kit, archetype: str = DEFAULT_ARCHETYPE) -> Loadout:
    """The combined effect of a kit, including the negative traits of carrying a lot.

    Each loadout at its tier multiplies force, rate and speed and adds armor; then:
    - **encumbrance:** load above the archetype's free load slows the fighter and its swing (so
      too much defense, or too much of anything heavy, reduces speed);
    - **reckless:** attack above tier 3 lowers armor;
    - **fragile:** speed above tier 3 lowers attack force.
    """
    _check_kit(kit)
    force = rate = speed = 1.0
    armor = 0.0
    for lean, tier in kit.items():
        one = at_tier(loadout(lean), tier)
        force, rate, speed, armor = (
            force * one.force_mul,
            rate * one.rate_mul,
            speed * one.speed_mul,
            armor + one.armor_add,
        )
    over = max(0.0, kit_load(kit, archetype) - c.LOADOUT_ARCHETYPES[archetype]["free"])
    speed *= max(c.ENCUMBRANCE_SPEED_FLOOR, 1.0 - c.ENCUMBRANCE_SPEED_PER_LOAD * over)
    rate *= max(c.ENCUMBRANCE_RATE_FLOOR, 1.0 - c.ENCUMBRANCE_RATE_PER_LOAD * over)
    armor -= c.RECKLESS_ARMOR_PER_TIER * max(0, kit.get("attack", 0) - 3)
    fragile = max(0, kit.get("speed", 0) - 3)
    force *= max(c.FRAGILE_FORCE_FLOOR, 1.0 - c.FRAGILE_FORCE_PER_TIER * fragile)
    if len(kit) == 1:
        ((lean, tier),) = kit.items()
        label = at_tier(loadout(lean), tier).label
        lean_id = lean
    else:
        parts = [f"{lean} {kit[lean]}" for lean in c.LOADOUTS if lean in kit]
        label = "a kit of " + " and ".join(parts)
        lean_id = "kit"
    return Loadout(lean_id, lean_id, label, force, rate, speed, armor)


def apply_kit(sheet: StatSheet, kit: Kit) -> StatSheet:
    """A copy of `sheet` with the kit's combined changes applied and every changed stat labeled.

    Only attack force, attack rate, top speed and armor change; mass, size, reach, endurance and
    the behavioral stats keep the sheet's own values. Inert objects have no use for a loadout and
    are returned unchanged, and so is a sheet with an empty kit.
    """
    if sheet.body == "inert" or not kit:
        return sheet
    archetype = archetype_of(sheet)
    chosen = kit_effect(kit, archetype)
    why = chosen.label
    items = [item_name(archetype, lean, kit[lean]) for lean in c.LOADOUTS if lean in kit]
    stats = dict(sheet.stats)
    stats[StatName.ATTACK_FORCE] = _scaled(stats[StatName.ATTACK_FORCE], chosen.force_mul, why)
    stats[StatName.ATTACK_RATE] = _scaled(stats[StatName.ATTACK_RATE], chosen.rate_mul, why)
    stats[StatName.SPEED] = _scaled(stats[StatName.SPEED], chosen.speed_mul, why)
    stats[StatName.ARMOR] = _armor_with(stats[StatName.ARMOR], chosen.armor_add, why)
    data = sheet.model_dump()
    data["stats"] = {name: stat.model_dump() for name, stat in stats.items()}
    data["display_name"] = f"{sheet.display_name} with {' and '.join(items)}"
    data["sheet_hash"] = compute_sheet_hash(stats)
    return StatSheet.model_validate(data)


def apply_loadout(sheet: StatSheet, chosen: Loadout, tier: int = 1) -> StatSheet:
    """One loadout at one tier (a kit of one), with the negative traits of its weight."""
    return apply_kit(sheet, {chosen.id: tier})
