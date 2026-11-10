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
    assert "2/2 (100%)" in text and "1/1 (100%)" in text  # tuning and held-out, separately
    assert "Overall" not in text  # the two sets are never mixed into one number
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


# --- Seed sheets: the real layout, bad files, and missing sheets -------------------------------


def write_sheet(path: Path, fighter_id: str) -> None:
    data = json.loads((FIXTURES / "contracts" / "stat-sheet-gray-wolf.json").read_text("utf-8"))
    data["fighter_id"] = fighter_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_seed_sheets_are_read_from_the_fighters_folder(tmp_path):
    write_sheet(tmp_path / "fighters" / "gray-wolf.json", "gray-wolf")
    (tmp_path / "fighters.yaml").write_text("- slug: gray-wolf\n", encoding="utf-8")  # G01's list
    (tmp_path / "mythical.yaml").write_text("- not: a sheet\n", encoding="utf-8")  # G09's file
    found = bm.seed_sheets(tmp_path)
    assert found.get(FighterRequest(entity="gray-wolf", raw="wolf")).fighter_id == "gray-wolf"


def test_a_stat_sheet_in_the_wrong_place_is_not_found(tmp_path):
    write_sheet(tmp_path / "gray-wolf.json", "gray-wolf")  # top level: not where G05 puts them
    with pytest.raises(bm.BenchmarkError, match="no seed stat sheets found"):
        bm.seed_sheets(tmp_path)


def test_an_invalid_sheet_names_the_file_in_a_benchmark_error(tmp_path):
    folder = tmp_path / "fighters"
    folder.mkdir()
    (folder / "broken.json").write_text('{"fighter_id": "x"}', encoding="utf-8")
    with pytest.raises(bm.BenchmarkError, match="broken.json is not a valid stat sheet"):
        bm.seed_sheets(tmp_path)
    (folder / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(bm.BenchmarkError, match="broken.json is not a valid stat sheet"):
        bm.seed_sheets(tmp_path)


def test_a_matchup_with_a_missing_sheet_is_skipped_and_the_rest_are_scored():
    tuning = bm.load_entries(bm.MOCK_DIR / "matchups.yaml", False)
    held = bm.load_entries(bm.MOCK_DIR / "heldout.yaml", True)
    ghost = bm.Entry(
        "ghost", "obvious",
        Matchup(
            fighters=[
                FighterRequest(entity="unicorn", raw="unicorn"),
                FighterRequest(entity="grizzly-bear", raw="bear"),
            ],
            raw_text="unicorn vs bear",
        ),
        "0", "high", None, "obvious: test", False,
    )  # fmt: skip
    report = bm.run_benchmark(bm.mock_sheets(), "mock", [*tuning, ghost], held, runs=60)
    skipped = [j for j in report.judged if j.skipped]
    assert [j.entry.id for j in skipped] == ["ghost"] and "no stat sheet for 'unicorn'" in skipped[
        0
    ].reason
    text = bm.render_run(report)
    assert "Skipped (1)" in text and "ghost" in text
    assert "| Tuning | 2/2 (100%) |" in text  # pass rate over the scored matchups only


# --- Count cases: the right favorite, and the right side varied --------------------------------


def test_a_count_case_fails_when_the_fair_fight_varied_the_wrong_side():
    # Side 0 is expected to win, so the range is side 1's count; here side 0 was varied instead.
    wrong_side = FairFight(varied_side=0, count=5, win_prob_at_count=0.5, message="m")
    judged = bm.judge(
        entry("0", fair_range=(3, 10), group="count"), result("win_1", 0.1, 0.9), wrong_side
    )
    assert not judged.passed and "varied side 0" in judged.reason


def test_a_count_case_passes_only_with_the_expected_favorite_and_a_count_in_range():
    right = FairFight(varied_side=1, count=5, win_prob_at_count=0.5, message="m")
    assert bm.judge(
        entry("0", fair_range=(3, 10), group="count"), result("win_0", 0.9, 0.1), right
    ).passed
    flipped = bm.judge(
        entry("1", fair_range=(3, 10), group="count"), result("win_0", 0.9, 0.1), right
    )
    assert not flipped.passed  # side 1 was expected to win, but the search varied side 1


def test_a_count_case_says_when_the_main_fight_was_a_draw_or_no_contest():
    none = FairFight(varied_side=0, count=None, win_prob_at_count=None, message="m")
    draw = bm.judge(entry("0", fair_range=(3, 10), group="count"), result("draw", 0.0, 0.0), none)
    assert not draw.passed and "draw" in draw.reason and "no loser" in draw.reason
    nc = bm.judge(
        entry("0", fair_range=(3, 10), group="count"), result("no_contest", 0.0, 0.0), none
    )
    assert "no contest" in nc.reason


# --- Tuning only ------------------------------------------------------------------------------


def test_tuning_only_neither_runs_nor_shows_the_held_out_set():
    tuning = bm.load_entries(bm.MOCK_DIR / "matchups.yaml", False)
    held = bm.load_entries(bm.MOCK_DIR / "heldout.yaml", True)
    report = bm.run_benchmark(bm.mock_sheets(), "mock", tuning, held, runs=60, tuning_only=True)
    assert not report.subset(held_out=True)
    text = bm.render_run(report)
    assert "### Held-out set" not in text and "not run (tuning only)" in text
    assert all(
        j.entry.id not in text
        for j in bm.run_benchmark(bm.mock_sheets(), "mock", [], held, runs=60).judged
    )
