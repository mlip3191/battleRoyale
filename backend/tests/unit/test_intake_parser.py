"""parse_matchup on mocks: the 25+ intake cases, code overriding the model, and the retry (A02)."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from app.config import REPO_ROOT
from app.intake.parser import (
    INPUT_END,
    INPUT_START,
    PROMPT_NAME,
    IntakeUnavailable,
    has_number,
    load_prompt,
    parse_matchup,
    typed_sides,
)
from app.intake.schema import ParsedMatchup
from app.models.matchup import IntakeResult
from app.models.terrain import Terrain
from app.providers.base import ChatMessage
from app.providers.live.http import ProviderError
from app.providers.mock.text import MockChatLLM
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


# Issue #142 item 4: an outage raises its own error instead of blaming the user's wording.
async def test_endpoint_down_retries_once_then_raises_intake_unavailable() -> None:
    chat = FailingChat()
    with pytest.raises(IntakeUnavailable):
        await parse_matchup("a lion vs a tiger", chat=chat)
    assert chat.calls == 2


@pytest.mark.parametrize(
    "error", [ProviderError("HTTP 503"), httpx.ConnectError("refused"), TimeoutError()]
)
async def test_every_kind_of_outage_raises_intake_unavailable(error: Exception) -> None:
    class DownChat:
        async def complete(self, messages: list[ChatMessage], **_: Any) -> str:
            raise error

    with pytest.raises(IntakeUnavailable):
        await parse_matchup("a lion vs a tiger", chat=DownChat())


# An empty `{}` reply plus a failed call is an outage, not the user's wording (live runs saw both).
@pytest.mark.parametrize("fail_first", [True, False])
async def test_empty_reply_and_one_outage_raises_intake_unavailable(fail_first: bool) -> None:
    class FlakyChat:
        calls = 0

        async def complete(self, messages: list[ChatMessage], **_: Any) -> str:
            self.calls += 1
            if (self.calls == 1) == fail_first:
                raise TimeoutError()
            return "{}"

    chat = FlakyChat()
    with pytest.raises(IntakeUnavailable):
        await parse_matchup("a lion vs a tiger", chat=chat)
    assert chat.calls == 2


# Two `{}` replies mean the model answered but unusably: ask the user to rephrase.
async def test_two_empty_replies_ask_to_rephrase() -> None:
    text = "a lion vs a tiger"
    chat = CannedChat({text: ["{}", "{}"]})
    result = await parse_matchup(text, chat=chat)
    assert result.status == "clarify" and "another way" in (result.question or "")
    assert len(chat.calls) == 2


# A `{}` first reply is retried, and a good second reply is used.
async def test_empty_reply_then_valid_reply_is_ok() -> None:
    text = "a lion vs a tiger"
    good = {
        "fighters": [{"raw": "a lion", "entity": "lion"}, {"raw": "a tiger", "entity": "tiger"}]
    }
    chat = CannedChat({text: ["{}", good]})
    result = await parse_matchup(text, chat=chat)
    assert result.status == "ok" and result.matchup is not None
    assert [f.entity for f in result.matchup.fighters] == ["lion", "tiger"]
    assert "fighters" in chat.calls[1][3]["content"]  # the retry names the missing field


# One-sided input: before the schema fix, `{}` passed as an empty matchup; now it is retried.
async def test_empty_reply_then_valid_one_sided_reply_is_used() -> None:
    text = "bear"
    good = {
        "fighters": [{"raw": "bear", "entity": "bear"}],
        "needs_clarification": {
            "question": "Which bear are we talking about?",
            "options": ["grizzly bear", "polar bear", "black bear"],
        },
    }
    chat = CannedChat({text: ["{}", good]})
    result = await parse_matchup(text, chat=chat)
    assert len(chat.calls) == 2  # the `{}` triggered a retry
    assert "fighters" in chat.calls[1][3]["content"]
    assert result.status == "clarify" and result.question == "Which bear are we talking about?"
    assert result.options == ["grizzly bear", "polar bear", "black bear"]


# The schema sent to the model must require `fighters`, so structured output can't return `{}`.
def test_parsed_matchup_schema_requires_fighters() -> None:
    assert "fighters" in ParsedMatchup.model_json_schema().get("required", [])


# Issue #142 item 6: a missing mock fixture is a developer error and must fail loudly.
async def test_a_missing_mock_fixture_raises_instead_of_asking_to_rephrase(
    tmp_path: Path,
) -> None:
    with pytest.raises(LookupError, match="No mock chat fixture"):
        await parse_matchup("a lion vs a tiger", chat=MockChatLLM(fixture_dir=tmp_path))


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


# Issue #142 item 5: any "X vs Y" input parses in mock mode, not just the canned default.
@pytest.mark.parametrize(
    ("text", "entities", "counts", "terrain"),
    [
        ("a horse vs a gorilla", ["horse", "gorilla"], [1, 1], Terrain.ARENA),
        ("50 ducks vs a honey badger", ["duck", "honey badger"], [50, 1], Terrain.ARENA),
        (
            "an african elephant vs 12 gray wolves",
            ["african elephant", "gray wolf"],
            [1, 12],
            Terrain.ARENA,
        ),
        (
            "a honey badger vs a saltwater crocodile",
            ["honey badger", "saltwater crocodile"],
            [1, 1],
            Terrain.ARENA,
        ),
        (
            "a saltwater crocodile vs a horse in the water",
            ["saltwater crocodile", "horse"],
            [1, 1],
            Terrain.WATER,
        ),
        ("two tigers vs a lion in a forest", ["tiger", "lion"], [2, 1], Terrain.FOREST),
        ("a toaster VS. a goose", ["toaster", "goose"], [1, 1], Terrain.ARENA),
        ("a horse versus a gorilla", ["horse", "gorilla"], [1, 1], Terrain.ARENA),
        (
            "100 duck-sized horses vs 1 horse-sized duck",
            ["horse", "duck"],
            [100, 1],
            Terrain.ARENA,
        ),
        # Plural place words singularise to a known battlefield ("woods" -> forest).
        ("two tigers vs a lion in the woods", ["tiger", "lion"], [2, 1], Terrain.FOREST),
        # A terrain word inside a fighter's name is not the battlefield.
        ("a sea turtle vs a goose", ["sea turtle", "goose"], [1, 1], Terrain.ARENA),
        ("a field mouse vs a house cat", ["field mouse", "house cat"], [1, 1], Terrain.ARENA),
        ("a snow leopard vs a polar bear", ["snow leopard", "polar bear"], [1, 1], Terrain.ARENA),
    ],
)
async def test_the_mock_provider_echoes_any_vs_matchup(
    text: str, entities: list[str], counts: list[int], terrain: Terrain
) -> None:
    result = await parse_matchup(text, chat=MockChatLLM())
    assert result.status == "ok" and result.matchup is not None
    left, right = result.matchup.fighters
    assert [left.entity, right.entity] == entities
    assert [left.count, right.count] == counts
    assert result.matchup.terrain == terrain


# Size adjectives stay on the echoed raw phrases so the parser can still read them.
async def test_the_mock_provider_keeps_size_references_on_echoed_matchups() -> None:
    result = await parse_matchup("100 duck-sized horses vs 1 horse-sized duck", chat=MockChatLLM())
    assert result.status == "ok" and result.matchup is not None
    left, right = result.matchup.fighters
    assert (left.size_reference, right.size_reference) == ("duck", "horse")


# One side, or no "vs", still asks the user to rephrase (the mock has nothing to echo).
async def test_the_mock_provider_still_asks_to_rephrase_a_single_side() -> None:
    result = await parse_matchup("just a grizzly bear", chat=MockChatLLM())
    assert result.status == "clarify"


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


# Issue #142 item 7: spelled-out numbers are dropped too, as whole words only.
async def test_spelled_out_numbers_are_dropped_from_variant_and_assumptions() -> None:
    text = "a moose vs a polar bear"
    reply = {
        "fighters": [
            {"raw": "a moose", "entity": "moose", "variant": "weighs four thousand kilos"},
            {"raw": "a polar bear", "entity": "polar bear", "variant": "often-fed adult"},
        ],
        "assumptions": [
            "The moose weighs four thousand kilos.",
            "Hundreds of kilos of muscle.",
            "Someone often sees the bear's weight as its edge.",
        ],
    }
    result = await parse_matchup(text, chat=CannedChat({text: [reply]}))
    assert result.status == "ok" and result.matchup is not None
    moose, bear = result.matchup.fighters
    assert (moose.variant, bear.variant) == (None, "often-fed adult")
    notes = " | ".join(result.matchup.assumptions).lower()
    assert "thousand" not in notes and "hundreds" not in notes
    assert "someone often sees the bear's weight as its edge." in notes


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("weighs four thousand kilos", True),
        ("twenty-five km per hour", True),
        ("a dozen tusks", True),
        ("weighs 4000 kg", True),
        ("Ants fight as one swarm.", False),  # "one" is left out: too common in prose
        ("an adult male in his prime", False),
        ("often seen alone; someone's weight", False),  # whole words only
        ("no armor, none at all", False),
    ],
)
def test_has_number_matches_whole_number_words(text: str, expected: bool) -> None:
    assert has_number(text) is expected


def test_the_prompt_says_variant_and_assumptions_have_no_numbers() -> None:
    prompt = " ".join(load_prompt().split())
    assert '"variant" and "assumptions" must contain no numbers' in prompt


def test_the_prompt_says_unusual_fighters_need_no_question() -> None:
    prompt = " ".join(load_prompt().split())
    assert "a dragon vs a main battle tank" in prompt and "a toaster vs a goose" in prompt
    assert "never leave a side out" in prompt
