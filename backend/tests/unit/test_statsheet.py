"""G04 part 1: each stat comes from the best evidence that exists, in the documented order."""

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.stats import ASSUMABLE_STATS, Confidence, Source, StatName, StatValue
from app.research.facts import Fact, store_facts, wikidata_facts
from app.research.seed_fighters import find_seed_sheet
from app.research.sheet_hash import compute_sheet_hash
from app.research.statsheet import (
    FighterProfile,
    StoredFact,
    build_stat_sheet,
    get_stat_sheet,
    load_facts,
)

WHEN = datetime(2026, 11, 12, tzinfo=UTC)
CAT = FighterProfile("house-cat", "House cat", "house cat", "mammal", "living", "land", ("claws",))
TRUCK = FighterProfile(
    "pickup-truck", "Pickup truck", "pickup truck", "vehicle", "machine", "land", ("ramming",)
)
ANT = FighterProfile("army-ant", "Army ant", "army ant", "insect", "living", "land", ("none",))
TOASTER = FighterProfile("toaster", "Toaster", "toaster", "object", "inert", "land", ("none",))
# Wikidata facts are stored under their property IDs, as facts.py does.
WIKIDATA_IDS = {"mass": "P2067", "length": "P2043", "height": "P2048", "speed": "P2052"}


# A stored Wikidata fact for a test.
def fact(field: str, value: float, unit: str, source: str = "wikidata", n: int = 1) -> StoredFact:
    field = WIKIDATA_IDS.get(field, field) if source == "wikidata" else field
    reference = f"https://www.wikidata.org/wiki/Q146#Q146-{field}-{n}"
    return StoredFact(Fact(source, field, value, unit, reference), "CC0 1.0", WHEN)


# An extractor stand-in that returns one verified value for one stat (part 2 builds the real one).
def extractor_for(stat: StatName, value: float):
    def extract(profile: FighterProfile, wanted: StatName) -> StatValue | None:
        if wanted != stat:
            return None
        return StatValue(
            value=value,
            unit="kg",
            source=Source(
                title="House cat",
                url="https://en.wikipedia.org/wiki/Cat",
                quote=f"weighs about {value:g} kg",
                retrieved_at=WHEN,
            ),
            confidence=Confidence.HIGH,
            is_estimate=False,
            method="extracted",
            low=value * 0.9,
            high=value * 1.1,
        )

    return extract


class TestPreferenceOrder:
    def test_a_seed_sheet_wins_over_every_other_level(self, tmp_path: Path) -> None:
        sheet = get_stat_sheet("grizzly bear", _db_with(tmp_path, "grizzly-bear", mass=1.0))
        assert sheet == find_seed_sheet("grizzly bear")
        assert sheet is not None and sheet.stats[StatName.MASS].method == "hand_verified"

    def test_a_stored_fact_wins_over_extraction(self) -> None:
        sheet = build_stat_sheet(CAT, [fact("mass", 4.5, "kg")], extractor_for(StatName.MASS, 9))
        mass = sheet.stats[StatName.MASS]
        assert (mass.value, mass.method, mass.source.license) == (4.5, "extracted", "CC0 1.0")
        assert mass.source.quote == "mass: 4.5 kg"

    def test_extraction_wins_over_derived_and_default(self) -> None:
        sheet = build_stat_sheet(CAT, [], extractor_for(StatName.MASS, 4.0))
        assert sheet.stats[StatName.MASS].value == 4.0
        assert sheet.stats[StatName.MASS].source.title == "House cat"

    def test_derived_wins_over_the_category_default(self) -> None:
        sheet = build_stat_sheet(CAT, [fact("length", 0.46, "m")])
        reach = sheet.stats[StatName.REACH]
        assert (reach.method, reach.value, reach.low, reach.high) == (
            "derived",
            0.115,
            0.08625,
            0.14375,
        )
        assert reach.confidence == "medium"  # as sure as the size fact it came from

    def test_the_category_default_is_the_last_resort(self) -> None:
        mass = build_stat_sheet(CAT).stats[StatName.MASS]
        assert (mass.value, mass.method, mass.is_estimate) == (50.0, "category_default", True)

    def test_a_ramming_machine_derives_force_and_rate_from_mass_and_speed(self) -> None:
        facts = [fact("mass", 2.5, "t"), fact("speed", 180, "km/h")]
        stats = build_stat_sheet(TRUCK, facts).stats
        assert stats[StatName.ATTACK_FORCE].value == pytest.approx(0.1 * 2500 * 50, abs=1)
        assert stats[StatName.ATTACK_FORCE].method == "derived"
        assert stats[StatName.ATTACK_RATE].value == 0.4

    def test_a_zero_speed_end_stays_zero_in_the_ram_force_range(self) -> None:
        facts = [fact("speed", v, "m/s", n=i) for i, v in enumerate([0.0, 10.0, 20.0])]
        force = build_stat_sheet(TRUCK, facts).stats[StatName.ATTACK_FORCE]
        assert force.low == 0.0

    def test_a_tiny_fighter_keeps_its_reach_and_range(self) -> None:
        reach = build_stat_sheet(ANT).stats[StatName.REACH]
        assert 0 < reach.low < reach.value < reach.high
        assert reach.confidence == "low"  # derived from a default size

    def test_an_object_keeps_its_reach_default(self) -> None:
        reach = build_stat_sheet(TOASTER).stats[StatName.REACH]
        assert (reach.method, reach.value) == ("category_default", 0.0)


class TestStoredFacts:
    @pytest.mark.parametrize(
        ("stat_field", "value", "unit", "stat", "expected"),
        [
            ("mass", 10, "lb", StatName.MASS, 4.535924),
            ("speed", 36, "km/h", StatName.SPEED, 10.0),
            ("length", 6, "ft", StatName.SIZE, 1.8288),
        ],
    )
    def test_units_are_converted(
        self, stat_field: str, value: float, unit: str, stat: StatName, expected: float
    ) -> None:
        got = build_stat_sheet(CAT, [fact(stat_field, value, unit)]).stats[stat]
        assert got.value == pytest.approx(expected, rel=1e-5)  # stored to 6 significant figures
        assert got.unit in ("kg", "m/s", "m")

    def test_several_figures_give_the_middle_one_and_their_spread(self) -> None:
        facts = [fact("mass", m, "kg", n=i) for i, m in enumerate([3.0, 5.0, 4.0, 6.0])]
        mass = build_stat_sheet(CAT, facts).stats[StatName.MASS]
        assert (mass.value, mass.low, mass.high) == (4.0, 3.0, 6.0)

    def test_size_uses_the_longer_of_length_and_height(self) -> None:
        sheet = build_stat_sheet(CAT, [fact("length", 0.5, "m"), fact("height", 0.3, "m")])
        assert sheet.stats[StatName.SIZE].value == 0.5

    def test_wikidata_wins_over_the_trait_databases(self) -> None:
        facts = [fact("body mass", 3.0, "kg", source="animaltraits"), fact("mass", 4.0, "kg")]
        assert build_stat_sheet(CAT, facts).stats[StatName.MASS].value == 4.0

    def test_an_out_of_bounds_value_is_rejected_and_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            mass = build_stat_sheet(CAT, [fact("mass", 5e12, "kg")]).stats[StatName.MASS]
        assert mass.method == "category_default"
        assert "Rejected mass_kg" in caplog.text

    def test_an_unknown_unit_is_skipped(self) -> None:
        mass = build_stat_sheet(CAT, [fact("mass", 4.0, "stone")]).stats[StatName.MASS]
        assert mass.method == "category_default"

    def test_facts_are_read_from_the_database(self, tmp_path: Path) -> None:
        loaded = load_facts(_db_with(tmp_path, "house-cat", mass=4.2), "house-cat")
        assert [(s.fact.field, s.fact.value, s.license) for s in loaded] == [
            ("P2067", 4.2, "CC0 1.0")
        ]

    def test_a_real_wikidata_entity_reaches_the_sheet(self, tmp_path: Path) -> None:
        unit = "http://www.wikidata.org/entity/Q11570"  # kilogram
        claim = {
            "id": "Q146$1",
            "rank": "normal",
            "mainsnak": {"datavalue": {"value": {"amount": "+4.5", "unit": unit}}},
        }
        entity = {"id": "Q146", "claims": {"P2067": [claim]}}
        connection = connect(tmp_path / "app.db")
        apply_migrations(connection)
        store_facts(
            connection, "house-cat", "wikidata", wikidata_facts(entity), "CC0 1.0", WHEN.isoformat()
        )
        mass = build_stat_sheet(CAT, load_facts(connection, "house-cat")).stats[StatName.MASS]
        assert (mass.value, mass.method, mass.source.quote) == (4.5, "extracted", "mass: 4.5 kg")

    def test_the_quote_keeps_every_stored_digit(self) -> None:
        mass = build_stat_sheet(TRUCK, [fact("mass", 1234567, "kg")]).stats[StatName.MASS]
        assert mass.source.quote == "mass: 1234567 kg"


class TestEverySheet:
    def test_a_fighter_with_no_evidence_gets_estimates_and_assumptions(self) -> None:
        sheet = build_stat_sheet(CAT)
        for name, stat in sheet.stats.items():
            expected = "assumption" if name in ASSUMABLE_STATS else ("category_default", "derived")
            assert stat.method in expected, name
        assert sheet.sheet_hash == compute_sheet_hash(sheet.stats)

    @pytest.mark.parametrize("profile", [CAT, TRUCK], ids=lambda p: p.fighter_id)
    def test_every_value_has_a_range_and_behavior_is_assumed(self, profile: FighterProfile) -> None:
        for name, stat in build_stat_sheet(profile, [fact("mass", 4, "kg")]).stats.items():
            assert stat.low is not None and stat.high is not None, name
            assert stat.low <= stat.value <= stat.high, name
            if name in ASSUMABLE_STATS:
                assert stat.method == "assumption" and " level " in (stat.note or "")

    def test_a_seed_list_fighter_without_a_sheet_is_built(self) -> None:
        sheet = get_stat_sheet("Pickup truck")
        assert sheet is not None and sheet.fighter_id == "pickup-truck"
        assert sheet.weapons == ["ramming"]
        assert sheet.stats[StatName.ATTACK_FORCE].method == "derived"

    def test_an_unknown_fighter_has_no_sheet_yet(self) -> None:
        assert get_stat_sheet("velociraptor") is None


# A database with the migrations applied and one Wikidata mass fact for a fighter.
def _db_with(tmp_path: Path, fighter_id: str, mass: float):
    connection = connect(tmp_path / "app.db")
    apply_migrations(connection)
    store_facts(
        connection,
        fighter_id,
        "wikidata",
        [Fact("wikidata", "P2067", mass, "kg", "https://www.wikidata.org/wiki/Q1#s1")],
        "CC0 1.0",
        WHEN.isoformat(),
    )
    return connection
