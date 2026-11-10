"""parse_matchup on mocks: the 25+ intake cases, code overriding the model, and the retry (A02)."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.config import REPO_ROOT
from app.intake.parser import (
    INPUT_END,
    INPUT_START,
    PROMPT_NAME,
    load_prompt,
    parse_matchup,
    typed_sides,
)
from app.models.matchup import IntakeResult
from app.models.terrain import Terrain
from app.providers.base import ChatMessage
from app.providers.live.http import ProviderError
from app.providers.registry import get_provider

CASES_PATH = REPO_ROOT / "backend" / "tests" / "fixtures" / "providers" / "intake_cases.yaml"
CASES: list[dict[str, Any]] = yaml.safe_load(Path(CASES_PATH).read_text(encoding="utf-8"))


class CannedChat:
    """Stand-in chat model: replies come from a list per user text, in call order."""

    def __init__(self, replies: dict[str, list[Any]]) -> None:
        self.replies = replies
        self.calls: list[list[ChatMessage]] = []

    # The user's text, unwrapped from the data markers in the first user message.
    @staticmethod
    def user_text(messages: list[ChatMessage]) -> str:
        content = messages[1]["content"]
        return content.removeprefix(f"{INPUT_START}\n").removesuffix(f"\n{INPUT_END}")

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        prompt_name: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        assert prompt_name == PROMPT_NAME and json_schema is not None
        self.calls.append(messages)
        replies = self.replies[self.user_text(messages)]
        reply = replies[min(len(self.calls), len(replies)) - 1]
        return reply if isinstance(reply, str) else json.dumps(reply)


class FailingChat:
    """Stand-in chat model whose endpoint is down."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages: list[ChatMessage], **_: Any) -> str:
        self.calls += 1
        raise ProviderError("chat endpoint unavailable")


# Check one result against a case's expectations (only the keys the case lists).
def check(result: IntakeResult, expect: dict[str, Any]) -> None:
    assert result.status == expect["status"], result
    notes = " | ".join(result.matchup.assumptions if result.matchup else []).lower()
    if "terrain" in expect:
        assert result.matchup is not None and result.matchup.terrain == Terrain(expect["terrain"])
    if "fighters" in expect:
        assert result.matchup is not None
        pairs = zip(result.matchup.fighters, expect["fighters"], strict=True)
    else:
        pairs = zip([], [], strict=True)
    for got, want in pairs:
        for field, value in want.items():
            assert getattr(got, field) == value, (field, got)
    for text in expect.get("assumptions_include", []):
        assert text.lower() in notes, (text, notes)
    if expect.get("no_assumptions"):
        assert notes == ""
    if "options_count" in expect:
        assert len(result.options) == expect["options_count"], result.options
    for option in expect.get("options_include", []):
        assert option in result.options, (option, result.options)
    for text in expect.get("question_include", []):
        assert result.question is not None and text.lower() in result.question.lower()
    for text in expect.get("message_include", []):
        assert result.message is not None and text.lower() in result.message.lower()
    if result.status == "clarify":
        assert result.matchup is None and result.question and 2 <= len(result.options) <= 4
    if result.status == "ok":
        assert result.matchup is not None and len(result.matchup.fighters) == 2


def test_there_are_at_least_25_cases_with_unique_texts() -> None:
    texts = [case["text"] for case in CASES]
    assert len(CASES) >= 25 and len(set(texts)) == len(texts)


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
async def test_intake_case(case: dict[str, Any]) -> None:
    chat = CannedChat({case["text"]: case["replies"]})
    result = await parse_matchup(case["text"], chat=chat)
    check(result, case["expect"])
    if "calls" in case["expect"]:
        assert len(chat.calls) == case["expect"]["calls"]
    if result.matchup:
        assert result.matchup.raw_text == case["text"]


async def test_code_overrides_wrong_model_output() -> None:
    text = "3 duck-sized wolves vs a moose in the forest"
    wrong = {
        "fighters": [
            {"raw": "3 duck-sized wolves", "entity": "Wolves", "count": 7, "size_reference": 2.5},
            {"raw": "a moose", "entity": "moose", "count": 40, "size_reference": "10"},
        ],
        "terrain": "volcano",
    }
    result = await parse_matchup(text, chat=CannedChat({text: [wrong]}))
    assert result.status == "ok" and result.matchup is not None
    wolf, moose = result.matchup.fighters
    assert (wolf.entity, wolf.count, wolf.size_reference) == (
        "wolf",
        3,
        "duck",
    )  # plural, count, size
    assert (moose.count, moose.size_reference) == (1, None)  # wrong count, numeric size
    assert result.matchup.terrain == Terrain.ARENA  # unknown terrain
    assert any("volcano" in note for note in result.matchup.assumptions)


async def test_invalid_output_retries_once_with_the_error_then_asks_to_rephrase() -> None:
    text = "a shark vs a squid"
    chat = CannedChat({text: ["not JSON", "still not JSON"]})
    result = await parse_matchup(text, chat=chat)
    assert result.status == "clarify" and "another way" in (result.question or "")
    assert len(chat.calls) == 2
    retry = chat.calls[1]
    assert retry[:2] == chat.calls[0][:2]
    assert retry[2] == {"role": "assistant", "content": "not JSON"}
    assert retry[3]["role"] == "user" and "not valid JSON" in retry[3]["content"]


async def test_endpoint_down_retries_once_then_asks_to_rephrase() -> None:
    chat = FailingChat()
    result = await parse_matchup("a lion vs a tiger", chat=chat)
    assert result.status == "clarify" and chat.calls == 2


@pytest.mark.parametrize("text", ["", "   "])
async def test_empty_text_asks_without_calling_the_model(text: str) -> None:
    chat = FailingChat()
    result = await parse_matchup(text, chat=chat)
    assert result.status == "clarify" and chat.calls == 0


async def test_very_long_text_asks_for_a_shorter_version_without_calling_the_model() -> None:
    chat = FailingChat()
    result = await parse_matchup("a wolf vs a moose " * 40, chat=chat)
    assert result.status == "clarify" and chat.calls == 0


async def test_the_real_mock_provider_parses_its_default_reply() -> None:
    result = await parse_matchup(
        "a grizzly bear vs 6 gray wolves in a forest", chat=get_provider("chat")
    )
    assert result.status == "ok" and result.matchup is not None
    bear, wolves = result.matchup.fighters
    assert (bear.entity, bear.variant, wolves.entity, wolves.count) == (
        "grizzly bear",
        "adult male",
        "gray wolf",
        6,
    )
    assert result.matchup.terrain == Terrain.FOREST


async def test_parse_matchup_uses_the_registry_provider_by_default() -> None:
    result = await parse_matchup("a grizzly bear vs 6 gray wolves in a forest")
    assert result.status == "ok"


@pytest.mark.parametrize(
    ("text", "sides"),
    [
        ("a dragon vs a main battle tank", ["a dragon", "a main battle tank"]),
        ("a toaster VS. a goose", ["a toaster", "a goose"]),
        ("a wolf versus a bear against a moose", ["a wolf", "a bear", "a moose"]),
        ("a horse v. a goat", ["a horse", "a goat"]),
        ("bear", ["bear"]),
        ("a grizzly bear vs", ["a grizzly bear vs"]),
    ],
)
def test_typed_sides_splits_on_vs_words(text: str, sides: list[str]) -> None:
    assert typed_sides(text) == sides


# Regression for the live check: the model dropped the tank; the retry must name what's missing.
async def test_a_dropped_side_is_named_in_the_retry() -> None:
    text = "a dragon vs a main battle tank"
    only_dragon = {"fighters": [{"raw": "a dragon", "entity": "dragon"}]}
    both = {
        "fighters": [
            {"raw": "a dragon", "entity": "dragon"},
            {"raw": "a main battle tank", "entity": "main battle tank"},
        ]
    }
    chat = CannedChat({text: [only_dragon, both]})
    result = await parse_matchup(text, chat=chat)
    assert result.status == "ok" and result.matchup is not None
    assert [f.entity for f in result.matchup.fighters] == ["dragon", "main battle tank"]
    feedback = chat.calls[1][3]["content"]
    assert "2 sides" in feedback and "a main battle tank" in feedback


# Number rule (PR #140 review): a model-written variant with a digit is dropped.
async def test_a_variant_with_a_digit_is_dropped_and_a_digit_free_one_kept() -> None:
    text = "a moose vs a polar bear"
    reply = {
        "fighters": [
            {"raw": "a moose", "entity": "moose", "variant": "weighs 4000 kg"},
            {"raw": "a polar bear", "entity": "polar bear", "variant": "adult male"},
        ]
    }
    result = await parse_matchup(text, chat=CannedChat({text: [reply]}))
    assert result.status == "ok" and result.matchup is not None
    moose, bear = result.matchup.fighters
    assert (moose.variant, bear.variant) == (None, "adult male")


# Number rule (PR #140 review): model notes with a digit are dropped; code notes stay.
async def test_model_assumptions_with_a_digit_are_dropped_but_code_notes_stay() -> None:
    text = "a million ants vs moose in the volcano"
    reply = {
        "fighters": [
            {"raw": "a million ants", "entity": "ant"},
            {"raw": "moose", "entity": "moose"},
        ],
        "terrain": "the volcano",
        "assumptions": ["Moose weighs 600 kg and runs 56 km/h", "Ants fight as one swarm."],
    }
    result = await parse_matchup(text, chat=CannedChat({text: [reply]}))
    assert result.status == "ok" and result.matchup is not None
    notes = " | ".join(result.matchup.assumptions)
    assert "600" not in notes and "km/h" not in notes
    assert "Ants fight as one swarm." in notes
    assert "Assumed 1 moose" in notes and "10,000" in notes and "volcano" in notes


# PR #140 review: two sides copied from the same words are rejected, then retried.
async def test_two_sides_with_the_same_raw_are_retried() -> None:
    text = "a goose vs a toaster"
    same = {
        "fighters": [
            {"raw": "a goose", "entity": "goose"},
            {"raw": "A  Goose", "entity": "goose"},
        ]
    }
    good = {
        "fighters": [
            {"raw": "a goose", "entity": "goose"},
            {"raw": "a toaster", "entity": "toaster"},
        ]
    }
    chat = CannedChat({text: [same, good]})
    result = await parse_matchup(text, chat=chat)
    assert result.status == "ok" and result.matchup is not None
    assert [f.entity for f in result.matchup.fighters] == ["goose", "toaster"]
    assert len(chat.calls) == 2 and "same raw" in chat.calls[1][3]["content"]


# A mirror match the user really typed keeps both identical sides, with no retry.
async def test_a_typed_mirror_match_is_not_rejected() -> None:
    text = "a wolf vs A  Wolf"
    reply = {
        "fighters": [
            {"raw": "a wolf", "entity": "wolf"},
            {"raw": "a wolf", "entity": "wolf"},
        ]
    }
    chat = CannedChat({text: [reply]})
    result = await parse_matchup(text, chat=chat)
    assert result.status == "ok" and result.matchup is not None
    assert [f.entity for f in result.matchup.fighters] == ["wolf", "wolf"]
    assert len(chat.calls) == 1


def test_the_prompt_says_variant_and_assumptions_have_no_numbers() -> None:
    prompt = " ".join(load_prompt().split())
    assert '"variant" and "assumptions" must contain no numbers' in prompt


def test_the_prompt_says_unusual_fighters_need_no_question() -> None:
    prompt = " ".join(load_prompt().split())
    assert "a dragon vs a main battle tank" in prompt and "a toaster vs a goose" in prompt
    assert "never leave a side out" in prompt
