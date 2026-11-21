"""The outro says "near coin flip" when the verdict card says "too close to call" (#482).

The rule matches the front end's isTooCloseToCall: the winner's 95% low end, rounded to a whole
percent, is 50 or less. The boundary pair is 0.504 (too close) and 0.506 (a clear win).
"""

import json
import re
from typing import Any

import pytest

from app.models.simulation import SimulationResult
from app.narration.facts import NarrationFacts, build_facts
from app.narration.templates import template_scripts
from app.narration.writer import ScriptRejected, _task_lines, read_reply, required_placeholders
from tests.narration_samples import Sample, samples

SAMPLE: Sample = {s.key: s for s in samples()}["grizzly-vs-gorilla"]
CROWNS = re.compile(r"\bwinner\b|takes the win|\bwon\b|\bwins\b", re.I)


# The sample result with the winner's 95% low end set (the high end stays above it).
def _result(low: float, outcome: str | None = None) -> SimulationResult:
    result = SAMPLE.result
    outcome = outcome or result.outcome
    ci = [list(pair) for pair in result.win_prob_ci95]
    if outcome in ("win_0", "win_1"):
        ci[int(outcome[-1])] = [low, min(low + 0.06, 1.0)]
    return result.model_copy(update={"outcome": outcome, "win_prob_ci95": ci})


def _facts(low: float, outcome: str | None = None) -> NarrationFacts:
    result = _result(low, outcome)
    return build_facts(SAMPLE.sheets, result, SAMPLE.fair, SAMPLE.counts)


@pytest.mark.parametrize(("low", "expected"), [(0.504, True), (0.506, False), (0.5, True)])
def test_the_too_close_fact_matches_the_front_end_boundary(low: float, expected: bool) -> None:
    assert _facts(low).too_close is expected


def test_a_draw_is_never_too_close() -> None:
    assert _facts(0.45, "draw").too_close is False


def _outro_text(low: float) -> str:
    facts = _facts(low)
    outro = template_scripts(facts, _result(low))[2]
    return " ".join(line.text for line in outro.lines)


def test_the_template_outro_calls_a_close_one_a_near_coin_flip() -> None:
    text = _outro_text(0.504)
    assert "coin flip" in text.lower() and "slight edge" in text.lower()
    assert not CROWNS.search(text)


def test_the_template_outro_still_crowns_a_clear_winner() -> None:
    text = _outro_text(0.506)
    assert "Your winner" in text and "slight edge" not in text.lower()


def test_the_close_outro_only_uses_numbers_from_the_results() -> None:
    facts = _facts(0.504)
    outro = template_scripts(facts, _result(0.504))[2]
    pct = facts.win_pct[int(facts.outcome[-1])]
    assert f"{pct}%" in " ".join(line.text for line in outro.lines)


def test_the_model_outro_does_not_have_to_use_the_winner_when_too_close() -> None:
    close = [name for group in required_placeholders(_facts(0.504)) for name in group]
    clear = [name for group in required_placeholders(_facts(0.506)) for name in group]
    assert "winner" not in close and "win_pct" in close
    assert "winner" in clear


# A model outro reply, one line per text.
def _reply(*texts: str) -> str:
    speakers = ["announcer", "color_commentator"]
    lines: list[dict[str, Any]] = [
        {"speaker": speakers[i % 2], "text": t} for i, t in enumerate(texts)
    ]
    return json.dumps({"lines": lines})


CLOSE_OUTRO = (
    "Folks, that was a near coin flip!",
    "{winner} had the slight edge, ahead {win_pct} of the time.",
    "It came down to {deciding_factor}, and barely.",
    "{fair_fight}",
    "That's all from the arena. Good night, everybody!",
)


def test_a_close_outro_that_crowns_a_winner_is_rejected() -> None:
    facts = _facts(0.504)
    bad = _reply(
        "Your winner: {winner}!",
        "{winner} won {win_pct} of the time.",
        "It came down to {deciding_factor}.",
        "{fair_fight}",
        "Good night, everybody!",
    )
    with pytest.raises(ScriptRejected, match="too close"):
        read_reply("outro", bad, facts, len(_result(0.504).representative_log))


def test_a_close_outro_that_names_a_slight_edge_is_accepted() -> None:
    facts = _facts(0.504)
    script = read_reply(
        "outro", _reply(*CLOSE_OUTRO), facts, len(_result(0.504).representative_log)
    )
    assert script.fallback is False
    assert not CROWNS.search(" ".join(line.text for line in script.lines))


# The model's task text says so when the verdict is too close, and not when it is a clear win.
def test_the_task_text_tells_the_model_when_it_is_too_close() -> None:
    log = _result(0.504).representative_log
    close = " ".join(_task_lines("outro", _facts(0.504), log))
    clear = " ".join(_task_lines("outro", _facts(0.506), log))
    assert "TOO CLOSE TO CALL" in close and "slight edge" in close
    assert "not a winner" in close  # the softened placeholder help
    assert "TOO CLOSE TO CALL" not in clear and "not a winner" not in clear
