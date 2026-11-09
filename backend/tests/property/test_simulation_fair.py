"""F06: fair-fight search and next-challenger testing."""

import pytest

from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import run
from app.simulation.fair import fair_fight, fair_fight_search, plural, test_challengers
from tests.property.sim_helpers import ant, lion, load_sheet, make_sheet, matchup_of


def house_cat():
    return make_sheet(
        "house cat", mass_kg=4.5, size_m=0.46, top_speed_mps=13, attack_force_n=80,
        attacks_per_s=2.0, reach_m=0.2, armor_0_1=0.05, aggression_0_1=1.0,
        group_tactics_0_1=0.1,
    )  # fmt: skip


def elephant():
    return make_sheet(
        "elephant", mass_kg=5000, size_m=3.2, top_speed_mps=11, attack_force_n=20000,
        attacks_per_s=0.5, reach_m=2.0, armor_0_1=0.5,
    )  # fmt: skip


def wolf():
    return load_sheet("stat-sheet-gray-wolf.json")


# --- fair_fight ------------------------------------------------------------------------------


def test_wolf_vs_house_cats_finds_a_count_within_tolerance_in_few_probes():
    search = fair_fight_search(matchup_of(1, 1), [wolf(), house_cat()])
    found = search.result
    assert found.count is not None and found.count > 1
    assert found.varied_side == 1  # the cats are the losing side
    assert abs(found.win_prob_at_count - 0.5) <= c.FAIR_TOLERANCE
    assert search.probes <= c.FAIR_MAX_PROBES
    assert str(found.count) in found.message and "house cats" in found.message


def test_the_losing_side_is_varied_whichever_side_it_is_on():
    found = fair_fight(matchup_of(1, 1), [house_cat(), wolf()])
    assert found.varied_side == 0
    assert found.count is not None


def test_ant_vs_elephant_has_no_fair_fight():
    search = fair_fight_search(matchup_of(1, 1), [ant(), elephant()])
    assert search.result.count is None and search.result.win_prob_at_count is None
    assert search.result.message == "No fair fight within 10,000 ants."
    assert search.probes <= c.FAIR_MAX_PROBES


def test_a_stalemate_main_result_gives_no_count_and_an_explanation():
    found = fair_fight(matchup_of(10_000, 1), [ant(), lion()])
    assert found.count is None
    assert "stalemate" in found.message


def test_a_no_contest_main_result_gives_no_count_and_an_explanation():
    eagle = make_sheet("eagle", habitat="air", mass_kg=5, size_m=0.9)
    shark = make_sheet("shark", habitat="water", mass_kg=300)
    found = fair_fight(matchup_of(1, 1, terrain=Terrain.WATER), [eagle, shark])
    assert found.count is None
    assert "reach" in found.message


def test_fair_fight_is_deterministic():
    first = fair_fight_search(matchup_of(1, 1), [wolf(), house_cat()])
    second = fair_fight_search(matchup_of(1, 1), [wolf(), house_cat()])
    assert first == second


def test_a_given_main_result_is_reused_not_recomputed():
    matchup = matchup_of(1, 1)
    main = run(matchup, [wolf(), house_cat()], runs=200, explain=False)
    assert fair_fight(matchup, [wolf(), house_cat()], result=main).count is not None


def test_search_starts_from_the_losing_sides_current_count():
    """3 cats vs a wolf: the answer can't be below the 3 already there."""
    found = fair_fight(matchup_of(3, 1), [house_cat(), wolf()])
    assert found.varied_side == 0
    assert found.count is None or found.count >= 3


def test_plural_rules():
    assert plural("House cat", 1) == "house cat"
    assert plural("House cat", 37) == "house cats"
    assert plural("Gray wolf", 2) == "gray wolves"
    assert plural("Red fox", 2) == "red foxes"
    assert plural("Fly", 2) == "flies"
    assert plural("Monkey", 2) == "monkeys"


# --- test_challengers ----------------------------------------------------------------------------


def test_challengers_are_sorted_by_closeness_to_a_coin_flip_and_repeatable():
    candidates = [
        elephant(),
        house_cat(),
        make_sheet("bear", mass_kg=300, size_m=2.2, attack_force_n=4000),
        make_sheet("jackal", mass_kg=10, size_m=0.9, attack_force_n=700, attacks_per_s=1.5),
    ]
    first = test_challengers(wolf(), candidates)
    second = test_challengers(wolf(), candidates)
    assert first == second
    gaps = [abs(s.tested_win_prob - 0.5) for s in first]
    assert gaps == sorted(gaps)
    assert {s.entity for s in first} == {"Elephant", "House cat", "Bear", "Jackal"}
    assert all(s.reason for s in first)


def test_challengers_that_cannot_meet_the_winner_are_left_out():
    eagle = make_sheet("eagle", habitat="air", mass_kg=5, size_m=0.9)
    shark = make_sheet("shark", habitat="water", mass_kg=300)
    suggestions = test_challengers(shark, [eagle, wolf()], terrain=Terrain.WATER)
    assert [s.entity for s in suggestions] == ["Gray wolf"]


def test_test_challengers_is_not_collected_as_a_test():
    assert test_challengers.__test__ is False


def test_challenger_win_probability_is_the_challengers_not_the_winners():
    (weak,) = test_challengers(wolf(), [house_cat()])
    assert weak.tested_win_prob == pytest.approx(0.0, abs=0.05)
