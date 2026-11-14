"""G09: a mythical creature's sheet is its body analog scaled to its size analog, all assumed."""

import pytest

from app.models.stats import Ability, StatName
from app.research.mythical import (
    Creature,
    build_mythical_sheet,
    find_creature,
    load_creatures,
)
from app.research.seed_fighters import find_seed_sheet
from app.simulation import constants as c


def sheet_for(creature_id: str):
    creature = find_creature(creature_id)
    assert creature is not None
    return build_mythical_sheet(creature)


def test_the_dragon_is_a_crocodile_scaled_to_elephant_mass() -> None:
    dragon = sheet_for("dragon")
    croc, elephant = find_seed_sheet("saltwater crocodile"), find_seed_sheet("African elephant")
    assert croc is not None and elephant is not None
    k = elephant.stats[StatName.MASS].value / croc.stats[StatName.MASS].value
    assert dragon.stats[StatName.MASS].value == elephant.stats[StatName.MASS].value
    expected = {
        StatName.SIZE: croc.stats[StatName.SIZE].value * k**c.LENGTH_SCALE_EXP,
        StatName.ATTACK_FORCE: croc.stats[StatName.ATTACK_FORCE].value * k**c.STRENGTH_SCALE_EXP,
        StatName.SPEED: croc.stats[StatName.SPEED].value * k**c.SPEED_SCALE_EXP,
        StatName.ATTACK_RATE: croc.stats[StatName.ATTACK_RATE].value,
        StatName.AGGRESSION: croc.stats[StatName.AGGRESSION].value,
    }
    for name, value in expected.items():
        assert dragon.stats[name].value == pytest.approx(value, rel=1e-5), name


def test_every_dragon_stat_is_an_assumption_naming_both_analogs() -> None:
    dragon = sheet_for("dragon")
    for name, stat in dragon.stats.items():
        assert stat.method == "assumption" and stat.is_estimate, name
        assert stat.source is None and stat.confidence == "low", name
        assert stat.note and "saltwater crocodile" in stat.note, name
        assert "African elephant" in stat.note, name
        assert stat.low is not None and stat.high is not None, name


def test_the_dragon_keeps_its_lore_and_flies_at_its_scaled_body_speed() -> None:
    dragon = sheet_for("Dragon")
    assert dragon.category == "mythical" and dragon.fighter_id == "dragon"
    assert dragon.lore is not None
    assert set(dragon.lore.abilities) == {Ability.FLIGHT, Ability.BREATH_WEAPON}
    assert "Flight doesn't change it" in (dragon.stats[StatName.SPEED].note or "")


def test_no_size_analog_keeps_the_body_size() -> None:
    werewolf, wolf = sheet_for("werewolf"), find_seed_sheet("gray wolf")
    assert wolf is not None
    for name in StatName:
        assert werewolf.stats[name].value == wolf.stats[name].value, name
    assert werewolf.stats[StatName.MASS].note == "Modeled on gray wolf, at its own size."


@pytest.mark.parametrize("creature", load_creatures(), ids=lambda m: m.id)
def test_every_creature_in_the_file_builds_a_valid_sheet(creature: Creature) -> None:
    sheet = build_mythical_sheet(creature)
    assert sheet.fighter_id == creature.id
    assert all(stat.method == "assumption" for stat in sheet.stats.values())


def test_the_sheet_is_the_same_every_time() -> None:
    assert sheet_for("kraken").sheet_hash == sheet_for("kraken").sheet_hash


def test_names_off_the_list_find_no_creature() -> None:
    assert find_creature("sea serpent") is not None
    assert find_creature("hydra") is None
