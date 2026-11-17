"""Shared by the safety-case tests: load tests/fixtures/safety_cases.yaml and run one case through
parse_matchup on mocks (stand-in chat model from the case's mock block, mock Wikidata, and the
test's temp cache from tests/conftest.py). Not a test module, so pytest does not collect it."""

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.intake import parser
from app.intake.llm_io import INPUT_END, INPUT_START, as_data
from app.intake.parser import parse_matchup, typed_sides
from app.intake.rules import normalize_entity
from app.models.matchup import IntakeResult
from app.providers.base import ChatMessage
from app.safety.classify import PROMPT_NAME as SAFETY_PROMPT
from app.safety.verdict import SafetyVerdict, blocked_result

CASES_PATH = Path(__file__).parents[1] / "fixtures" / "safety_cases.yaml"


@dataclass(frozen=True)
class SafetyCase:
    """One entry of safety_cases.yaml (see the file's header for each field)."""

    id: str
    text: str
    expect: str
    kind: str
    reason: str | None = None
    layer: str | None = None
    clean: str | None = None
    mock: dict[str, Any] = field(default_factory=dict)


# Every case in file order.
@cache
def load_cases() -> tuple[SafetyCase, ...]:
    data = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    return tuple(SafetyCase(**entry) for entry in data["cases"])


# Cases by id.
def cases_by_id() -> dict[str, SafetyCase]:
    return {case.id: case for case in load_cases()}


# The stand-in parse reply: the case's mock sides, else the text split on "vs".
def parse_reply(case: SafetyCase) -> dict[str, Any]:
    sides = case.mock.get("sides") or [
        [raw, normalize_entity(raw) or raw.lower()] for raw in typed_sides(case.text)
    ]
    fighters = [
        {"raw": s[0], "entity": s[1], "variant": s[2] if len(s) > 2 else None} for s in sides
    ]
    return {"fighters": fighters, "assumptions": case.mock.get("assumptions", [])}


class CaseModel:
    """Stand-in chat model for one case: the parse reply above; the classifier answers the
    case's `classifier` verdict for the user's text and `classifier_sides` for anything else
    (the second pass on the model's reading)."""

    def __init__(self, case: SafetyCase) -> None:
        self.case = case
        self.calls: dict[str, int] = {}

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        prompt_name: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        self.calls[prompt_name] = self.calls.get(prompt_name, 0) + 1
        text = messages[1]["content"].removeprefix(f"{INPUT_START}\n")
        text = text.removesuffix(f"\n{INPUT_END}")
        if prompt_name == SAFETY_PROMPT:
            key = "classifier" if text == as_data(self.case.text) else "classifier_sides"
            return json.dumps({"verdict": self.case.mock.get(key, "allowed")})
        return json.dumps(parse_reply(self.case))


# Run one case on mocks; returns the result and the layer that blocked it (None if not blocked).
async def run_case(
    case: SafetyCase, monkeypatch: pytest.MonkeyPatch
) -> tuple[IntakeResult, str | None]:
    seen: list[SafetyVerdict] = []

    def recording(verdict: SafetyVerdict) -> IntakeResult:
        seen.append(verdict)
        return blocked_result(verdict)

    monkeypatch.setattr(parser, "blocked_result", recording)
    model = CaseModel(case)
    result = await parse_matchup(case.text, chat=model, safety_chat=model)
    return result, (seen[-1].layer if seen else None)
