"""Build a fighter's stat sheet, taking each stat from the best evidence that exists (G04).

Order per physical stat (docs/research.md): hand-verified seed sheet, a stored fact (Wikidata,
then trait databases), a number extracted with a verified quote (extract.py), a value derived
by code, then the category default. Behavioral stats are never extracted: they come from
the seed sheet or are rubric assumptions.
"""

import logging
import sqlite3
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.models.stats import Confidence, Source, StatName, StatSheet, StatValue
from app.research.defaults import PHYSICAL_ORDER, behavioral_default, category_default
from app.research.facts import PROPERTIES, Fact
from app.research.ranges import range_for, within_sanity_bounds
from app.research.seed_fighters import (
    SeedFighter,
    fighter_slug,
    find_seed_sheet,
    load_seed_fighters,
)
from app.research.sheet_hash import compute_sheet_hash
from app.research.units import STAT_UNITS, UnitError, to_stat_unit
from app.simulation import constants as c

logger = logging.getLogger(__name__)

BEHAVIORAL = (StatName.ARMOR, StatName.AGGRESSION, StatName.GROUP_TACTICS)
RAM_WEAPONS = frozenset({"ramming", "crushing"})

# Which stored facts can fill each stat, best first. Each group is (source, fields); the first
# group with a usable fact wins, and within a group the larger field wins (size is the longest
# dimension, so a height taller than the length is used). Wikidata fields are property IDs, as
# facts.py stores them: P2067 mass, P2043 length, P2048 height, P2052 speed.
FACT_GROUPS: dict[StatName, list[tuple[str, tuple[str, ...]]]] = {
    StatName.MASS: [
        ("wikidata", ("P2067",)),
        ("animaltraits", ("body mass",)),
        ("pantheria", ("5-1_AdultBodyMass_g",)),
    ],
    StatName.SIZE: [
        ("wikidata", ("P2043", "P2048")),
        ("pantheria", ("13-1_AdultHeadBodyLen_mm",)),
    ],
    StatName.SPEED: [("wikidata", ("P2052",))],
}
CONFIDENCE_ORDER = (Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH)
SOURCE_TITLES = {
    "wikidata": "Wikidata",
    "animaltraits": "AnimalTraits (Herberstein et al. 2022)",
    "pantheria": "PanTHERIA (Jones et al. 2009)",
}


@dataclass(frozen=True)
class FighterProfile:
    """Who the fighter is: everything a sheet needs besides its stats."""

    fighter_id: str
    display_name: str
    media_name: str
    category: str
    body: str
    habitat: str
    weapons: tuple[str, ...]


@dataclass(frozen=True)
class StoredFact:
    """A fact from the facts table, with the license and date it was stored with."""

    fact: Fact
    license: str
    retrieved_at: datetime


# Next level after stored facts: the chat-model extractor (extract.py runs it before building,
# since model calls are async). Returns None when it finds nothing it can verify.
Extractor = Callable[[FighterProfile, StatName], StatValue | None]


def no_extraction(profile: FighterProfile, stat: StatName) -> StatValue | None:
    return None


# Weapons for seed-list fighters whose weapon changes the fight. Only ramming, crushing,
# weapon_ranged, and spines (on an inert body) change it; other weapon words are for narration.
SEED_WEAPONS: dict[str, tuple[str, ...]] = {
    "bulldozer": ("ramming", "crushing"),
    "saguaro-cactus": ("spines",),
}


# A seed-list fighter's profile. Weapons aren't in the seed list: machines ram, the fighters in
# SEED_WEAPONS get theirs, and everyone else gets "none" until intake or G09 says how they attack.
def profile_from_seed(fighter: SeedFighter) -> FighterProfile:
    weapons = ("ramming",) if fighter.body == "machine" else ("none",)
    weapons = SEED_WEAPONS.get(fighter.id, weapons)
    return FighterProfile(
        fighter_id=fighter.id,
        display_name=fighter.display_name,
        media_name=fighter.display_name.lower(),
        category=fighter.category,
        body=fighter.body,
        habitat=fighter.habitat,
        weapons=weapons,
    )


# Every fact stored for a fighter.
def load_facts(connection: sqlite3.Connection, fighter_id: str) -> list[StoredFact]:
    rows = connection.execute(
        "SELECT source, field, value, unit, reference, license, retrieved_at FROM facts "
        "WHERE fighter_id = ? ORDER BY fact_id",
        (fighter_id,),
    ).fetchall()
    return [
        StoredFact(Fact(*row[:5]), license=row[5], retrieved_at=datetime.fromisoformat(row[6]))
        for row in rows
    ]


# The stat's value from stored facts, or None when no fact is usable.
def stat_from_facts(stat: StatName, facts: Sequence[StoredFact]) -> StatValue | None:
    for source, fields in FACT_GROUPS.get(stat, []):
        picks = [
            _pick(stat, [f for f in facts if (f.fact.source, f.fact.field) == (source, field)])
            for field in fields
        ]
        usable = [p for p in picks if p is not None]
        if usable:
            return max(usable, key=lambda value: value.value)
    return None


# One field's facts as a stat value: the middle quoted figure (the upper of the two middle ones,
# as docs/research.md prefers the upper figure), with the spread of all of them
# as the range. Facts in an unknown unit or outside the sanity bounds are dropped.
def _pick(stat: StatName, facts: list[StoredFact]) -> StatValue | None:
    converted = []
    for stored in facts:
        try:
            value = to_stat_unit(stored.fact.value, stored.fact.unit, stat)
        except UnitError:
            logger.warning("Skipped %s fact in unit %r.", stat.value, stored.fact.unit)
            continue
        if within_sanity_bounds(stat, value):
            converted.append((value, stored))
    if not converted:
        return None
    values = sorted(value for value, _ in converted)
    middle = statistics.median_high(values)
    value, chosen = next(pair for pair in converted if pair[0] == middle)
    # Wikidata drops qualifiers such as sex, so one figure is only medium confidence.
    low, high = (values[0], values[-1]) if len(values) > 1 else (None, None)
    low, high = range_for(stat, value, Confidence.MEDIUM, low, high)
    fact = chosen.fact
    count = (
        f" Middle of {len(values)} stored figures (the upper one if two are in the middle); "
        "low and high are the smallest and largest."
    )
    return StatValue(
        value=_sig(value),
        unit=STAT_UNITS[stat],
        source=Source(
            title=SOURCE_TITLES.get(fact.source, fact.source),
            url=fact.reference.split(" ")[0],
            quote=f"{PROPERTIES.get(fact.field, fact.field)}: {fact.value:.15g} {fact.unit}",
            retrieved_at=chosen.retrieved_at,
            license=chosen.license,
        ),
        confidence=Confidence.MEDIUM,
        is_estimate=False,
        method="extracted",
        low=_sig(low),
        high=_sig(high),
        note=f"Stored {fact.source} fact, converted to {STAT_UNITS[stat]}."
        + (count if len(values) > 1 else " One stored figure; range is the standard +/-25%."),
    )


# A value code computes from stats already chosen, or None when no formula applies. Objects and
# plants don't lunge, so they keep their reach default.
def derive(
    stat: StatName, profile: FighterProfile, chosen: dict[StatName, StatValue]
) -> StatValue | None:
    rams = bool(RAM_WEAPONS & set(profile.weapons))
    if stat == StatName.REACH and StatName.SIZE in chosen and profile.body != "inert":
        size = chosen[StatName.SIZE]

        def reach(s: float) -> float:
            return 0.25 * s

        return _derived(
            reach(size.value),
            stat,
            reach(_end(size.low, size.value)),
            reach(_end(size.high, size.value)),
            "reach = 0.25 x size_m, from size_m; low and high use size's low and high.",
            _weakest(size),
        )
    if stat == StatName.ATTACK_FORCE and rams:
        return _ram_force(profile, chosen[StatName.MASS], chosen[StatName.SPEED])
    if stat == StatName.ATTACK_RATE and rams:
        rate = c.RAM_ATTACKS_PER_S
        return _derived(
            rate,
            stat,
            rate,
            rate,
            "Ramming machine: RAM_ATTACKS_PER_S, the engine's fixed ramming rate.",
            Confidence.MEDIUM,
        )
    return None


# Ram force from the momentum formula; low and high use the low and high mass and speed.
def _ram_force(profile: FighterProfile, mass: StatValue, speed: StatValue) -> StatValue:
    floor = c.CRUSH_MIN_SPEED_MPS if "crushing" in profile.weapons else 0.0
    scale = c.RAM_DAMAGE_PER_MOMENTUM / c.DAMAGE_PER_NEWTON

    def force(m: float, v: float) -> float:
        return scale * m * max(v, floor)

    return _derived(
        force(mass.value, speed.value),
        StatName.ATTACK_FORCE,
        force(_end(mass.low, mass.value), _end(speed.low, speed.value)),
        force(_end(mass.high, mass.value), _end(speed.high, speed.value)),
        "Ramming machine: attack_force_n = RAM_DAMAGE_PER_MOMENTUM x mass_kg x top_speed_mps / "
        "DAMAGE_PER_NEWTON. The engine works out the real hit from mass and speed.",
        _weakest(mass, speed),
    )


# One end of a range, or the value when the range is missing (a 0.0 end is a real end).
def _end(bound: float | None, value: float) -> float:
    return value if bound is None else bound


# A derived value is only as sure as its least sure input.
def _weakest(*inputs: StatValue) -> Confidence:
    return min((i.confidence for i in inputs), key=CONFIDENCE_ORDER.index)


# Keep `sig` significant figures, so tiny fighters keep their precision.
def _sig(x: float, sig: int = 6) -> float:
    return float(f"{x:.{sig}g}")


def _derived(
    value: float, stat: StatName, low: float, high: float, note: str, confidence: Confidence
) -> StatValue:
    return StatValue(
        value=_sig(value),
        unit=STAT_UNITS[stat],
        confidence=confidence,
        is_estimate=False,
        method="derived",
        low=_sig(low),
        high=_sig(high),
        note=note,
    )


# The sheet for a fighter with no seed sheet, built level by level for each stat.
def build_stat_sheet(
    profile: FighterProfile,
    facts: Sequence[StoredFact] = (),
    extract: Extractor = no_extraction,
) -> StatSheet:
    chosen: dict[StatName, StatValue] = {}
    for stat in PHYSICAL_ORDER:
        value = (
            stat_from_facts(stat, facts)
            or extract(profile, stat)
            or derive(stat, profile, chosen)
            or category_default(profile.category, stat)
        )
        if value is None:  # vehicles and machines with no ram weapon: G09 decides
            raise ValueError(f"no value for {stat.value} of {profile.fighter_id}")
        chosen[stat] = value
    for stat in BEHAVIORAL:
        chosen[stat] = behavioral_default(profile.category, stat)
    return StatSheet.model_validate(
        {
            "fighter_id": profile.fighter_id,
            "display_name": profile.display_name,
            "media_name": profile.media_name,
            "category": profile.category,
            "body": profile.body,
            "habitat": profile.habitat,
            "weapons": list(profile.weapons),
            "stats": chosen,
            "sheet_hash": compute_sheet_hash(chosen),
        }
    )


# The best sheet for a fighter name: its seed sheet if there is one, else one built from stored
# facts for a seed-list fighter. None for anything else (intake and G09 cover new fighters).
def get_stat_sheet(entity: str, connection: sqlite3.Connection | None = None) -> StatSheet | None:
    seed = find_seed_sheet(entity)
    if seed is not None:
        return seed
    slug = fighter_slug(entity)
    fighter = next(
        (f for f in load_seed_fighters() if slug in (f.id, fighter_slug(f.display_name))), None
    )
    if fighter is None or fighter.category == "mythical":
        return None
    facts = load_facts(connection, fighter.id) if connection is not None else []
    return build_stat_sheet(profile_from_seed(fighter), facts)
