"""Tests for the live evaluation's cost and speed scoring (M09 part 3, #51); no live calls."""

from collections import Counter

from scripts import eval_cost as ec


def test_percentiles_use_the_nearest_rank() -> None:
    values = [3.0, 1.0, 2.0, 5.0, 4.0]
    assert ec.percentile(values, 50) == 3.0
    assert ec.percentile(values, 90) == 5.0
    assert ec.percentile([], 50) is None


def run(title: str, repeat: bool, verdict: float, show: float, **calls: int) -> ec.BattleRun:
    return ec.BattleRun(title, repeat, "done", verdict, show, cached=repeat, calls=Counter(calls))


def test_the_section_shows_times_calls_and_cache_hits() -> None:
    runs = [
        run("A vs B", False, 4.0, 40.0, chat=6, embedder=2),
        run("C vs D", False, 6.0, 60.0, chat=8, embedder=4),
        run("A vs B", True, 1.0, 20.0, chat=3),
        run("C vs D", True, 2.0, 30.0, chat=3),
    ]
    text = ec.cost_markdown(runs, 150.0)
    assert "| A vs B | repeat (cached) | done | 1.0 s | 20.0 s | 3 | 0 |" in text
    assert "| Median time to verdict | 4.0 s | 1.0 s |" in text
    assert "| 90th percentile time to full show | 60.0 s | 30.0 s |" in text
    assert "| Calls per battle: chat | 7.0 | |" in text
    assert "| Repeat battles answered from the cache | | 2 of 2 |" in text


def test_a_battle_with_no_verdict_shows_a_dash() -> None:
    timed_out = ec.BattleRun("E vs F", False, "timed out", None, 300.0)
    text = ec.cost_markdown([timed_out, ec.BattleRun("E vs F", True)], 300.0)
    assert "| E vs F | fresh | timed out | - | 300.0 s |" in text
