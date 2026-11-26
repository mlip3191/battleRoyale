"""#351: when the results page says no single factor decided the fight, the announcer does not
name one, in the template outro, in the model's placeholders and in the fact list."""

import json
from pathlib import Path

import pytest

from app.models.simulation import FairFight, SimulationResult
from app.models.stats import StatSheet
from app.narration.facts import NarrationFacts, build_facts, fact_lines
from app.narration.templates import outro_script
from app.narration.writer import (
    ScriptRejected,
    outro_placeholders,
    read_reply,
    required_placeholders,
)
from app.simulation.decide import names_a_factor

CONTRACTS = Path(__file__).parents[1] / "fixtures" / "contracts"
DECIDED = "Strength decided it: Gorilla (3420 N) against Roman legionary (150 N)."
TOO_CLOSE = "Too close to call: no single stat or circumstance made a clear difference."
COMFORTABLE = "Gray wolf wins comfortably: no single stat or circumstance was decisive."
UNTESTED = "Not every factor could be tested for a fight this big."
STALEMATE = "A stalemate: neither side could finish the other before the time limit."


def _json(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _facts(explainer: str) -> NarrationFacts:
    sheets = [
        StatSheet.model_validate(_json("stat-sheet.json")),
        StatSheet.model_validate(_json("stat-sheet-gray-wolf.json")),
    ]
    result = SimulationResult.model_validate(_json("simulation-result.json"))
    result = result.model_copy(update={"deciding_factor_explainer": explainer})
    return build_facts(sheets, result, FairFight.model_validate(_json("fair-fight.json")))


@pytest.mark.parametrize(
    ("explainer", "decided"),
    [
        (DECIDED, True),
        (TOO_CLOSE, False),
        (COMFORTABLE, False),
        (UNTESTED, False),
        (STALEMATE, False),
        ("No contest: neither a nor b can hurt the other.", False),
    ],
)
def test_which_explainers_name_a_factor(explainer: str, decided: bool) -> None:
    assert names_a_factor(explainer) is decided
    assert _facts(explainer).factor_decided is decided


def test_a_decided_fight_still_names_its_factor_everywhere() -> None:
    facts = _facts(DECIDED)
    texts = [line.text for line in outro_script(facts).lines]
    assert any(text.startswith("The deciding factor:") for text in texts)
    assert "deciding_factor" in outro_placeholders(facts)
    assert ("deciding_factor",) in required_placeholders(facts)
    assert "deciding factor: none" not in " ".join(fact_lines(facts))


@pytest.mark.parametrize("explainer", [TOO_CLOSE, COMFORTABLE, UNTESTED])
def test_an_undecided_fight_never_names_a_factor(explainer: str) -> None:
    facts = _facts(explainer)
    texts = [line.text for line in outro_script(facts).lines]
    assert not any("deciding factor:" in text.lower() for text in texts)
    assert "No single factor decided this one." in texts
    assert "deciding_factor" not in outro_placeholders(facts)
    assert ("deciding_factor",) not in required_placeholders(facts)
    text = " ".join(fact_lines(facts))
    assert "deciding factor: no single factor decided it;" in text
    assert "none (" not in text  # the shorthand a model once copied into the outro (#620)


def test_a_model_outro_cannot_use_the_factor_placeholder_when_undecided() -> None:
    facts = _facts(UNTESTED)
    lines = [
        {"speaker": "announcer", "text": "Winner: {winner}, {win_pct}."},
        {"speaker": "announcer", "text": "The deciding factor: {deciding_factor}."},
        {"speaker": "announcer", "text": "{fair_fight}"},
        {"speaker": "announcer", "text": "Good night."},
    ]
    with pytest.raises(ScriptRejected):
        read_reply("outro", {"lines": lines}, facts, 0)
