"""Safety layer 2: the chat model sorts a request into "allowed" or a contract block reason.

The model only picks a label from a fixed list; it never writes the message (code does) and
never sets a number. If no usable label comes back, safety fails closed: SafetyUnavailable.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from app.intake.llm_io import CALL_ERRORS, data_block
from app.providers.base import ChatLLM, ChatMessage
from app.safety.verdict import ALLOWED, SafetyVerdict, blocked

PROMPT_NAME = "safety_classify"
PROMPT_PATH = Path(__file__).parents[2] / "prompts" / f"{PROMPT_NAME}.md"
ATTEMPTS = 2


class SafetyUnavailable(RuntimeError):
    """The classifier gave no usable answer (outage or unusable replies), so nothing may pass."""


class ClassifierReply(BaseModel):
    """The classifier's whole reply: one label."""

    model_config = ConfigDict(extra="ignore", use_attribute_docstrings=True)

    verdict: Literal[
        "allowed",
        "real_person",
        "minor",
        "sexual",
        "hate",
        "self_harm",
        "copyrighted_character",
        "deity",
        "weapon",
        "out_of_scope",
        "nonsense",
        "other",
    ]
    """"allowed", or why the request is blocked (the IntakeResult.blocked_reason list)."""


# The prompt template, read fresh so edits apply without a restart.
def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


# System prompt plus the text wrapped as data; the text appears nowhere else.
def build_messages(text: str) -> list[ChatMessage]:
    return [
        {"role": "system", "content": load_prompt()},
        {"role": "user", "content": data_block(text)},
    ]


# Reply text -> a label, or None when the reply is unusable.
def read_reply(reply: str) -> ClassifierReply | None:
    text = reply.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        return ClassifierReply.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError):
        return None


# Ask the classifier about text; tries twice, then fails closed with SafetyUnavailable.
async def classify_text(text: str, *, chat: ChatLLM) -> SafetyVerdict:
    messages = build_messages(text)
    schema = ClassifierReply.model_json_schema()
    problem: Exception | None = None
    for _ in range(ATTEMPTS):
        try:
            reply = await chat.complete(messages, prompt_name=PROMPT_NAME, json_schema=schema)
        except CALL_ERRORS as error:
            problem = error
            continue
        parsed = read_reply(reply)
        if parsed is not None:
            if parsed.verdict == "allowed":
                return ALLOWED
            return blocked(parsed.verdict, "classifier")
    raise SafetyUnavailable("The safety classifier gave no usable answer.") from problem
