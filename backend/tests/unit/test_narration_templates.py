"""Template scripts are valid, sync to real events, stay short, and never invent a number."""

import json
import socket
from pathlib import Path

import pytest

from app.models.narration import Script
from app.models.simulation import FairFight, SimulationResult
from app.models.stats import StatSheet
from app.narration.facts import NarrationFacts, build_facts
from app.narration.number_guard import find_unsupported_numbers
from app.narration.templates import (
    MAX_BEATS,
    MAX_LINE,
    MIN_BEATS,
    fit,
    fmt,
    guarded,
    pick_events,
    template_scripts,
)

CONTRACTS = Path(__file__).parents[1] / "fixtures" / "contracts"
SEED = Path(__file__).parents[3] / "data" / "seed" / "fighters"


# Load a JSON file.
def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# A stat sheet from the contract fixtures or the seed fighters.
def _sheet(name: str) -> StatSheet:
    path = CONTRACTS / name if name.startswith("stat-sheet") else SEED / name
    return StatSheet.model_validate(_json(path))


RESULT = SimulationResult.model_validate(_json(CONTRACTS / "simulation-result.json"))
FAIR = FairFight.model_validate(_json(CONTRACTS / "fair-fight.json"))

# Matchups: an animal fight, an object, a mythical creature, and two seed fighters.
MATCHUPS = {
    "bear-vs-wolves": ("stat-sheet.json", "stat-sheet-gray-wolf.json"),
    "toaster-vs-wolves": ("stat-sheet-toaster.json", "stat-sheet-gray-wolf.json"),
    "dragon-vs-bear": ("stat-sheet-dragon.json", "stat-sheet.json"),
    "crocodile-vs-elephant": ("saltwater-crocodile.json", "african-elephant.json"),
    "duck-vs-horse": ("duck.json", "horse.json"),
}


# A copy of the fixture result with only the first n events in the log.
def _short_result(n: int) -> SimulationResult:
    return RESULT.model_copy(update={"representative_log": RESULT.representative_log[:n]})


# A copy of the fixture result with a long log (the fixture log repeated).
def _long_result(repeats: int) -> SimulationResult:
    return RESULT.model_copy(update={"representative_log": RESULT.representative_log * repeats})


# Facts for one named matchup.
def _facts(key: str, result: SimulationResult = RESULT) -> NarrationFacts:
    a, b = MATCHUPS[key]
    return build_facts([_sheet(a), _sheet(b)], result, FAIR)


# Block every socket, so any network call fails the test.
@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("narration templates must not touch the network")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.mark.parametrize("key", list(MATCHUPS))
def test_scripts_validate_and_are_fallbacks(key: str) -> None:
    scripts = template_scripts(_facts(key), RESULT)
    assert [s.kind for s in scripts] == ["intro", "play_by_play", "outro"]
    for script in scripts:
        assert Script.model_validate(script.model_dump()) == script
        assert script.fallback is True


@pytest.mark.parametrize("key", list(MATCHUPS))
def test_every_number_passes_the_guard(key: str) -> None:
    facts = _facts(key)
    for script in template_scripts(facts, RESULT):
        for line in script.lines:
            assert find_unsupported_numbers(line.text, facts.allowed) == [], line.text


@pytest.mark.parametrize("key", list(MATCHUPS))
def test_lengths_and_counts(key: str) -> None:
    intro, pbp, outro = template_scripts(_facts(key), RESULT)
    assert 4 <= len(intro.lines) <= 8
    assert MIN_BEATS <= len(pbp.lines) <= MAX_BEATS
    assert outro.lines
    for script in (intro, pbp, outro):
        assert all(len(line.text) <= MAX_LINE for line in script.lines)


@pytest.mark.parametrize("n_events", [1, 3, 12, 60])
def test_play_by_play_points_at_real_events(n_events: int) -> None:
    result = _short_result(n_events) if n_events <= 12 else _long_result(5)
    _, pbp, _ = template_scripts(_facts("bear-vs-wolves", result), result)
    log_len = len(result.representative_log)
    assert MIN_BEATS <= len(pbp.lines) <= MAX_BEATS
    indices = [line.at_event for line in pbp.lines]
    assert all(i is not None and 0 <= i < log_len for i in indices)
    assert indices == sorted(indices)


def test_three_event_log_reuses_real_events() -> None:
    indices = pick_events(_short_result(3).representative_log)
    assert len(indices) == MIN_BEATS
    assert set(indices) == {0, 1, 2}


def test_long_log_keeps_first_last_and_knockouts() -> None:
    log = _long_result(5).representative_log
    indices = pick_events(log)
    assert len(indices) == MAX_BEATS
    assert indices[0] == 0 and indices[-1] == len(log) - 1
    assert any(log[i].type == "ko" for i in indices)


def test_empty_log_still_gives_min_beats_without_events() -> None:
    result = RESULT.model_copy(update={"representative_log": [], "outcome": "no_contest"})
    _, pbp, outro = template_scripts(_facts("bear-vs-wolves", result), result)
    assert len(pbp.lines) == MIN_BEATS
    assert all(line.at_event is None for line in pbp.lines)
    assert "No contest" in outro.lines[0].text


def test_dragon_gets_legend_line_and_estimates() -> None:
    intro, _, _ = template_scripts(_facts("dragon-vs-bear"), RESULT)
    legend = [line.text for line in intro.lines if "according to legend" in line.text.lower()]
    assert legend
    assert "estimate" in legend[0].lower()


def test_estimated_stats_are_called_estimates() -> None:
    intro, _, _ = template_scripts(_facts("dragon-vs-bear"), RESULT)
    text = " ".join(line.text for line in intro.lines)
    assert "an estimated 6,000 kilograms" in text


def test_non_mythical_fighters_get_no_legend_line() -> None:
    intro, _, _ = template_scripts(_facts("bear-vs-wolves"), RESULT)
    assert not any("legend" in line.text.lower() for line in intro.lines)


def test_outro_fills_numbers_from_the_result() -> None:
    _, _, outro = template_scripts(_facts("bear-vs-wolves"), RESULT)
    text = " ".join(line.text for line in outro.lines)
    assert "Gray wolf, 6 of them" in text
    assert "55% of 1,000 simulated fights" in text
    assert "About 4 of Gray wolf" in text and "49%" in text
    assert "numbers" in text


def test_fmt_and_fit() -> None:
    assert fmt(6000.0) == "6,000"
    assert fmt(43.2) == "43.2"
    assert fmt(1.0) == "1"
    long_text = "word " * 100
    assert len(fit(long_text)) <= MAX_LINE


@pytest.mark.parametrize(("value", "said"), [(0.04, "0.04"), (0.012, "0.012"), (0.5, "0.5")])
def test_fmt_never_rounds_small_values_to_zero(value: float, said: str) -> None:
    assert fmt(value) == said


def test_small_stat_is_said_and_passes_the_guard() -> None:
    small = _sheet("stat-sheet.json")
    mass = small.stats["mass_kg"].model_copy(update={"value": 0.04, "low": 0.03, "high": 0.05})
    small = small.model_copy(update={"stats": {**small.stats, "mass_kg": mass}})
    facts = build_facts([small, _sheet("stat-sheet-gray-wolf.json")], RESULT, FAIR)
    intro, _, _ = template_scripts(facts, RESULT)
    text = " ".join(line.text for line in intro.lines)
    assert "weighs in at 0.04 kilograms (0.088 pounds)" in text
    for line in intro.lines:
        assert find_unsupported_numbers(line.text, facts.allowed) == [], line.text


def test_fit_shortens_a_long_name_and_keeps_the_closing_sentence() -> None:
    dragon = _sheet("stat-sheet-dragon.json")
    long_name = "Dragon of the far northern frozen mountain peaks beyond the sea"[:60].strip()
    dragon = dragon.model_copy(update={"display_name": long_name})
    intro, _, _ = template_scripts(build_facts([dragon, _sheet("stat-sheet.json")], RESULT), RESULT)
    tape = next(ln.text for ln in intro.lines if "according to legend" in ln.text)
    assert long_name not in tape  # the full name did not fit, so it was shortened
    assert len(tape) <= MAX_LINE
    assert tape.endswith("Legend numbers are estimates.")
    assert tape.startswith("Dragon")


def test_fit_leaves_short_lines_and_other_text_alone() -> None:
    assert fit("Gray wolf closes in.", ["Gray wolf"]) == "Gray wolf closes in."


# A copy of the fixture result whose events all carry one engine hint.
def _hinted(hint: str) -> SimulationResult:
    log = [e.model_copy(update={"text_hint": hint}) for e in RESULT.representative_log]
    return RESULT.model_copy(update={"representative_log": log})


@pytest.mark.parametrize("hint", ["seven quick bites", "eleven swipes", "hundreds of jabs"])
def test_hint_with_an_invented_number_falls_back_to_the_default(hint: str) -> None:
    result = _hinted(hint)
    facts = _facts("bear-vs-wolves", result)
    _, pbp, _ = template_scripts(facts, result)
    texts = [line.text for line in pbp.lines]
    assert not any(hint in t for t in texts)
    assert any("a solid hit" in t or "here it comes" in t for t in texts)
    for t in texts:
        assert find_unsupported_numbers(t, facts.allowed) == [], t


def test_clean_hint_is_kept() -> None:
    result = _hinted("a big swipe")
    _, pbp, _ = template_scripts(_facts("bear-vs-wolves", result), result)
    assert any("a big swipe" in line.text for line in pbp.lines)


def test_template_line_with_one_invented_digit_falls_back() -> None:
    facts = _facts("bear-vs-wolves")
    intro, _, _ = template_scripts(facts, RESULT)
    real = next(ln.text for ln in intro.lines if "389" in ln.text)
    invented = real.replace("389", "387")
    assert guarded(real, "safe", facts.allowed) == real
    assert guarded(invented, "safe", facts.allowed) == "safe"
