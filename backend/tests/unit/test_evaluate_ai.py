"""Tests for the live AI evaluation's scoring and document handling (M09, #51); no live calls."""

from types import SimpleNamespace
from typing import Any

from scripts import evaluate_ai as ev


# A stand-in intake result with the fields the scorer reads.
def result(status: str, terrain: str = "arena", fighters: tuple[tuple[str, int], ...] = ()) -> Any:
    sides = [SimpleNamespace(entity=e, count=c) for e, c in fighters]
    matchup = SimpleNamespace(terrain=SimpleNamespace(value=terrain), fighters=sides)
    return SimpleNamespace(status=status, matchup=matchup if status == "ok" else None)


CASE = {
    "name": "wolves vs moose",
    "replies": [{"fighters": []}],
    "expect": {
        "status": "ok",
        "terrain": "forest",
        "fighters": [{"entity": "wolf", "count": 3}, {"entity": "moose", "count": 1}],
    },
}


def test_a_fully_right_reading_counts_every_field() -> None:
    score = ev.IntakeScore()
    ev.score_intake_case(score, CASE, result("ok", "forest", (("wolf", 3), ("moose", 1))))
    assert (score.scored, score.status, score.full) == (1, 1, 1)
    assert score.exact == {"entity": [2, 2], "count": [2, 2], "terrain": [1, 1]}
    assert score.misses == []


def test_a_wrong_count_is_a_miss_on_that_field_only() -> None:
    score = ev.IntakeScore()
    ev.score_intake_case(score, CASE, result("ok", "forest", (("wolf", 7), ("moose", 1))))
    assert score.full == 0 and score.status == 1
    assert score.exact["count"] == [1, 2] and score.exact["entity"] == [2, 2]
    assert score.misses == ["wolves vs moose: count expected 3, got 7"]


def test_a_wrong_status_fails_the_case() -> None:
    score = ev.IntakeScore()
    ev.score_intake_case(score, CASE, result("clarify"))
    assert (score.status, score.full) == (0, 0)
    assert any("status expected ok, got clarify" in miss for miss in score.misses)


def test_a_case_built_on_broken_model_output_is_skipped() -> None:
    score = ev.IntakeScore()
    broken = {**CASE, "replies": ["not JSON", "still not JSON"]}
    ev.score_intake_case(score, broken, None)
    assert (score.scored, score.skipped) == (0, 1)


def test_the_intake_table_shows_shares() -> None:
    score = ev.IntakeScore(scored=4, status=4, full=3)
    score.exact["entity"] = [7, 8]
    text = ev.intake_markdown(score, 12.0)
    assert "| Entity exact | 7/8 (88%) |" in text
    assert "**3/4 (75%)**" in text


def test_a_rerun_replaces_only_its_own_sections() -> None:
    first = ev.render({}, {"safety": "safety v1", "intake": "intake v1"}, "2026-11-16", "abc1234")
    kept = ev.read_sections(first)
    second = ev.render(kept, {"intake": "intake v2"}, "2026-11-17", "def5678")
    sections = ev.read_sections(second)
    assert sections["safety"] == "safety v1" and sections["intake"] == "intake v2"
    assert sections["extraction"] == ev.NOT_RUN
    assert "2026-11-17 on commit `def5678`" in second
    assert [h for _, h in ev.SECTIONS if f"## {h}" in second] == [h for _, h in ev.SECTIONS]


async def test_it_refuses_to_run_in_mock_mode(capsys: Any) -> None:
    assert await ev.main(["--sections", "intake"]) == 4
    assert "PROVIDER_MODE=live" in capsys.readouterr().out


# Pretend to be in live mode with stand-in sections and a temp output file.
def live_run(monkeypatch: Any, tmp_path: Any, runners: dict[str, Any], leftover: int = 0) -> Any:
    import smoke_providers

    output = tmp_path / "evaluation.md"
    monkeypatch.setattr(ev, "OUTPUT", output)
    monkeypatch.setattr(ev, "REPO", tmp_path)
    monkeypatch.setattr(ev, "RUNNERS", runners)
    monkeypatch.setattr(ev, "get_settings", lambda: SimpleNamespace(provider_mode="live"))
    monkeypatch.setattr(smoke_providers, "redact", lambda text, _: (text, leftover))
    return output


async def test_a_failed_section_is_reported_and_the_others_are_still_written(
    monkeypatch: Any, tmp_path: Any, capsys: Any
) -> None:
    async def works() -> str:
        return "intake numbers"

    async def fails() -> str:
        raise TimeoutError("details that must not be printed")

    runners = {"intake": works, "safety": fails, "retrieval": works}
    output = live_run(monkeypatch, tmp_path, runners)
    assert await ev.main(["--sections", "safety,intake"]) == 2
    sections = ev.read_sections(output.read_text(encoding="utf-8"))
    assert sections["intake"] == "intake numbers" and sections["safety"] == ev.NOT_RUN
    out = capsys.readouterr().out
    assert "safety (TimeoutError)" in out and "must not be printed" not in out


async def test_nothing_is_written_when_the_redaction_scan_finds_a_secret(
    monkeypatch: Any, tmp_path: Any
) -> None:
    async def works() -> str:
        return "numbers"

    output = live_run(monkeypatch, tmp_path, {"intake": works}, leftover=1)
    assert await ev.main(["--sections", "intake"]) == 3
    assert not output.exists()


async def test_an_unknown_section_is_refused(capsys: Any) -> None:
    assert await ev.main(["--sections", "intake,vibes"]) == 2
    assert "vibes" in capsys.readouterr().out
