"""F02: the fight engine is deterministic, honest about uncertainty, and fast."""

import copy
import json
import time
from pathlib import Path

from app.models.matchup import FighterRequest, Matchup
from app.models.simulation import EventType, SimulationResult
from app.models.stats import StatName, StatSheet
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import DRAW, run, run_once
from app.simulation.fighters import sample_template
from app.simulation.rng import make_seed, run_rng

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


def load_sheet(name: str) -> StatSheet:
    return StatSheet.model_validate(json.loads((FIXTURES / name).read_text("utf-8")))


def matchup(count_0: int = 1, count_1: int = 1) -> Matchup:
    return Matchup(
        fighters=[
            FighterRequest(entity="a", count=count_0, raw="a"),
            FighterRequest(entity="b", count=count_1, raw="b"),
        ],
        terrain=Terrain.OPEN_FIELD,
        raw_text="a vs b",
    )


def scaled_ranges(sheet: StatSheet, factor: float) -> StatSheet:
    """Copy of a sheet with every low-high range shrunk toward its value by `factor`."""
    data = copy.deepcopy(sheet.model_dump(mode="json"))
    for stat in data["stats"].values():
        stat["low"] = stat["value"] - (stat["value"] - stat["low"]) * factor
        stat["high"] = stat["value"] + (stat["high"] - stat["value"]) * factor
    return StatSheet.model_validate(data)


def with_stat(sheet: StatSheet, name: StatName, value: float) -> StatSheet:
    data = sheet.model_dump(mode="json")
    stat = data["stats"][name.value]
    stat["value"], stat["low"], stat["high"] = value, value, value
    data["sheet_hash"] = f"{sheet.sheet_hash}-{name.value}-{value}"
    return StatSheet.model_validate(data)


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
    weaker = scaled_ranges(weaker, 1.0).model_copy()
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


def test_one_v_one_thousand_runs_finish_under_one_second():
    bear, wolf = load_sheet("stat-sheet.json"), load_sheet("stat-sheet-gray-wolf.json")
    start = time.perf_counter()
    run(matchup(), [bear, wolf], runs=1000)
    assert time.perf_counter() - start < 1.0


def test_bigger_fighter_usually_wins():
    bear, wolf = load_sheet("stat-sheet.json"), load_sheet("stat-sheet-gray-wolf.json")
    result = run(matchup(), [bear, wolf], runs=500)
    assert result.win_prob[0] > 0.9
