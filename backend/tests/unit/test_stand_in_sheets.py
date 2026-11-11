"""#86: stand-in sheets never carry a real citation for a number that was invented."""

from app.models.stats import ASSUMABLE_STATS, StatName
from tests.property.sim_helpers import STAND_IN_NOTE, load_sheet, make_sheet


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
