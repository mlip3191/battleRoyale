"""F05: the deciding factor, its explainer, and summary()."""

import json
import re
import time

import pytest

from app.models.matchup import Matchup
from app.models.stats import StatName, StatSheet
from app.models.terrain import Terrain
from app.simulation.engine import run
from app.simulation.summary import summary
from tests.property.sim_helpers import (
    FIXTURES,
    ant,
    duck,
    horse,
    lion,
    load_sheet,
    make_sheet,
    matchup_of,
)

NUMBER = re.compile(r"\d+(?:\.\d+)?")


def inputs_of(matchup: Matchup, sheets: list[StatSheet]) -> list[float]:
    """Every number the explainer is allowed to quote: stat values and fighter counts."""
    numbers = [float(f.count) for f in matchup.fighters]
    for sheet in sheets:
        numbers += [stat.value for stat in sheet.stats.values()]
    return numbers


def numbers_in(text: str, sheets: list[StatSheet]) -> list[float]:
    for sheet in sheets:  # names may contain digits; they are inputs too
        text = text.replace(sheet.display_name, "")
    return [float(n) for n in NUMBER.findall(text)]


def assert_only_input_numbers(result, matchup, sheets):
    allowed = inputs_of(matchup, sheets)
    for number in numbers_in(result.deciding_factor_explainer, sheets):
        assert any(abs(number - a) <= 0.005 * max(abs(a), 1e-12) + 1e-12 for a in allowed), (
            f"{number} is not an input (explainer: {result.deciding_factor_explainer})"
        )


def test_every_result_has_a_deciding_factor_and_explainer():
    w = make_sheet("w")
    cases = [
        (matchup_of(1, 1), [w, w]),  # mirror: too close to call
        (matchup_of(1, 1), [make_sheet("big", mass_kg=400), w]),
        (matchup_of(10_000, 1), [ant(), lion()]),  # stalemate
        (
            matchup_of(1, 1, terrain=Terrain.WATER),
            [make_sheet("e", habitat="air"), make_sheet("s", habitat="water")],
        ),
    ]
    for matchup, sheets in cases:
        result = run(matchup, sheets, runs=300)
        assert result.deciding_factor
        assert result.deciding_factor_explainer.strip()


def test_size_dominated_matchup_reports_mass_or_size():
    big = make_sheet("big", mass_kg=400, size_m=2.4)
    small = make_sheet("small", mass_kg=40, size_m=1.0)
    matchup = matchup_of(1, 1)
    result = run(matchup, [big, small])
    assert result.deciding_factor in (StatName.MASS, StatName.SIZE)
    assert_only_input_numbers(result, matchup, [big, small])


def test_swarm_matchup_reports_numbers():
    w = make_sheet("w")
    matchup = matchup_of(300, 1)
    result = run(matchup, [w, w])
    assert result.deciding_factor == "numbers"
    assert "Numbers decided it" in result.deciding_factor_explainer
    assert_only_input_numbers(result, matchup, [w, w])


def test_small_group_numbers_advantage_reports_numbers():
    w = make_sheet("w")
    result = run(matchup_of(6, 1), [w, w])
    assert result.deciding_factor == "numbers"


def test_behavioral_deciding_factor_says_it_rests_on_an_assumption():
    bold = make_sheet("bold", aggression_0_1=1.0)
    timid = make_sheet("timid", aggression_0_1=0.05)
    matchup = matchup_of(1, 1)
    result = run(matchup, [bold, timid])
    assert result.deciding_factor == StatName.AGGRESSION
    assert "rests on an assumption" in result.deciding_factor_explainer
    assert_only_input_numbers(result, matchup, [bold, timid])


def test_measured_stat_does_not_claim_an_assumption():
    big = make_sheet("big", mass_kg=400, size_m=2.4)
    small = make_sheet("small", mass_kg=40, size_m=1.0)
    result = run(matchup_of(1, 1), [big, small])
    assert "assumption" not in result.deciding_factor_explainer


def test_terrain_can_be_the_deciding_factor():
    shark = make_sheet("shark", habitat="water", mass_kg=300, attack_force_n=3000)
    cat = lion()
    result = run(matchup_of(1, 1, terrain=Terrain.WATER), [shark, cat], runs=300)
    assert result.deciding_factor == "terrain"
    assert "water" in result.deciding_factor_explainer


def test_a_size_reference_battle_credits_the_scaling_not_a_raw_stat():
    """100 duck-sized horses vs a horse-sized duck: size decided it, because of the scaling."""
    matchup = matchup_of(100, 1, ref_0="duck", ref_1="horse", terrain=Terrain.OPEN_FIELD)
    sheets = [horse(), duck()]
    result = run(matchup, sheets, runs=300, reference_sheets=[duck(), horse()])
    text = result.deciding_factor_explainer
    assert result.deciding_factor == StatName.MASS
    assert "after scaling" in text
    assert "scaled to duck size" in text and "scaled to horse size" in text
    assert_only_input_numbers(result, matchup, sheets)


def test_a_battle_without_size_references_never_mentions_scaling():
    big = make_sheet("big", mass_kg=400, size_m=2.4)
    small = make_sheet("small", mass_kg=40, size_m=1.0)
    result = run(matchup_of(1, 1), [big, small], runs=300)
    assert "scaling" not in result.deciding_factor_explainer.lower()


def test_mirror_match_is_too_close_to_call():
    w = make_sheet("w")
    result = run(matchup_of(1, 1), [w, w], runs=300)
    assert "Too close to call" in result.deciding_factor_explainer


def test_stalemate_is_explained_as_a_stalemate():
    result = run(matchup_of(10_000, 1), [ant(), lion()], runs=100)
    assert result.outcome == "draw"
    assert "stalemate" in result.deciding_factor_explainer.lower()


def test_explainer_quotes_only_input_numbers_for_the_contract_fixtures():
    bear = load_sheet("stat-sheet.json")
    wolf = load_sheet("stat-sheet-gray-wolf.json")
    matchup = Matchup.model_validate(json.loads((FIXTURES / "matchup.json").read_text("utf-8")))
    result = run(matchup, [bear, wolf])
    assert_only_input_numbers(result, matchup, [bear, wolf])


def test_deciding_factor_is_reproducible():
    big = make_sheet("big", mass_kg=400, size_m=2.4)
    small = make_sheet("small", mass_kg=40, size_m=1.0)
    first = run(matchup_of(1, 1), [big, small], runs=300)
    second = run(matchup_of(1, 1), [big, small], runs=300)
    assert first == second


def test_simulate_plus_deciding_factor_finishes_under_five_seconds_for_one_v_one():
    bear = load_sheet("stat-sheet.json")
    wolf = load_sheet("stat-sheet-gray-wolf.json")
    start = time.perf_counter()
    run(matchup_of(1, 1), [bear, wolf], runs=1000)
    assert time.perf_counter() - start < 5.0


def test_explain_false_skips_the_analysis():
    w = make_sheet("w")
    result = run(matchup_of(1, 1), [w, w], runs=50, explain=False)
    assert result.deciding_factor_explainer == "Deciding factor not computed."


# --- summary() ---------------------------------------------------------------------------------


def test_summary_gives_the_numbers_the_ui_and_announcer_need():
    big = make_sheet("big", mass_kg=400, size_m=2.4)
    small = make_sheet("small", mass_kg=40, size_m=1.0)
    result = run(matchup_of(1, 1), [big, small], runs=300)
    s = summary(result, ("Big", "Small"))
    assert s.favorite == 0 and s.favorite_name == "Big"
    assert s.win_pct[0] > 90 and s.win_pct[0] + s.win_pct[1] + s.draw_pct == pytest.approx(
        100, abs=0.2
    )
    assert s.duration_s == round(result.mean_duration_s, 1)
    assert s.survivors == (round(result.mean_survivors[0], 1), round(result.mean_survivors[1], 1))
    assert s.deciding_factor_text == result.deciding_factor_explainer
    assert s.outcome == "win_0"


def test_summary_has_no_favorite_for_a_draw_or_no_contest():
    draw = run(matchup_of(10_000, 1), [ant(), lion()], runs=50)
    assert summary(draw, ("Ant", "Lion")).favorite is None
    contest = run(
        matchup_of(1, 1, terrain=Terrain.WATER),
        [make_sheet("e", habitat="air"), make_sheet("s", habitat="water")],
        runs=10,
    )
    s = summary(contest, ("E", "S"))
    assert s.outcome == "no_contest" and s.favorite is None
    assert s.deciding_factor == "habitat"
