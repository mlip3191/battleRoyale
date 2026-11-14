"""Shared helpers for the simulation tests: contract sheets and stand-in fighters."""

import copy
import json
from pathlib import Path

from app.models.matchup import FighterRequest, Matchup
from app.models.stats import ASSUMABLE_STATS, StatName, StatSheet
from app.models.terrain import Terrain

STAND_IN_NOTE = "stand-in value for tests (no source)"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


def load_sheet(name: str) -> StatSheet:
    return StatSheet.model_validate(json.loads((FIXTURES / name).read_text("utf-8")))


def matchup(count_0: int = 1, count_1: int = 1) -> Matchup:
    return Matchup(
        fighters=[
            FighterRequest(entity="a", count=count_0, raw="a"),
            FighterRequest(entity="b", count=count_1, raw="b"),
        ],
        terrain=Terrain.OPEN_FIELD,
        raw_text="a vs b",
    )


def label_as_stand_in(entry: dict, stat: str, mythical: bool = False) -> None:
    """Make an edited stat honest (#86, #174): no source, an estimate, low confidence, and a note.

    A behavioral stat (aggression, group tactics, armor), or any stat of a mythical fighter, becomes
    an `assumption`; any other stat becomes a `category_default`, the only estimate method the
    sheet rules allow for it. Works on the plain-dict form of a sheet.
    """
    entry["source"] = None
    entry["is_estimate"] = True
    entry["confidence"] = "low"
    assumed = mythical or StatName(stat) in ASSUMABLE_STATS
    entry["method"] = "assumption" if assumed else "category_default"
    entry["note"] = STAND_IN_NOTE


def scaled_ranges(sheet: StatSheet, factor: float) -> StatSheet:
    """Copy of a sheet with every low-high range shrunk toward its value by `factor`.

    Test-only. Only the sampling range changes (it is "filled by code", not quoted from a source);
    each stat's value, method and source stay as they were, so no citation ends up on a number it
    did not support.
    """
    data = copy.deepcopy(sheet.model_dump(mode="json"))
    for stat in data["stats"].values():
        stat["low"] = stat["value"] - (stat["value"] - stat["low"]) * factor
        stat["high"] = stat["value"] + (stat["high"] - stat["value"]) * factor
    return StatSheet.model_validate(data)


def with_stat(sheet: StatSheet, name: StatName, value: float) -> StatSheet:
    """Copy of a sheet with one stat set to a fixed value, labeled as a stand-in (#174)."""
    data = sheet.model_dump(mode="json")
    stat = data["stats"][name.value]
    stat["value"], stat["low"], stat["high"] = value, value, value
    label_as_stand_in(stat, name.value, mythical=sheet.category == "mythical")
    data["sheet_hash"] = f"{sheet.sheet_hash}-{name.value}-{value}"
    return StatSheet.model_validate(data)


def make_sheet(
    name: str,
    spread: float = 0.2,
    habitat: str | None = None,
    body: str | None = None,
    weapons: list[str] | None = None,
    fighter_id: str | None = None,
    category: str | None = None,
    **stats: float,
) -> StatSheet:
    """A stand-in fighter: the gray wolf with some stats replaced (range = value +/- spread).

    Real sheets arrive with G05; these only exercise the engine. Every replaced stat is labeled
    honestly (#86): no source, an estimate, low confidence, and a note saying it is a stand-in,
    so a stand-in can never carry the wolf's real citation. A behavioral stat (aggression, group
    tactics, armor) becomes an `assumption`; any other stat becomes a `category_default`, the
    only estimate method the sheet rules allow for it. Stats you do not replace keep the wolf's
    real source. `category` (default "mammal") and `body` say what kind of thing it is.
    """
    data = copy.deepcopy(load_sheet("stat-sheet-gray-wolf.json").model_dump(mode="json"))
    data["sheet_hash"] = name
    data["display_name"] = name.capitalize()
    if fighter_id:
        data["fighter_id"] = fighter_id  # e.g. "honey-badger", for per-fighter tables
    if habitat:
        data["habitat"] = habitat
    if body:
        data["body"] = body
    if category:
        data["category"] = category
    if weapons:
        data["weapons"] = weapons
    for stat, value in stats.items():
        entry = data["stats"][stat]
        entry["value"] = float(value)
        entry["low"] = value * (1 - spread)
        entry["high"] = value * (1 + spread)
        label_as_stand_in(entry, stat, mythical=data["category"] == "mythical")
    return StatSheet.model_validate(data)


def matchup_of(
    count_0: int,
    count_1: int,
    ref_0: str | None = None,
    ref_1: str | None = None,
    terrain: Terrain = Terrain.OPEN_FIELD,
) -> Matchup:
    return Matchup(
        fighters=[
            FighterRequest(entity="a", count=count_0, size_reference=ref_0, raw="a"),
            FighterRequest(entity="b", count=count_1, size_reference=ref_1, raw="b"),
        ],
        terrain=terrain,
        raw_text="a vs b",
    )


# Stand-in animals (round numbers, not sourced) used for timing and scaling checks.
def ant() -> StatSheet:
    return make_sheet(
        "ant",
        mass_kg=0.000003,
        size_m=0.005,
        top_speed_mps=0.1,
        attack_force_n=0.5,
        attacks_per_s=1.0,
        reach_m=0.002,
        armor_0_1=0.1,
    )


def lion() -> StatSheet:
    return make_sheet(
        "lion",
        mass_kg=190,
        size_m=2.5,
        top_speed_mps=18,
        attack_force_n=4000,
        attacks_per_s=1.0,
        reach_m=0.8,
        armor_0_1=0.1,
    )


def horse() -> StatSheet:
    return make_sheet(
        "horse",
        mass_kg=500,
        size_m=2.4,
        top_speed_mps=20,
        attack_force_n=3000,
        attacks_per_s=0.8,
        reach_m=1.0,
        armor_0_1=0.05,
    )


def duck() -> StatSheet:
    return make_sheet(
        "duck",
        mass_kg=1.2,
        size_m=0.5,
        top_speed_mps=6,
        attack_force_n=30,
        attacks_per_s=1.5,
        reach_m=0.15,
        armor_0_1=0.05,
    )


def make_dragon(
    abilities: list[str], heads: int | None = None, name: str = "dragon", **stats: float
) -> StatSheet:
    """The dragon fixture with chosen legendary powers (all its stats are assumptions).

    A stat you override keeps the `assumption` method but its note says it is a stand-in value.
    """
    data = copy.deepcopy(load_sheet("stat-sheet-dragon.json").model_dump(mode="json"))
    data["sheet_hash"] = name
    data["lore"]["abilities"] = abilities
    data["lore"]["heads"] = heads
    data["weapons"] = [w for w in data["weapons"] if w != "breath_weapon"] + (
        ["breath_weapon"] if "breath_weapon" in abilities else []
    )
    for stat, value in stats.items():
        entry = data["stats"][stat]
        entry["value"], entry["low"], entry["high"] = value, value * 0.8, value * 1.2
        label_as_stand_in(entry, stat, mythical=True)  # the dragon fixture is a mythical sheet
    return StatSheet.model_validate(data)
