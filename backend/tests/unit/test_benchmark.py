"""F07: the benchmark runner scores matchups, separates the sets, and keeps its history."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from app.models.matchup import FighterRequest, Matchup
from app.models.simulation import FairFight, SimulationResult
from app.simulation import benchmark as bm
from scripts.run_benchmark import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def result(outcome: str, p0: float, p1: float) -> SimulationResult:
    """The contract fixture result with chosen win probabilities."""
    data = json.loads((FIXTURES / "contracts" / "simulation-result.json").read_text("utf-8"))
    data.update(outcome=outcome, win_prob=[p0, p1], draw_prob=round(1 - p0 - p1, 6))
    return SimulationResult.model_validate(data)


def entry(
    winner="0", confidence="high", fair_range=None, group="obvious", held_out=False
) -> bm.Entry:
    matchup = Matchup(
        fighters=[FighterRequest(entity="a", raw="a"), FighterRequest(entity="b", raw="b")],
        raw_text="a vs b",
    )
    return bm.Entry("t", group, matchup, winner, confidence, fair_range, "obvious: test", held_out)


# --- Loading ----------------------------------------------------------------------------


def test_load_accepts_a_list_or_a_matchups_mapping(tmp_path):
    raw = {
        "id": "x",
        "fighters": [{"entity": "wolf"}, {"entity": "cat", "count": 20}],
        "terrain": "forest",
        "expected_winner": 0,
        "confidence": "high",
        "source": "obvious: size",
    }
    for name, payload in (("a.yaml", [raw]), ("b.yaml", {"matchups": [raw]})):
        path = tmp_path / name
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")
        (loaded,) = bm.load_entries(path, held_out=True)
        assert loaded.id == "x" and loaded.held_out and loaded.group == "obvious"
        assert loaded.matchup.fighters[1].count == 20 and loaded.expected_winner == "0"


def test_group_is_inferred_and_fair_ranges_are_parsed():
    base = {"id": "x", "fighters": [{"entity": "a"}, {"entity": "b"}], "expected_winner": "1"}
    assert bm.parse_entry({**base, "expected_fair_count": "30-45"}, False).fair_range == (30, 45)
    ranged = bm.parse_entry({**base, "expected_fair_count": {"min": 3, "max": 9}}, False)
    assert ranged.group == "count"
    assert (
        bm.parse_entry({**base, "source": "https://example.org/zoo"}, False).group == "documented"
    )
    assert bm.parse_entry({**base, "group": "documented"}, False).group == "documented"


def test_malformed_entries_and_missing_files_give_clear_errors(tmp_path):
    with pytest.raises(bm.BenchmarkError, match="malformed"):
        bm.parse_entry({"id": "x", "fighters": [{"entity": "a"}, {"entity": "b"}]}, False)
    with pytest.raises(bm.BenchmarkError, match="G07"):
        bm.load_entries(tmp_path / "missing.yaml", False)


# --- Pass rules -------------------------------------------------------------------------


def test_favorite_must_match_the_expected_winner():
    assert bm.judge(entry("0"), result("win_0", 0.9, 0.1), None).passed
    wrong = bm.judge(entry("0"), result("win_1", 0.1, 0.9), None)
    assert not wrong.passed and "expected side 0" in wrong.reason


def test_high_confidence_needs_the_favorite_at_seventy_percent():
    assert not bm.judge(entry("1", "high"), result("win_1", 0.38, 0.55), None).passed
    assert bm.judge(entry("1", "medium"), result("win_1", 0.38, 0.55), None).passed
    assert bm.judge(entry("1", "high"), result("win_1", 0.2, 0.7), None).passed


def test_expected_draw_needs_a_draw_and_no_contest_has_no_favorite():
    assert bm.judge(entry("draw"), result("draw", 0.0, 0.0), None).passed
    assert not bm.judge(entry("draw"), result("win_0", 0.8, 0.1), None).passed
    nothing = bm.judge(entry("0"), result("no_contest", 0.0, 0.0), None)
    assert nothing.favorite is None and not nothing.passed


def test_count_cases_pass_on_the_fair_fight_range():
    fair = FairFight(varied_side=1, count=37, win_prob_at_count=0.5, message="m")
    main_result = result("win_0", 0.9, 0.1)
    inside = bm.judge(entry(fair_range=(30, 45), group="count"), main_result, fair)
    assert inside.passed and inside.fair_count == 37
    assert not bm.judge(entry(fair_range=(5, 20), group="count"), main_result, fair).passed
    none = FairFight(varied_side=1, count=None, win_prob_at_count=None, message="m")
    assert not bm.judge(entry(fair_range=(5, 20), group="count"), main_result, none).passed


# --- The report -------------------------------------------------------------------------


def run_report(mode="mock") -> bm.RunReport:
    sheets = bm.mock_sheets()
    tuning = bm.load_entries(bm.MOCK_DIR / "matchups.yaml", False)
    held = bm.load_entries(bm.MOCK_DIR / "heldout.yaml", True)
    return bm.run_benchmark(sheets, mode, tuning, held, runs=100)


def test_report_shows_tuning_and_held_out_separately_with_commit_and_runtime():
    text = bm.render_run(run_report())
    assert "| Tuning | 2/2 (100%) |" in text
    assert "Held-out (never used to change constants) | 1/1 (100%)" in text
    assert "### Tuning set" in text and "### Held-out set" in text
    assert "traceability n/a" in text and "runtime" in text and "Commit `" in text
    assert text.startswith("## Run 20")  # the date is in the heading


def test_new_runs_go_on_top_and_only_the_last_five_are_kept(tmp_path):
    out = tmp_path / "results.md"
    report = run_report()
    start = datetime(2026, 11, 1, 12, 0)
    for day in range(7):
        report.started = start + timedelta(days=day)
        bm.write_report(out, report)
    lines = out.read_text("utf-8").splitlines()
    headings = [line for line in lines if line.startswith("## Run")]
    assert len(headings) == bm.KEEP_RUNS
    assert headings[0].startswith("## Run 2026-11-07")
    assert headings[-1].startswith("## Run 2026-11-03")


def test_a_second_run_keeps_the_first_below_it(tmp_path):
    out = tmp_path / "results.md"
    first, second = run_report("seed"), run_report("research")
    first.started, second.started = datetime(2026, 11, 8, 9, 0), datetime(2026, 11, 9, 9, 0)
    bm.write_report(out, first)
    bm.write_report(out, second)
    text = out.read_text("utf-8")
    assert text.index("sheets: research") < text.index("sheets: seed")
    assert text.count("# Benchmark results") == 1


# --- The runner (the CI check that it cannot silently break) ----------------------------


def test_mock_mode_runs_three_matchups_end_to_end(tmp_path, capsys):
    out = tmp_path / "results.md"
    assert main(["--mock", "--output", str(out)]) == 0
    text = out.read_text("utf-8")
    assert text.count("| mock-") == 3  # three matchups scored
    assert "3/3 (100%)" in text
    assert "mock-wolves-to-match-a-bear" in capsys.readouterr().out


def test_mock_mode_does_not_touch_the_docs_file_by_default():
    before = bm.RESULTS_FILE.read_bytes() if bm.RESULTS_FILE.exists() else None
    assert main(["--mock"]) == 0
    after = bm.RESULTS_FILE.read_bytes() if bm.RESULTS_FILE.exists() else None
    assert before == after


def test_live_modes_say_what_they_are_waiting_for(tmp_path, capsys):
    assert main(["--live", "--matchups", str(tmp_path / "nope.yaml")]) == 2
    assert "G07" in capsys.readouterr().err
    mock_files = ["--matchups", str(bm.MOCK_DIR / "matchups.yaml")]
    mock_files += ["--heldout", str(bm.MOCK_DIR / "heldout.yaml")]
    assert main(["--live", "--sheets", "research", *mock_files]) == 2
    assert "G04" in capsys.readouterr().err


def test_unknown_fighter_is_a_clear_error():
    with pytest.raises(bm.BenchmarkError, match="no stat sheet for 'unicorn'"):
        bm.mock_sheets().get(FighterRequest(entity="unicorn", raw="unicorn"))
