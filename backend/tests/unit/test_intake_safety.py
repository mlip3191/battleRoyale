"""Safety inside parse_matchup (A04 part 1; #142 items 1 and 2): order, concurrency, outages,
real people as raw or entity, and the "a wolf" -> "godzilla" probe. Prompt injection lives in
tests/golden/test_safety_injections.py."""

import asyncio
import json
from typing import Any

import pytest

from app.intake.llm_io import INPUT_END, INPUT_START, as_data
from app.intake.parser import PROMPT_NAME as PARSE_PROMPT
from app.intake.parser import IntakeUnavailable, parse_matchup
from app.models.matchup import IntakeResult
from app.providers.base import ChatMessage
from app.providers.live.http import ProviderError
from app.safety.classify import PROMPT_NAME as SAFETY_PROMPT

# What the classifier stand-in blocks: fighter words -> reason. It ignores instructions.
BLOCKED_WORDS = {
    "napoleon": "real_person",
    "godzilla": "copyrighted_character",
    "zeus": "deity",
    "the moon": "out_of_scope",
}


# The user's text, unwrapped from the data markers.
def user_text(messages: list[ChatMessage]) -> str:
    content = messages[1]["content"]
    return content.removeprefix(f"{INPUT_START}\n").removesuffix(f"\n{INPUT_END}")


# A two-sided parse reply: each side is (raw, entity) or (raw, entity, variant).
def reply(*sides: tuple[str, ...], **extra: Any) -> dict[str, Any]:
    fighters = [
        {"raw": s[0], "entity": s[1], "variant": s[2] if len(s) > 2 else None} for s in sides
    ]
    return {"fighters": fighters, **extra}


class FakeModel:
    """Stand-in chat model for both prompts, keyed by the user's text, counting every call.

    Parse replies come from `parses` (text -> reply). The classifier blocks a text that names a
    word in BLOCKED_WORDS, whatever else the text says; `verdicts` can override it per text.
    """

    def __init__(
        self,
        parses: dict[str, dict[str, Any]] | None = None,
        verdicts: dict[str, str] | None = None,
    ) -> None:
        # Keyed as the model sees the text: marker-like "<<<" already broken up.
        self.parses = {as_data(text): parsed for text, parsed in (parses or {}).items()}
        self.verdicts = verdicts or {}
        self.calls: dict[str, list[str]] = {PARSE_PROMPT: [], SAFETY_PROMPT: []}

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        prompt_name: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        assert json_schema is not None
        text = user_text(messages)
        self.calls[prompt_name].append(text)
        if prompt_name == SAFETY_PROMPT:
            return json.dumps({"verdict": self.verdict(text)})
        return json.dumps(self.parses[text])

    # The label for a text: an override, else the first blocked word in it, else allowed.
    def verdict(self, text: str) -> str:
        if text in self.verdicts:
            return self.verdicts[text]
        hits = [reason for word, reason in BLOCKED_WORDS.items() if word in text.lower()]
        return hits[0] if hits else "allowed"


class DownChat:
    """Stand-in chat model whose endpoint is down."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages: list[ChatMessage], **_: Any) -> str:
        self.calls += 1
        raise ProviderError("chat endpoint unavailable")


# Parse with one FakeModel answering both prompts (as in production, one chat provider).
async def run(text: str, model: FakeModel) -> IntakeResult:
    return await parse_matchup(text, chat=model, safety_chat=model)


# --- Order: code rules first ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("a toddler vs a goose", "minor"),
        ("the French vs the Germans", "hate"),
        ("my brother vs a goose", "real_person"),
        ("a 6-year-old vs a goose", "minor"),
    ],
)
async def test_code_rules_block_before_any_model_call(text: str, reason: str) -> None:
    parse, safety = DownChat(), DownChat()  # any call would raise
    result = await parse_matchup(text, chat=parse, safety_chat=safety)
    assert result.status == "blocked" and result.blocked_reason == reason
    assert result.message and result.matchup is None
    assert (parse.calls, safety.calls) == (0, 0)


# --- Real people, as raw or as entity (#142 items 1 and 2) ----------------------------------


async def test_a_real_person_in_the_users_words_is_refused() -> None:
    text = "Napoleon vs a grizzly bear"
    model = FakeModel({text: reply(("Napoleon", "napoleon"), ("a grizzly bear", "grizzly bear"))})
    result = await run(text, model)
    assert (result.status, result.blocked_reason) == ("blocked", "real_person")
    assert model.calls[SAFETY_PROMPT][0] == text


async def test_a_real_person_only_in_the_models_entity_is_refused() -> None:
    text = "the short emperor vs a grizzly bear"
    model = FakeModel(
        {
            text: reply(
                ("the short emperor", "napoleon bonaparte"), ("a grizzly bear", "grizzly bear")
            )
        }
    )
    result = await run(text, model)
    assert (result.status, result.blocked_reason) == ("blocked", "real_person")
    # The first call saw only the user's words; the second checked the model's reading.
    assert model.calls[SAFETY_PROMPT] == [text, "napoleon bonaparte vs grizzly bear"]


async def test_the_wolf_to_godzilla_probe_is_refused() -> None:
    text = "a wolf vs a grizzly bear"
    model = FakeModel({text: reply(("a wolf", "godzilla"), ("a grizzly bear", "grizzly bear"))})
    result = await run(text, model)
    assert (result.status, result.blocked_reason) == ("blocked", "copyrighted_character")


async def test_a_model_entity_hit_by_code_rules_is_refused() -> None:
    text = "a little one vs a goose"
    model = FakeModel({text: reply(("a little one", "toddler"), ("a goose", "goose"))})
    result = await run(text, model)
    assert (result.status, result.blocked_reason) == ("blocked", "minor")


async def test_a_real_person_asked_about_in_a_clarify_is_still_refused() -> None:
    text = "Napoleon"
    parsed = {
        "fighters": [{"raw": "Napoleon", "entity": "napoleon"}],
        "needs_clarification": {"question": "Who should he fight?", "options": ["a bear", "a cat"]},
    }
    result = await run(text, FakeModel({text: parsed}))
    assert (result.status, result.blocked_reason) == ("blocked", "real_person")


async def test_plain_words_need_no_second_classifier_call() -> None:
    text = "a grizzly bear vs 6 gray wolves"
    model = FakeModel(
        {
            text: reply(
                ("a grizzly bear", "grizzly bear", "adult male"), ("6 gray wolves", "gray wolf")
            )
        }
    )
    result = await run(text, model)
    assert result.status == "ok"
    assert model.calls[SAFETY_PROMPT] == [text]  # nothing new to check


async def test_animals_and_archetypes_pass_the_whole_gate() -> None:
    text = "a baby elephant vs a Roman legionary"
    model = FakeModel(
        {
            text: reply(
                ("a baby elephant", "elephant", "baby"), ("a Roman legionary", "Roman legionary")
            )
        }
    )
    result = await run(text, model)
    assert result.status == "ok" and result.matchup is not None
    assert [f.variant for f in result.matchup.fighters] == ["baby", None]


# --- Concurrency ----------------------------------------------------------------------------


async def test_the_classifier_runs_while_the_parse_call_is_waiting() -> None:
    text = "a wolf vs a bear"
    classified = asyncio.Event()

    class TogetherModel(FakeModel):
        async def complete(self, messages: list[ChatMessage], **kwargs: Any) -> str:
            if kwargs["prompt_name"] == SAFETY_PROMPT:
                classified.set()
            else:  # the parse call only finishes once the classifier has been called
                await asyncio.wait_for(classified.wait(), timeout=2)
            return await super().complete(messages, **kwargs)

    model = TogetherModel({text: reply(("a wolf", "wolf"), ("a bear", "bear"))})
    assert (await run(text, model)).status == "ok"


async def test_a_classifier_block_does_not_wait_for_the_parse_call() -> None:
    text = "Napoleon vs a bear"
    cancelled = asyncio.Event()

    class SlowParse(FakeModel):
        async def complete(self, messages: list[ChatMessage], **kwargs: Any) -> str:
            if kwargs["prompt_name"] == PARSE_PROMPT:
                try:
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    cancelled.set()
                    raise
            return await super().complete(messages, **kwargs)

    result = await asyncio.wait_for(run(text, SlowParse()), timeout=2)
    assert result.blocked_reason == "real_person" and cancelled.is_set()


# --- Fail closed ----------------------------------------------------------------------------


async def test_a_classifier_outage_raises_intake_unavailable_even_if_parsing_worked() -> None:
    text = "a wolf vs a bear"
    parse = FakeModel({text: reply(("a wolf", "wolf"), ("a bear", "bear"))})
    with pytest.raises(IntakeUnavailable):
        await parse_matchup(text, chat=parse, safety_chat=DownChat())


async def test_an_outage_on_the_second_check_raises_intake_unavailable() -> None:
    text = "a wolf vs a bear"

    class SecondCallDown(FakeModel):
        async def complete(self, messages: list[ChatMessage], **kwargs: Any) -> str:
            if kwargs["prompt_name"] == SAFETY_PROMPT and self.calls[SAFETY_PROMPT]:
                raise ProviderError("HTTP 503")
            return await super().complete(messages, **kwargs)

    model = SecondCallDown({text: reply(("a wolf", "godzilla"), ("a bear", "bear"))})
    with pytest.raises(IntakeUnavailable):
        await run(text, model)


async def test_an_unusable_classifier_reply_raises_intake_unavailable() -> None:
    text = "a wolf vs a bear"
    model = FakeModel({text: reply(("a wolf", "wolf"), ("a bear", "bear"))}, {text: "maybe"})
    with pytest.raises(IntakeUnavailable):
        await run(text, model)


async def test_the_mock_provider_allows_by_default_in_mock_mode() -> None:
    result = await parse_matchup("a grizzly bear vs 6 gray wolves in a forest")
    assert result.status == "ok"


# Prompt injection (same result as the clean version) moved to the injection cases in
# tests/fixtures/safety_cases.yaml, run by tests/golden/test_safety_injections.py.
