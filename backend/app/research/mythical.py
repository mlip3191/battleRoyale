"""Stat sheets for mythical creatures, built by code from real animals (G09, #39).

No source measures a dragon, so code copies the body analog's seed sheet and scales it to the
size analog's mass with the engine's square-cube rules (simulation/constants.py), the same ones
a "horse-sized duck" uses. Every stat is then an "assumption" (ARCHITECTURE §5) whose note names
both analogs. Abilities such as flight and breath come from the lore; they don't change a stat
(PM choice on #39: a flying creature keeps its scaled body speed).
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import REPO_ROOT
from app.models.stats import Confidence, LoreProfile, StatName, StatSheet, StatValue
from app.research.ranges import range_for
from app.research.seed_fighters import fighter_slug, find_seed_sheet
from app.research.sheet_hash import compute_sheet_hash
from app.research.statsheet import get_stat_sheet
from app.simulation import constants as c

MYTHICAL_PATH = REPO_ROOT / "data" / "seed" / "mythical.yaml"

# How each stat grows when a body is resized by k = size analog mass / body analog mass.
SCALE_EXPONENTS: dict[StatName, float] = {
    StatName.MASS: 1.0,
    StatName.SIZE: c.LENGTH_SCALE_EXP,
    StatName.REACH: c.LENGTH_SCALE_EXP,
    StatName.ATTACK_FORCE: c.STRENGTH_SCALE_EXP,
    StatName.SPEED: c.SPEED_SCALE_EXP,
}


@dataclass(frozen=True)
class Creature:
    """One entry of mythical.yaml."""

    id: str
    display_name: str
    media_name: str
    lore: LoreProfile


# Every creature in the file.
def load_creatures(path: Path = MYTHICAL_PATH) -> list[Creature]:
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))["creatures"]
    return [
        Creature(e["id"], e["display_name"], e["media_name"], LoreProfile.model_validate(e["lore"]))
        for e in entries
    ]


# The creature a name refers to ("Dragon", "sea serpent", "Sea-serpent"), or None.
def find_creature(name: str, path: Path = MYTHICAL_PATH) -> Creature | None:
    slug = fighter_slug(name)
    return next(
        (m for m in load_creatures(path) if slug in (m.id, fighter_slug(m.display_name))), None
    )


# An analog's sheet: its hand-verified seed sheet, else the one the G04 builder makes for a
# seed-list fighter (the great white shark has no hand-verified sheet yet, so it is built).
def analog_sheet(name: str) -> StatSheet:
    sheet = find_seed_sheet(name) or get_stat_sheet(name)
    if sheet is None:
        raise ValueError(f"analog {name!r} is not a seed-list fighter")
    return sheet


# The creature's sheet: the body analog scaled to the size analog, every stat an assumption.
def build_mythical_sheet(creature: Creature) -> StatSheet:
    lore = creature.lore
    body = analog_sheet(lore.body_analog)
    size = analog_sheet(lore.size_analog) if lore.size_analog else None
    k = size.stats[StatName.MASS].value / body.stats[StatName.MASS].value if size else 1.0
    stats = {name: _assumed(name, value, k, lore) for name, value in body.stats.items()}
    return StatSheet.model_validate(
        {
            "fighter_id": creature.id,
            "display_name": creature.display_name,
            "media_name": creature.media_name,
            "category": "mythical",
            "body": body.body,
            "habitat": body.habitat,
            "weapons": list(body.weapons),
            "lore": lore,
            "stats": stats,
            "sheet_hash": compute_sheet_hash(stats),
        }
    )


# One stat of the body analog, scaled by k where size changes it, relabeled as an assumption.
def _assumed(name: StatName, body_value: StatValue, k: float, lore: LoreProfile) -> StatValue:
    exponent = SCALE_EXPONENTS.get(name)
    if name == StatName.MASS and lore.size_analog:
        value = analog_sheet(lore.size_analog).stats[StatName.MASS].value  # exactly, not k x mass
    else:
        value = body_value.value * k**exponent if exponent is not None else body_value.value
    value = float(f"{value:.6g}")
    low, high = range_for(name, value, Confidence.LOW)
    return StatValue(
        value=value,
        unit=body_value.unit,
        confidence=Confidence.LOW,
        is_estimate=True,
        method="assumption",
        low=low,
        high=high,
        note=_note(name, exponent, k, lore),
    )


# Which analogs a value came from and how it was scaled.
def _note(name: StatName, exponent: float | None, k: float, lore: LoreProfile) -> str:
    if lore.size_analog:
        start = f"Modeled on {lore.body_analog}, scaled to {lore.size_analog} mass"
        how = (
            f" (square-cube rules: k = {k:.3g}, this stat x k^{exponent:.3g})."
            if exponent is not None and name != StatName.MASS
            else " (square-cube rules)."
            if exponent is not None
            else "; size doesn't change this stat."
        )
    else:
        start, how = f"Modeled on {lore.body_analog}, at its own size", "."
    if name == StatName.SPEED and "flight" in lore.abilities:
        how += " Flight doesn't change it: the scaled body speed is used."
    return start + how
