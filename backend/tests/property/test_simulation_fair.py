"""F06: fair-fight search and next-challenger testing."""

import math
from types import SimpleNamespace

import pytest

from app.models.matchup import FighterRequest
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation import fair
from app.simulation.engine import run
from app.simulation.fair import _how_even, fair_fight, fair_fight_search, test_challengers
from app.text import counted_name
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

    # Counts are whole numbers and 200-run probes are noisy, so do not judge the search by its own
    # probe. Check the answer with a bigger independent run: one cat fewer is still the underdog
    # and one cat more is the favorite (0.03 is the noise of 2,000 runs). Any version bump holds.
    def cats_win_share(cats):
        return run(matchup_of(1, cats), [wolf(), house_cat()], runs=2000, explain=False).win_prob[1]

    assert cats_win_share(max(1, found.count - 1)) <= 0.5 + 0.03
    assert cats_win_share(found.count + 1) >= 0.5 - 0.03
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


def test_counted_name_rules():
    assert counted_name("House cat", 1) == "house cat"
    assert counted_name("House cat", 37) == "house cats"
    assert counted_name("Gray wolf", 2) == "gray wolves"
    assert counted_name("Red fox", 2) == "red foxes"
    assert counted_name("Fly", 2) == "flies"
    assert counted_name("Monkey", 2) == "monkeys"


def test_counted_name_handles_irregular_names_and_keeps_proper_nouns():
    assert counted_name("House mouse", 37) == "house mice"
    assert counted_name("Goose", 2) == "geese"
    assert counted_name("Sheep", 5) == "sheep"
    # These two used to read "african elephant" and "t. rexes", pinning the old lower-casing
    # bug; fair.py now uses the shared counted_name, so proper words and "T." keep capitals (#258).
    assert counted_name("African elephant", 1) == "African elephant"
    assert counted_name("T. rex", 2) == "T. rexes"


def test_counted_name_keeps_proper_words_and_uses_the_shared_irregular_tables():
    """One pluralizer for fair fights, intake and narration (#258)."""
    assert counted_name("African elephant", 2) == "African elephants"
    assert counted_name("Roman legionary", 3) == "Roman legionaries"
    assert counted_name("House mouse", 2) == "house mice"
    assert counted_name("Bison", 4) == "bison"
    assert counted_name("Cattle", 4) == "cattle"
    assert counted_name("Triceratops", 2) == "triceratops"
    assert counted_name("T. rex", 3) == "T. rexes"
    assert counted_name("TV", 5) == "TVs"
    assert counted_name("Man", 2) == "men"
    assert counted_name("Knife", 2) == "knives"


def test_a_count_of_one_stays_singular():
    assert counted_name("African elephant", 1) == "African elephant"
    assert counted_name("House cat", 1) == "house cat"
    assert counted_name("Roman legionary", 1) == "Roman legionary"
    assert counted_name("TV", 1) == "TV"


def test_the_fair_fight_message_keeps_a_proper_first_word_capitalized(monkeypatch):
    """The Results-page message read "37 african elephants" before #258."""
    fake_engine(monkeypatch, 1, logistic(37))
    elephants = elephant().model_copy(update={"display_name": "African elephant"})
    search = fair_fight_search(matchup_of(1, 1), [wolf(), elephants], main_result(1))
    assert search.result.message == "A fair fight needs 37 African elephants against 1 gray wolf."


def test_the_search_shrinks_the_count_when_the_first_probe_is_already_too_strong():
    """A main result from a small fight, reused for a 300-cat matchup (cats win easily)."""
    small = run(matchup_of(1, 1), [house_cat(), wolf()], runs=200, explain=False)
    found = fair_fight(matchup_of(300, 1), [house_cat(), wolf()], result=small)
    assert found.varied_side == 0
    assert found.count is not None and found.count < 300
    assert abs(found.win_prob_at_count - 0.5) <= 0.1


def test_a_rough_answer_says_about_and_reports_the_real_win_share():
    # Whole numbers can't always land inside the band. Which cat counts do depends on the engine
    # version, so scan a range: "about" must appear exactly when the win share is outside the band,
    # and at least one fight in the range must be of that kind.
    rough = 0
    for cats in range(9, 31):
        found = fair_fight(matchup_of(cats, 1), [house_cat(), wolf()])
        assert found.count is not None
        outside = abs(found.win_prob_at_count - 0.5) > c.FAIR_TOLERANCE
        assert ("about" in found.message) == outside
        rough += outside
    assert rough >= 1


# --- test_challengers ----------------------------------------------------------------------------


def test_challengers_are_sorted_by_closeness_to_a_coin_flip_and_repeatable():
    candidates = [
        elephant(),
        house_cat(),
        make_sheet("bear", mass_kg=300, size_m=2.2, attack_force_n=4000),
        make_sheet("jackal", mass_kg=10, size_m=0.9, attack_force_n=700, attacks_per_s=1.5),
    ]
    first = test_challengers(wolf(), candidates, terrain=Terrain.ARENA)
    second = test_challengers(wolf(), candidates, terrain=Terrain.ARENA)
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
    (weak,) = test_challengers(wolf(), [house_cat()], terrain=Terrain.ARENA)
    assert weak.tested_win_prob == pytest.approx(0.0, abs=0.05)


def test_the_challenger_wording_follows_the_named_thresholds():
    tol, slight, eps = c.FAIR_TOLERANCE, c.CHALLENGER_SLIGHT_GAP, 1e-6  # eps: stay off float edges
    assert _how_even(0.5 + tol - eps) == _how_even(0.5 - tol + eps) == "a coin flip"
    assert _how_even(0.5 + tol + eps) == "a slight favorite"
    assert _how_even(0.5 - tol - eps) == "a slight underdog"
    assert _how_even(0.5 + slight - eps) == "a slight favorite"
    assert _how_even(0.5 - slight + eps) == "a slight underdog"
    assert _how_even(0.5 + slight + eps) == "a clear favorite"
    assert _how_even(0.5 - slight - eps) == "a clear underdog"


# --- test_challengers: the winner as the user saw it ----------------------------------------------


def mid_bear():
    return make_sheet("bear", mass_kg=300, size_m=2.2, attack_force_n=4000)


def wolves(count, size_reference=None):
    return FighterRequest(
        entity="gray-wolf", count=count, size_reference=size_reference, raw="gray wolves"
    )


def test_a_winner_of_six_is_tested_as_six_and_the_reason_says_so():
    (alone,) = test_challengers(wolf(), [mid_bear()], terrain=Terrain.ARENA)
    (pack,) = test_challengers(
        wolf(), [mid_bear()], terrain=Terrain.ARENA, winner_request=wolves(6)
    )
    assert pack.tested_win_prob < alone.tested_win_prob - 0.2  # one bear against six wolves
    assert "against 6 gray wolves." in pack.reason
    assert "against Gray wolf." in alone.reason


def test_a_winner_with_a_size_reference_is_scaled_to_it():
    big = make_sheet("elephant", mass_kg=5000, size_m=3.2, attack_force_n=20000, armor_0_1=0.5)
    (plain,) = test_challengers(wolf(), [mid_bear()], terrain=Terrain.ARENA)
    (scaled,) = test_challengers(
        wolf(),
        [mid_bear()],
        terrain=Terrain.ARENA,
        winner_request=wolves(1, "elephant"),
        winner_reference=big,
    )
    assert scaled.tested_win_prob < plain.tested_win_prob - 0.2  # an elephant-sized wolf
    assert "against Gray wolf (elephant-sized)." in scaled.reason


def test_a_size_reference_without_its_sheet_is_left_unscaled_and_does_not_fail():
    (plain,) = test_challengers(wolf(), [mid_bear()], terrain=Terrain.ARENA)
    (missing,) = test_challengers(
        wolf(), [mid_bear()], terrain=Terrain.ARENA, winner_request=wolves(1, "elephant")
    )
    assert missing.tested_win_prob == plain.tested_win_prob  # same fight, same seed
    assert "elephant-sized" not in missing.reason  # it was not scaled, so the text must not say so
    assert missing.reason == plain.reason


# --- the search logic, pinned with a fake engine ----------------------------------------------
# The real engine is noisy, so a broken search can still land on an acceptable count. Here `run`
# is replaced by a noise-free S-curve, so the exact answer and the exact probes are known.


def logistic(centre, width=4.0):
    """Win share of the varied side: 0.5 at `centre`, outside the 0.05 tolerance one step away."""
    return lambda count: 1 / (1 + math.exp(-(count - centre) / width))


def fake_engine(monkeypatch, side, curve):
    """Replace the engine inside fair.py; returns the list of (count, runs) it was asked for."""
    asked = []

    def fake_run(matchup, stat_sheets, runs, reference_sheets=None, explain=True):
        count = matchup.fighters[side].count
        asked.append((count, runs))
        win = [1 - curve(count)] * 2
        win[side] = curve(count)
        return SimpleNamespace(win_prob=tuple(win), outcome="win_0")

    monkeypatch.setattr(fair, "run", fake_run)
    return asked


def main_result(losing_side):
    """The main fight's result, which only says who lost."""
    win = [0.9, 0.9]
    win[losing_side] = 0.1
    return SimpleNamespace(win_prob=tuple(win), outcome=f"win_{1 - losing_side}")


@pytest.mark.parametrize("side", [0, 1])
def test_a_losing_side_that_starts_small_doubles_and_then_refines_to_the_exact_count(
    monkeypatch, side
):
    asked = fake_engine(monkeypatch, side, logistic(37))
    sheets = [wolf(), house_cat()] if side == 1 else [house_cat(), wolf()]
    search = fair_fight_search(matchup_of(1, 1), sheets, main_result(side))
    assert search.result.varied_side == side
    assert search.result.count == 37
    assert search.result.win_prob_at_count == pytest.approx(0.5)
    # Doubling until the win share passes 0.55 at 64, then halving the gap 32..64 down to 37.
    assert [count for count, _ in asked] == [1, 2, 4, 8, 16, 32, 64, 48, 40, 36, 38, 37]
    assert search.probes == 12 <= c.FAIR_MAX_PROBES
    assert {runs for _, runs in asked} == {c.FAIR_RUNS}


def test_a_losing_side_that_starts_too_big_halves_and_then_refines_to_the_exact_count(monkeypatch):
    asked = fake_engine(monkeypatch, 0, logistic(37))
    search = fair_fight_search(matchup_of(100, 1), [house_cat(), wolf()], main_result(0))
    assert search.result.varied_side == 0
    assert search.result.count == 37
    assert [count for count, _ in asked] == [100, 50, 25, 37]
    assert search.probes == 4


def test_the_search_stops_at_the_count_cap_when_no_count_is_fair(monkeypatch):
    asked = fake_engine(monkeypatch, 1, lambda count: 0.2)
    search = fair_fight_search(matchup_of(1, 1), [wolf(), house_cat()], main_result(1))
    counts = [count for count, _ in asked]
    assert search.result.count is None and search.result.win_prob_at_count is None
    assert search.result.message == "No fair fight within 10,000 house cats."
    assert counts == [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 10_000]
    assert max(counts) == c.FAIR_MAX_COUNT
    assert search.probes <= c.FAIR_MAX_PROBES


def test_the_search_never_runs_more_than_the_probe_limit(monkeypatch):
    # A step that no count lands near 50/50 on, with the jump too far out for the binary phase to
    # close in: the search must stop at the limit and give the closest count it saw, as "about".
    asked = fake_engine(monkeypatch, 1, lambda count: 0.3 if count < 5000 else 0.7)
    search = fair_fight_search(matchup_of(1, 1), [wolf(), house_cat()], main_result(1))
    assert len(asked) == search.probes == c.FAIR_MAX_PROBES
    assert search.result.count is not None and "about" in search.result.message
    assert 4096 < search.result.count < 8192 or search.result.count < 5000
