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


# A trailing place phrase on a side: "a horse in the water" -> "a horse".
_TERRAIN_TAIL = re.compile(r"\s+((?:in|on|at|inside|into)\s+.+)$", re.I)


# The parser's raw-phrase squash, imported so the copy cannot drift.
def _squash(text: str) -> str:
    from app.intake.parser import _squash as squash

    return squash(text)


# The user's matchup, unwrapped from the first data-block message (not a retry prompt).
def _user_matchup_text(messages: list[ChatMessage]) -> str | None:
    from app.intake.llm_io import INPUT_END, INPUT_START

    for message in messages:
        content = message.get("content") or ""
        if message.get("role") != "user" or INPUT_START not in content:
            continue
        inner = content.split(INPUT_START, 1)[1]
        if INPUT_END in inner:
            inner = inner.split(INPUT_END, 1)[0]
        return inner.strip()
    return None


# True when the canned reply's raw phrases all appear in the user's text (two sides).
def _fixture_fits_text(reply: Any, text: str) -> bool:
    data = _squash(text)
    if isinstance(reply, str):
        try:
            reply = json.loads(reply)
        except json.JSONDecodeError:
            return False
    if not isinstance(reply, dict):
        return False
    fighters = reply.get("fighters") or []
    if len(fighters) != 2:
        return False
    return all(
        isinstance(fighter, dict) and fighter.get("raw") and _squash(str(fighter["raw"])) in data
        for fighter in fighters
    )


# True when a phrase names a known battlefield (forest, water, and so on).
# Plural place words ("woods", "mountains") are singularised the same way as the parser.
def _has_known_terrain(phrase: str) -> bool:
    from app.intake.rules import TERRAIN_WORDS, singular_word

    words = " ".join(singular_word(w) for w in re.findall(r"[a-z]+", phrase.lower()))
    return any(re.search(rf"\b{re.escape(name)}\b", words) for name in TERRAIN_WORDS)


# Drop a trailing "in the water" / "in a forest" so the entity is just the fighter.
def _strip_terrain_tail(side: str) -> str:
    side = side.strip()
    match = _TERRAIN_TAIL.search(side)
    if match is None or not _has_known_terrain(match.group(1)):
        return side
    return side[: match.start()].strip() or side


# The battlefield words in a trailing "in the ..." phrase only, so a terrain word
# inside a fighter's name ("sea turtle", "field mouse") is not the battlefield.
def _terrain_phrase(text: str) -> str | None:
    from app.intake.parser import typed_sides
    from app.intake.rules import TERRAIN_WORDS, singular_word

    for side in typed_sides(text):
        match = _TERRAIN_TAIL.search(side)
        if match is None or not _has_known_terrain(match.group(1)):
            continue
        words = " ".join(singular_word(w) for w in re.findall(r"[a-z]+", match.group(1).lower()))
        for name in sorted(TERRAIN_WORDS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(name)}\b", words):
                return name
    return None


# A ParsedMatchup-shaped reply from an "X vs Y" request, for mock mode (#142 item 5).
# Code in the parser still decides counts, names, size references, and terrain.
def echo_intake_reply(text: str) -> dict[str, Any] | None:
    from app.intake.parser import typed_sides

    sides = [part.strip() for part in typed_sides(text) if part.strip()]
    if len(sides) != 2:
        return None
    fighters: list[dict[str, Any]] = []
    for side in sides:
        raw = _strip_terrain_tail(side)
        if _squash(raw) not in _squash(text):
            raw = side.strip()
        fighters.append(
            {
                "raw": raw,
                "entity": raw,
                "count": None,
                "variant": None,
                "size_reference": None,
            }
        )
    return {
        "fighters": fighters,
        "terrain": _terrain_phrase(text),
        "needs_clarification": None,
        "assumptions": [],
    }


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
        # #142 item 5: the intake_parse default is the grizzly-vs-wolves reply, which the
        # parser rejects for any other input. Echo the user's two sides instead, so the
        # front end can demo any matchup offline.
        if prompt_name == "intake_parse":
            text = _user_matchup_text(messages)
            if text and not _fixture_fits_text(reply, text):
                echoed = echo_intake_reply(text)
                if echoed is not None:
                    return json.dumps(echoed)
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
    if not options:
        raise ValueError("Decision question has no options in its criteria.")
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
