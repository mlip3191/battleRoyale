"""get_provider(name): the mock in mock mode, the live adapter in live mode (ARCHITECTURE §7)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, overload

from pydantic import SecretStr

from app.config import Settings, get_settings
from app.providers import mock
from app.providers.base import (
    TTS,
    ChatLLM,
    DocParser,
    Embedder,
    ImageGen,
    MusicGen,
    ProviderName,
    Reranker,
    StructuredLLM,
)

# Each provider's settings prefix (CHAT_LLM_URL, CHAT_LLM_MODEL, CHAT_LLM_API_KEY, ...).
SETTINGS_PREFIX: dict[ProviderName, str] = {
    "chat": "chat_llm",
    "structured": "structured_llm",
    "embedder": "embeddings",
    "reranker": "rerank",
    "doc_parser": "doc_parse",
    "image": "image",
    "tts": "tts",
    "music": "music",
}

MOCKS: dict[ProviderName, Callable[[], object]] = {
    "chat": mock.MockChatLLM,
    "structured": mock.MockStructuredLLM,
    "embedder": mock.MockEmbedder,
    "reranker": mock.MockReranker,
    "doc_parser": mock.MockDocParser,
    "image": mock.MockImageGen,
    "tts": mock.MockTTS,
    "music": mock.MockMusicGen,
}


class ProviderConfigError(RuntimeError):
    """Live mode is missing a setting; the message names the variable, never a value."""


@dataclass(frozen=True)
class ServiceConfig:
    """What a live adapter needs; repr hides the URL (it holds the host) and the key."""

    base_url: str = field(repr=False)
    model: str
    api_key: SecretStr = field(repr=False)


# Live adapters by provider name; each is added by the task that builds it.
def _live_factories() -> dict[ProviderName, Callable[[ServiceConfig, Settings], object]]:
    from app.providers.live.chat import LiveChatLLM
    from app.providers.live.doc_parser import LiveDocParser
    from app.providers.live.embedder import LiveEmbedder
    from app.providers.live.rerank import LiveReranker
    from app.providers.live.structured import LiveStructuredLLM

    return {
        "chat": LiveChatLLM,
        "structured": LiveStructuredLLM,
        "embedder": LiveEmbedder,
        "reranker": LiveReranker,
        "doc_parser": LiveDocParser,
    }


# Gather a service's URL, model, and key, failing fast on anything missing.
def service_config(name: ProviderName, settings: Settings) -> ServiceConfig:
    prefix = SETTINGS_PREFIX[name]
    url = str(getattr(settings, f"{prefix}_url", "") or "").strip().rstrip("/")
    model = str(getattr(settings, f"{prefix}_model", "") or "").strip()
    own_key: SecretStr | None = getattr(settings, f"{prefix}_api_key", None)
    key = own_key if own_key and own_key.get_secret_value() else settings.course_api_key
    missing = []
    if not url or "replace-me" in url:
        missing.append(f"{prefix.upper()}_URL")
    if hasattr(settings, f"{prefix}_model") and (not model or model == "replace-me"):
        missing.append(f"{prefix.upper()}_MODEL")
    if not key.get_secret_value() or key.get_secret_value() == "replace-me":
        missing.append("COURSE_API_KEY")
    if missing:
        raise ProviderConfigError(
            f"Live '{name}' provider needs these .env settings: {', '.join(missing)}. "
            "Check them with npm run env:check."
        )
    return ServiceConfig(base_url=url, model=model, api_key=key)


@overload
def get_provider(name: Literal["chat"], settings: Settings | None = None) -> ChatLLM: ...
@overload
def get_provider(
    name: Literal["structured"], settings: Settings | None = None
) -> StructuredLLM: ...
@overload
def get_provider(name: Literal["embedder"], settings: Settings | None = None) -> Embedder: ...
@overload
def get_provider(name: Literal["reranker"], settings: Settings | None = None) -> Reranker: ...
@overload
def get_provider(name: Literal["doc_parser"], settings: Settings | None = None) -> DocParser: ...
@overload
def get_provider(name: Literal["image"], settings: Settings | None = None) -> ImageGen: ...
@overload
def get_provider(name: Literal["tts"], settings: Settings | None = None) -> TTS: ...
@overload
def get_provider(name: Literal["music"], settings: Settings | None = None) -> MusicGen: ...


# Return the provider for name, honoring PROVIDER_MODE.
def get_provider(name: ProviderName, settings: Settings | None = None) -> object:
    settings = settings or get_settings()
    if name not in MOCKS:
        raise ValueError(f"Unknown provider '{name}'. Known: {', '.join(MOCKS)}.")
    if settings.provider_mode == "mock":
        return MOCKS[name]()
    factory = _live_factories().get(name)
    if factory is None:
        raise ProviderConfigError(
            f"No live '{name}' adapter yet; use PROVIDER_MODE=mock until its task builds one."
        )
    return factory(service_config(name, settings), settings)


# The chat model for intake: the same provider, with intake's shorter timeout and fewer retries.
def get_intake_chat(settings: Settings | None = None) -> ChatLLM:
    settings = settings or get_settings()
    if settings.provider_mode == "mock":
        return mock.MockChatLLM()
    from app.providers.live.chat import LiveChatLLM

    return LiveChatLLM(
        service_config("chat", settings),
        settings,
        timeout_s=settings.intake_timeout_s,
        retries=settings.intake_retries,
    )
