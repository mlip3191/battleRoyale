"""G09 (#39): objects, machines and plants get the right category, body and weapons, and a
brand-free media name."""

from datetime import UTC, datetime

from app.models.stats import StatName
from app.research.facts import Fact
from app.research.seed_fighters import find_seed_sheet, load_seed_fighters
from app.research.statsheet import (
    FighterProfile,
    StoredFact,
    build_stat_sheet,
    get_stat_sheet,
    media_name_for,
    profile_from_seed,
)
from app.safety.media_names import safe_media_name

WHEN = datetime(2026, 11, 14, tzinfo=UTC)


# The seed-list profile for a fighter id.
def seed_profile(fighter_id: str) -> FighterProfile:
    return profile_from_seed(next(f for f in load_seed_fighters() if f.id == fighter_id))


def test_a_toaster_is_an_inert_object_with_its_mass_from_a_source() -> None:
    mass = StoredFact(
        Fact("wikidata", "P2067", 1.4, "kg", "https://www.wikidata.org/wiki/Q14890#P2067"),
        "CC0 1.0",
        WHEN,
    )
    sheet = build_stat_sheet(seed_profile("toaster"), [mass])
    assert (sheet.category, sheet.body) == ("object", "inert")
    stat = sheet.stats[StatName.MASS]
    assert (stat.value, stat.method, stat.is_estimate) == (1.4, "extracted", False)
    assert stat.source is not None and "wikidata.org" in str(stat.source.url)
    assert sheet.stats[StatName.AGGRESSION].value == 0.0  # "inanimate, an object or plant"


def test_the_bulldozer_is_a_machine_vehicle_that_rams_and_crushes() -> None:
    sheet = find_seed_sheet("bulldozer")
    assert sheet is not None
    assert (sheet.category, sheet.body) == ("vehicle", "machine")
    assert {"ramming", "crushing"} <= set(sheet.weapons)


def test_the_saguaro_cactus_is_an_inert_plant_with_spines() -> None:
    sheet = get_stat_sheet("saguaro cactus")
    assert sheet is not None
    assert (sheet.category, sheet.body, sheet.weapons) == ("plant", "inert", ["spines"])


def test_a_branded_truck_never_gets_a_brand_in_its_media_name() -> None:
    truck = FighterProfile(
        "ford-f-150",
        "Ford F-150",
        media_name_for("Ford F-150", "vehicle"),
        "vehicle",
        "machine",
        "land",
        ("ramming",),
    )
    sheet = build_stat_sheet(truck)
    assert sheet.media_name == "vehicle"
    assert "ford" not in sheet.media_name.split()


def test_every_seed_fighter_keeps_its_own_name_as_its_media_name() -> None:
    for fighter in load_seed_fighters():
        profile = profile_from_seed(fighter)
        assert profile.media_name == fighter.display_name.lower(), fighter.id
        assert safe_media_name(profile.media_name) == profile.media_name, fighter.id
