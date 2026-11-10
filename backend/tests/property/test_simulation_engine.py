"""F02: the fight engine is deterministic, honest about uncertainty, and fast."""

import json
import time

import pytest

from app.models.matchup import Matchup
from app.models.simulation import EventType, SimulationResult
from app.models.stats import StatName, StatSheet
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import DRAW, run, run_once
from app.simulation.fighters import sample_template
from app.simulation.rng import make_seed, run_rng
from tests.property.sim_helpers import (
    FIXTURES,
    load_sheet,
    matchup,
    scaled_ranges,
    with_stat,
)


def test_run_returns_valid_result_for_contract_fixture():
    bear, wolf = load_sheet("stat-sheet.json"), load_sheet("stat-sheet-gray-wolf.json")
    m = Matchup.model_validate(json.loads((FIXTURES / "matchup.json").read_text("utf-8")))
    result = run(m, [bear, wolf])
    assert SimulationResult.model_validate(result.model_dump()) == result
    assert result.runs == 1000
    assert result.representative_log[-1].type == EventType.END


def test_same_inputs_give_identical_result():
    bear, wolf = load_sheet("stat-sheet.json"), load_sheet("stat-sheet-gray-wolf.json")
    assert run(matchup(), [bear, wolf], runs=200) == run(matchup(), [bear, wolf], runs=200)


def test_seed_depends_on_matchup_hashes_and_is_stable():
    m = matchup()
    assert make_seed(m, "h0", "h1") == make_seed(m, "h0", "h1")
    assert make_seed(m, "h0", "h1") != make_seed(m, "h0", "h2")
    assert make_seed(m, "h0", "h1") != make_seed(matchup(2, 1), "h0", "h1")


def test_narrower_stat_ranges_give_a_narrower_interval():
    """A near-even fight (wolf vs a slightly weaker wolf): wide inputs blur who is favored."""
    wolf = load_sheet("stat-sheet-gray-wolf.json")
    weaker = with_stat(wolf, StatName.ATTACK_FORCE, 1250.0)
    data = weaker.model_dump(mode="json")
    data["stats"]["attack_force_n"]["low"], data["stats"]["attack_force_n"]["high"] = 625.0, 1875.0
    weaker = StatSheet.model_validate(data)

    def width(a: StatSheet, b: StatSheet) -> float:
        low, high = run(matchup(), [a, b], runs=1000).win_prob_ci95[0]
        return high - low

    assert width(scaled_ranges(wolf, 0.05), scaled_ranges(weaker, 0.05)) < width(wolf, weaker)


def test_each_run_samples_stats_inside_their_ranges():
    wolf = load_sheet("stat-sheet-gray-wolf.json")
    low, high = wolf.stats[StatName.MASS].low, wolf.stats[StatName.MASS].high
    masses = [sample_template(wolf, 1, run_rng(1, k)).mass_kg for k in range(200)]
    assert all(low <= m <= high for m in masses)
    assert max(masses) - min(masses) > 0.5 * (high - low)


def test_fight_still_going_at_600_seconds_is_a_draw():
    """A fighter that hits for almost nothing can never finish a heavy opponent."""
    weak = with_stat(load_sheet("stat-sheet-gray-wolf.json"), StatName.ATTACK_FORCE, 1.0)
    result = run(matchup(), [weak, weak], runs=20)
    assert result.draw_prob == 1.0
    assert result.outcome == "draw"
    assert result.mean_duration_s == c.MAX_FIGHT_S
    assert result.representative_log[-1].t == c.MAX_FIGHT_S


def test_run_once_reports_draw_code_at_time_limit():
    weak = with_stat(load_sheet("stat-sheet-gray-wolf.json"), StatName.ATTACK_FORCE, 1.0)
    rng = run_rng(1, 0)
    sides = [sample_template(weak, 1, rng), sample_template(weak, 1, rng)]
    outcome = run_once(sides, Terrain.ARENA, rng)
    assert outcome.winner == DRAW
    assert outcome.duration_s == c.MAX_FIGHT_S


def test_event_log_never_exceeds_300_events():
    weak = with_stat(load_sheet("stat-sheet-gray-wolf.json"), StatName.ATTACK_FORCE, 1.0)
    result = run(matchup(3, 3), [weak, weak], runs=5)
    assert len(result.representative_log) <= c.MAX_LOG_EVENTS
    assert result.representative_log[-1].type == EventType.END


def test_one_v_one_thousand_runs_finish_within_the_simulate_budget():
    # ARCHITECTURE section 4: the simulate stage (1,000 runs, with the explanation) takes at most
    # 3 s. It takes about 0.5 s on a laptop and 1.4 s on a slower machine, so 1 s was too tight.
    bear, wolf = load_sheet("stat-sheet.json"), load_sheet("stat-sheet-gray-wolf.json")
    start = time.perf_counter()
    run(matchup(), [bear, wolf], runs=1000)
    assert time.perf_counter() - start < 3.0


def test_zero_runs_is_a_clear_error():
    with pytest.raises(ValueError, match="at least 1"):
        run(matchup(), [load_sheet("stat-sheet.json")] * 2, runs=0)


def test_closing_events_say_who_won_without_a_bare_side_number():
    bear, wolf = load_sheet("stat-sheet.json"), load_sheet("stat-sheet-gray-wolf.json")
    last = run(matchup(), [bear, wolf], runs=50).representative_log[-1]
    assert last.type == EventType.END and not any(ch.isdigit() for ch in last.text_hint)


def test_bigger_fighter_usually_wins():
    bear, wolf = load_sheet("stat-sheet.json"), load_sheet("stat-sheet-gray-wolf.json")
    result = run(matchup(), [bear, wolf], runs=500)
    assert result.win_prob[0] > 0.9
