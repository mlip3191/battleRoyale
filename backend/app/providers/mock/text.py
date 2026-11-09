"""Mock text providers: canned chat replies, default decisions, hash vectors, keyword reranking."""

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT
from app.providers.base import ChatMessage, DecisionAnswer, DecisionQuestion

# Canned replies live with the test fixtures (ARCHITECTURE §7), one JSON file per prompt name.
FIXTURE_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "providers"
MOCK_EMBEDDING_DIM = 64


# Stable short hash of any JSON-able input, so the same input always finds the same reply.
def input_hash(value: object) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# Load {"default": ..., "<input hash>": ...} for a prompt and pick the reply for this input.
def canned_reply(kind: str, prompt_name: str, value: object, fixture_dir: Path) -> Any:
    path = fixture_dir / kind / f"{prompt_name}.json"
    if not path.is_file():
        raise LookupError(f"No mock {kind} fixture for prompt '{prompt_name}' (expected {path}).")
    replies = json.loads(path.read_text(encoding="utf-8"))
    key = input_hash(value)
    if key in replies:
        return replies[key]
    if "default" in replies:
        return replies["default"]
    raise LookupError(f"Mock {kind} fixture '{prompt_name}' has no reply for input {key}.")


class MockChatLLM:
    """Replies from tests/fixtures/providers/chat/<prompt_name>.json."""

    def __init__(self, fixture_dir: Path = FIXTURE_DIR) -> None:
        self.fixture_dir = fixture_dir

    # JSON replies are stored as objects and returned as text, like a real model would.
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        prompt_name: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        reply = canned_reply("chat", prompt_name, messages, self.fixture_dir)
        return reply if isinstance(reply, str) else json.dumps(reply)


class MockStructuredLLM:
    """Picks each question's first option with equal odds, unless a fixture overrides it.

    Overrides live in tests/fixtures/providers/structured/<prompt_name>.json.
    """

    def __init__(self, fixture_dir: Path = FIXTURE_DIR) -> None:
        self.fixture_dir = fixture_dir

    # Fixture reply if there is one (copied so callers can't change it), else the default.
    async def decide(
        self,
        state: dict[str, str],
        questions: dict[str, DecisionQuestion],
        *,
        prompt_name: str,
    ) -> dict[str, DecisionAnswer]:
        if (self.fixture_dir / "structured" / f"{prompt_name}.json").is_file():
            value = {"state": state, "questions": questions}
            reply = canned_reply("structured", prompt_name, value, self.fixture_dir)
            return json.loads(json.dumps(reply))
        return {name: first_option(question) for name, question in questions.items()}


# The default mock answer: the first option, with every option equally likely.
def first_option(question: DecisionQuestion) -> DecisionAnswer:
    options = list(question["criteria"])
    share = 1 / len(options)
    return {
        "choice": options[0],
        "probabilities": {option: share for option in options},
        "confidence": share,
    }


class MockEmbedder:
    """Unit-length vectors derived from a hash of each text."""

    def __init__(self, dim: int = MOCK_EMBEDDING_DIM) -> None:
        self.dim = dim

    # Same text, same vector; different texts almost always differ.
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    # Stretch a SHA-256 stream into dim numbers in [-1, 1], then normalize.
    def _vector(self, text: str) -> list[float]:
        raw = b""
        counter = 0
        while len(raw) < self.dim:
            raw += hashlib.sha256(f"{counter}:{text}".encode()).digest()
            counter += 1
        values = [byte / 127.5 - 1.0 for byte in raw[: self.dim]]
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]


# Lowercase word set used for keyword overlap.
def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class MockReranker:
    """Scores each passage by the share of query words it contains."""

    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        query_words = _words(query)
        if not query_words:
            return [0.0 for _ in passages]
        return [len(query_words & _words(p)) / len(query_words) for p in passages]


class MockDocParser:
    """Returns text documents as-is and an empty string for anything else."""

    async def parse(self, data: bytes, mime: str) -> str:
        if mime.startswith("text/") or mime in ("application/json", "application/xml"):
            return data.decode("utf-8", errors="replace")
        return ""
