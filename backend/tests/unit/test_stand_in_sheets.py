"""#86: stand-in sheets never carry a real citation for a number that was invented."""

from app.models.stats import ASSUMABLE_STATS, StatName
from tests.property.sim_helpers import (
    STAND_IN_NOTE,
    load_sheet,
    make_dragon,
    make_sheet,
    scaled_ranges,
    with_stat,
)


def test_an_overridden_stat_has_no_source_and_is_labeled_a_low_confidence_estimate():
    duck = make_sheet("duck", mass_kg=1.2)
    mass = duck.stats[StatName.MASS]
    assert mass.value == 1.2
    assert mass.source is None and mass.is_estimate
    assert mass.confidence == "low" and mass.method == "category_default"
    assert mass.note == STAND_IN_NOTE


def test_an_overridden_behavioral_stat_is_an_assumption():
    bold = make_sheet("bold", aggression_0_1=0.9, armor_0_1=0.4, group_tactics_0_1=0.1)
    for name in ASSUMABLE_STATS:
        stat = bold.stats[name]
        assert stat.method == "assumption" and stat.source is None and stat.is_estimate
        assert stat.note == STAND_IN_NOTE


def test_a_stat_that_was_not_overridden_keeps_the_fixtures_real_source():
    wolf = load_sheet("stat-sheet-gray-wolf.json")
    duck = make_sheet("duck", top_speed_mps=6)
    size = duck.stats[StatName.SIZE]  # the fixture sources only mass and size
    assert size == wolf.stats[StatName.SIZE] and size.source is not None


def test_no_stat_is_both_overridden_and_cited():
    sheet = make_sheet("mix", mass_kg=3, size_m=0.4, top_speed_mps=9, attack_force_n=50)
    for name in (StatName.MASS, StatName.SIZE, StatName.SPEED, StatName.ATTACK_FORCE):
        assert sheet.stats[name].source is None


def test_the_category_can_be_set_instead_of_inheriting_mammal():
    assert make_sheet("plain").category == "mammal"
    assert make_sheet("duck", category="bird").category == "bird"
    tank = make_sheet("tank", category="vehicle", body="machine", weapons=["ramming"])
    assert tank.category == "vehicle" and tank.body.value == "machine"


# --- The other helpers that edit a copy of a real sheet (#174) -----------------------------------


def test_with_stat_labels_the_edited_stat_as_an_unsourced_estimate_and_keeps_the_rest():
    bear = load_sheet("stat-sheet.json")
    edited = with_stat(bear, StatName.MASS, 12.0)
    mass = edited.stats[StatName.MASS]
    assert mass.value == 12.0 and mass.source is None and mass.is_estimate
    assert mass.confidence == "low" and mass.method == "category_default"
    assert mass.note == STAND_IN_NOTE
    assert edited.stats[StatName.SIZE] == bear.stats[StatName.SIZE]  # untouched, still sourced


def test_with_stat_on_a_behavioral_stat_makes_it_an_assumption():
    edited = with_stat(load_sheet("stat-sheet-gray-wolf.json"), StatName.ARMOR, 0.9)
    armor = edited.stats[StatName.ARMOR]
    assert armor.value == 0.9 and armor.method == "assumption"
    assert armor.source is None and armor.note == STAND_IN_NOTE


def test_with_stat_on_a_mythical_sheet_stays_valid():
    dragon = load_sheet("stat-sheet-dragon.json")
    edited = with_stat(dragon, StatName.MASS, 5000.0)  # every stat of a mythical fighter is assumed
    assert edited.stats[StatName.MASS].method == "assumption"
    assert edited.stats[StatName.MASS].note == STAND_IN_NOTE


def test_scaled_ranges_changes_only_the_sampling_range_not_a_value_or_its_source():
    wolf = load_sheet("stat-sheet-gray-wolf.json")
    narrow = scaled_ranges(wolf, 0.1)
    for name, before in wolf.stats.items():
        after = narrow.stats[name]
        assert (after.value, after.method, after.source) == (
            before.value,
            before.method,
            before.source,
        )
        assert after.high - after.low <= before.high - before.low


def test_make_dragon_overrides_say_stand_in_and_the_rest_keep_their_rubric_notes():
    plain = make_dragon(["flight"])
    edited = make_dragon(["flight"], mass_kg=3000.0)
    assert edited.stats[StatName.MASS].value == 3000.0
    assert edited.stats[StatName.MASS].method == "assumption"
    assert edited.stats[StatName.MASS].note == STAND_IN_NOTE
    assert edited.stats[StatName.SPEED] == plain.stats[StatName.SPEED]
