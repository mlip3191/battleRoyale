"""One interface per course service (ARCHITECTURE §7); mocks and live adapters both satisfy them."""

from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

# Names accepted by registry.get_provider, one per interface below.
ProviderName = Literal[
    "chat", "structured", "embedder", "reranker", "doc_parser", "image", "tts", "music"
]


class ChatMessage(TypedDict):
    """One chat turn in the OpenAI-style messages list."""

    role: Literal["system", "user", "assistant"]
    content: str


@runtime_checkable
class ChatLLM(Protocol):
    """Chat / classification LLM (course port 9001)."""

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        prompt_name: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Return the assistant's reply text; with json_schema, the reply is JSON matching it.

        prompt_name is the file in backend/prompts/ that built the messages; mocks key on it.
        """
        ...


class DecisionQuestion(TypedDict):
    """A named "pick one of these options" question for Structured Decisions."""

    type: Literal["choice"]
    instructions: str
    criteria: dict[str, str]
    """Option id -> what that option means."""


class DecisionAnswer(TypedDict):
    """The model's pick for one question, with a probability for every option."""

    choice: str
    probabilities: dict[str, float]
    confidence: float


@runtime_checkable
class StructuredLLM(Protocol):
    """Structured Decisions (course port 9010): answers choice questions, never extracts (D-41)."""

    async def decide(
        self,
        state: dict[str, str],
        questions: dict[str, DecisionQuestion],
        *,
        prompt_name: str,
    ) -> dict[str, DecisionAnswer]:
        """Answer every question about state; the reply has one answer per question name.

        prompt_name names the decision (sent as its title); mocks key on it.
        """
        ...


@runtime_checkable
class Embedder(Protocol):
    """Text embeddings (course port 9002)."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per text, all the same length."""
        ...


@runtime_checkable
class Reranker(Protocol):
    """Reranker: scores how well each passage answers the query."""

    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        """Return one relevance score per passage, in the passages' order (higher is better)."""
        ...


@runtime_checkable
class DocParser(Protocol):
    """Document parsing / OCR (course port 9005)."""

    async def parse(self, data: bytes, mime: str) -> str:
        """Return the document's plain text."""
        ...


@runtime_checkable
class ImageGen(Protocol):
    """Image generation and editing (course port 9006)."""

    async def generate(self, prompt: str) -> bytes:
        """Return PNG bytes for prompt."""
        ...

    async def edit(self, image: bytes, prompt: str) -> bytes:
        """Return PNG bytes of image changed as prompt describes."""
        ...


@runtime_checkable
class TTS(Protocol):
    """Text-to-speech (course port 9008)."""

    async def speak(self, text: str, voice_id: str) -> bytes:
        """Return audio bytes (WAV or MP3) of text read in voice_id."""
        ...


@runtime_checkable
class MusicGen(Protocol):
    """Music generation (course port 9007)."""

    async def compose(self, prompt: str, seconds: float) -> bytes:
        """Return audio bytes of a track about seconds long."""
        ...
