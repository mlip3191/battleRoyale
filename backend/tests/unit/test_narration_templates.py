"""Template scripts are valid, sync to real events, stay short, and never invent a number."""

import dataclasses
import json
import socket
from pathlib import Path

import pytest

from app.models.narration import Script
from app.models.simulation import EventType, FairFight, FightEvent, SimulationResult
from app.models.stats import StatSheet
from app.narration.facts import NarrationFacts, build_facts
from app.narration.number_guard import find_unsupported_numbers
from app.narration.templates import (
    MAX_BEATS,
    MAX_HINT,
    MAX_LINE,
    MIN_BEATS,
    _hint,
    fair_fight_line,
    fit,
    fmt,
    guarded,
    intro_script,
    outro_script,
    pick_events,
    play_by_play_script,
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
    assert "About 4 gray wolves make it a coin flip" in text and "49%" in text
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
    assert "0.03" not in text and "0.05" not in text  # sampling bounds are never quoted
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
    # The intro itself swaps in a number-free stand-in once 389 (and its roundings) is not allowed.
    values = frozenset(v for v in facts.allowed.values if abs(v - 389) > 389 * 0.01)
    narrowed = dataclasses.replace(facts, allowed=dataclasses.replace(facts.allowed, values=values))
    texts = [ln.text for ln in intro_script(narrowed).lines]
    assert not any("389" in t for t in texts)
    bear = narrowed.fighters[0].display_name
    assert f"{bear} keeps its numbers to itself." in texts
    for t in texts:
        assert find_unsupported_numbers(t, narrowed.allowed) == [], t


# Every line of every script passes the guard for these facts.
def _assert_guarded(facts: NarrationFacts, *scripts: Script) -> None:
    for script in scripts:
        for ln in script.lines:
            assert find_unsupported_numbers(ln.text, facts.allowed) == [], ln.text


# One fixture event carrying the given engine hint.
def _event_with_hint(hint: str) -> FightEvent:
    return RESULT.representative_log[0].model_copy(update={"text_hint": hint})


@pytest.mark.parametrize("hint", ["a" * 100, "word " * 30, "x" * 60 + " yy"])
def test_hint_never_exceeds_the_cap(hint: str) -> None:
    assert len(_hint(_event_with_hint(hint), "default", use_hint=True)) <= MAX_HINT
    result = _hinted(hint)
    facts = _facts("bear-vs-wolves", result)
    _, pbp, _ = template_scripts(facts, result)
    for ln in pbp.lines:
        assert "a" * (MAX_HINT + 1) not in ln.text and "x" * (MAX_HINT + 1) not in ln.text
    _assert_guarded(facts, pbp)


def test_draw_outro_says_draw_and_its_percentage() -> None:
    result = RESULT.model_copy(
        update={"outcome": "draw", "win_prob": (0.44, 0.44), "draw_prob": 0.12}
    )
    facts = _facts("bear-vs-wolves", result)
    outro = outro_script(facts)
    text = " ".join(ln.text for ln in outro.lines)
    assert "draw" in text.lower()
    assert "12%" in text
    assert "even" in text
    _assert_guarded(facts, *template_scripts(facts, result))


def test_draw_share_the_guard_rejects_gets_a_number_free_line() -> None:
    result = RESULT.model_copy(
        update={"outcome": "draw", "win_prob": (0.474, 0.473), "draw_prob": 0.053}
    )
    facts = _facts("bear-vs-wolves", result)
    outro = outro_script(facts)
    _assert_guarded(facts, outro)
    assert any("Plenty of simulated fights ended even." == ln.text for ln in outro.lines)


def test_side_zero_win_names_the_bear() -> None:
    result = RESULT.model_copy(update={"outcome": "win_0"})
    facts = _facts("bear-vs-wolves", result)
    outro = outro_script(facts)
    assert outro.lines[0].text.startswith("Your winner: Grizzly bear")
    assert f"won {facts.win_pct[0]}%" in outro.lines[1].text
    _assert_guarded(facts, outro)


def test_fair_fight_absent_says_it_did_not_run() -> None:
    a, b = MATCHUPS["bear-vs-wolves"]
    facts = build_facts([_sheet(a), _sheet(b)], RESULT, None)
    assert facts.fair_ran is False
    outro = outro_script(facts)
    texts = [ln.text for ln in outro.lines]
    assert "Want a fair fight? We didn't run the fair-fight check tonight." in texts
    assert not any("No count makes this one fair" in t for t in texts)
    _assert_guarded(facts, outro)


def test_fair_fight_that_found_no_count_says_so() -> None:
    a, b = MATCHUPS["bear-vs-wolves"]
    no_count = FAIR.model_copy(update={"count": None})
    facts = build_facts([_sheet(a), _sheet(b)], RESULT, no_count)
    assert facts.fair_ran is True and facts.fair_count is None
    outro = outro_script(facts)
    texts = [ln.text for ln in outro.lines]
    assert "Want a fair fight? No count makes this one fair." in texts
    assert not any("didn't run" in t for t in texts)
    _assert_guarded(facts, outro)


def test_fair_fight_count_without_probability_never_says_none() -> None:
    a, b = MATCHUPS["bear-vs-wolves"]
    no_prob = FAIR.model_copy(update={"win_prob_at_count": None})
    facts = build_facts([_sheet(a), _sheet(b)], RESULT, no_prob)
    assert facts.fair_count is not None and facts.fair_win_pct is None
    outro = outro_script(facts)
    texts = [ln.text for ln in outro.lines]
    assert "Want a fair fight? We have a count that makes it a coin flip." in texts
    assert not any("None%" in t or "None" in t for t in texts)
    assert not any("No count makes this one fair" in t for t in texts)
    _assert_guarded(facts, outro)


@pytest.mark.parametrize(
    ("kind", "words"),
    [
        (EventType.ATTACK, "goes on the attack"),
        (EventType.RETREAT, "backs off"),
        (EventType.FLEE, "heads for the exit"),
        (EventType.STALEMATE, "stalemate"),
    ],
)
def test_every_beat_type_validates_and_points_at_its_event(kind: EventType, words: str) -> None:
    base = RESULT.representative_log[0]
    others = [base.model_copy(update={"type": t}) for t in (EventType.APPROACH, EventType.MISS)]
    log = [*others, base.model_copy(update={"type": kind})]
    result = RESULT.model_copy(update={"representative_log": log})
    facts = _facts("bear-vs-wolves", result)
    pbp = play_by_play_script(facts, result)
    assert Script.model_validate(pbp.model_dump()) == pbp
    assert any(ln.at_event == 2 and words in ln.text for ln in pbp.lines)
    _assert_guarded(facts, pbp)


def test_large_count_uses_a_thousands_separator() -> None:
    a, b = MATCHUPS["bear-vs-wolves"]
    facts = build_facts([_sheet(a), _sheet(b)], RESULT, FAIR, counts=(1, 1000))
    scripts = template_scripts(facts, RESULT)
    text = " ".join(ln.text for s in scripts for ln in s.lines)
    assert "1,000 of them" in text
    _assert_guarded(facts, *scripts)


# Facts where the fair-fight search varied the blue side (`sheet`) to `count` fighters.
def _fair_facts(sheet: StatSheet, count: int) -> NarrationFacts:
    fair = FAIR.model_copy(update={"varied_side": 1, "count": count})
    return build_facts([_sheet("stat-sheet.json"), sheet], RESULT, fair)


# Issue #250: "About 3 of Gorilla makes it a coin flip" was broken English.
@pytest.mark.parametrize(
    ("seed", "count", "said"),
    [
        ("gorilla.json", 3, "About 3 gorillas make it a coin flip"),
        ("gray-wolf.json", 14, "About 14 gray wolves make it a coin flip"),
        ("horse.json", 2, "About 2 horses make it a coin flip"),
        ("gorilla.json", 1, "About 1 gorilla makes it a coin flip"),
    ],
)
def test_fair_fight_line_names_the_fighters_in_plain_english(
    seed: str, count: int, said: str
) -> None:
    facts = _fair_facts(_sheet(seed), count)
    text = fair_fight_line(facts, [f.display_name for f in facts.fighters]).text
    assert text == f"Want a fair fight? {said}, winning 49% of the time."
    assert find_unsupported_numbers(text, facts.allowed) == []


# The line is still number-guarded: a count that is not in the facts falls back.
def test_fair_fight_line_with_an_unsupported_count_still_falls_back() -> None:
    facts = _fair_facts(_sheet("gorilla.json"), 3)
    narrowed = dataclasses.replace(
        facts,
        allowed=dataclasses.replace(facts.allowed, values=facts.allowed.values - {3.0}),
    )
    text = fair_fight_line(narrowed).text
    assert text == "Want a fair fight? We have a count that makes it a coin flip."


def test_fmt_tiny_values_never_use_scientific_notation() -> None:
    said = fmt(2.5e-6)
    assert said == "0.0000025"
    assert "e" not in said and "E" not in said
