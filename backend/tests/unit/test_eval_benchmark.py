"""Tests for the live evaluation's benchmark section (M09 part 4, #51); no live calls."""

from datetime import datetime

from app.simulation import benchmark as bm
from scripts import eval_benchmark as eb

TUNING = bm.load_entries(bm.MOCK_DIR / "matchups.yaml", False)
HELD = bm.load_entries(bm.MOCK_DIR / "heldout.yaml", True)


# A run where every matchup passes except the ids in `failed`, and the ids in `skipped` are skipped.
def report(failed: set[str] = frozenset(), skipped: set[str] = frozenset()) -> bm.RunReport:
    judged = [
        bm.Judged(
            entry, "x", 0, (50.0, 50.0), None, entry.id not in failed, "", entry.id in skipped
        )
        for entry in [*TUNING, *HELD]
    ]
    return bm.RunReport("seed", judged, 1.0, "abc1234", datetime(2026, 11, 17))


def test_verdicts_read_pass_fail_and_skipped() -> None:
    seed = report(failed={HELD[0].id}, skipped={TUNING[0].id})
    index = {j.entry.id: j for j in seed.judged}
    assert eb.verdict(index[HELD[0].id]) == "FAIL"
    assert eb.verdict(index[TUNING[0].id]) == "skipped"
    assert eb.verdict(index[TUNING[-1].id]) == "pass"
    assert eb.verdict(None) == "skipped"


def test_the_section_compares_seed_and_research_runs() -> None:
    held_id = HELD[0].id
    text = eb.benchmark_markdown(report(), [report(failed={held_id}), report()], 42.0)
    assert "| Set | Seed sheets | Research-only, run 1 | Research-only, run 2 |" in text
    total = len(HELD)
    assert f"| **Held-out** | {total}/{total} (100%) | {total - 1}/{total} (" in text
    assert f"| {held_id} | held-out | {HELD[0].group} | pass | FAIL | pass |" in text
    assert "D-58" in text


def test_identical_runs_say_nothing_differs() -> None:
    text = eb.benchmark_markdown(report(), [report(), report()], 1.0)
    assert "- none: every matchup got the same result in every run." in text
