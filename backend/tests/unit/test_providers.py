"""Mocks satisfy their interfaces offline, the registry picks mock or live, live chat is safe."""

import json
import logging
import wave
from io import BytesIO
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.providers import base, health
from app.providers.live.chat import LiveChatLLM
from app.providers.live.http import ProviderError
from app.providers.live.structured import LiveStructuredLLM
from app.providers.mock.text import MockChatLLM, MockStructuredLLM, input_hash
from app.providers.registry import (
    MOCKS,
    ProviderConfigError,
    ServiceConfig,
    get_intake_chat,
    get_provider,
    service_config,
)
from tests.conftest import mock_settings

DECOY_HOST = "decoy-host.invalid"
DECOY_KEY = "decoy-key-0000"
INTERFACES = {
    "chat": base.ChatLLM,
    "structured": base.StructuredLLM,
    "embedder": base.Embedder,
    "reranker": base.Reranker,
    "doc_parser": base.DocParser,
    "image": base.ImageGen,
    "tts": base.TTS,
    "music": base.MusicGen,
}
CHALLENGER: dict[str, base.DecisionQuestion] = {
    "challenger": {
        "type": "choice",
        "instructions": "Which opponent gives the closest fight?",
        "criteria": {"house_cat": "a house cat", "duck": "a duck"},
    }
}


# Live-mode settings pointing at a decoy host, never the real .env.
def live_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "provider_mode": "live",
        "course_api_key": DECOY_KEY,
        "chat_llm_url": f"http://{DECOY_HOST}:9001",
        "chat_llm_model": "decoy/chat-model",
        "structured_llm_url": f"http://{DECOY_HOST}:9010",
        "structured_llm_model": "decoy/decision-model",
    }
    return Settings(_env_file=None, **(values | overrides))


def test_there_is_a_mock_for_every_interface_and_it_satisfies_it() -> None:
    assert set(MOCKS) == set(INTERFACES) and len(INTERFACES) == 8
    for name, interface in INTERFACES.items():
        assert isinstance(get_provider(name), interface), name  # type: ignore[call-overload]


async def test_mocks_return_the_right_types_and_are_deterministic() -> None:
    messages: list[base.ChatMessage] = [{"role": "user", "content": "Toaster vs wolf"}]
    chat = get_provider("chat")
    reply = await chat.complete(messages, prompt_name="example")
    assert reply == await chat.complete(messages, prompt_name="example")
    assert isinstance(reply, str) and reply

    picked = await get_provider("structured").decide(
        {"winner": "gray wolf"}, CHALLENGER, prompt_name="no-fixture"
    )
    assert picked == {
        "challenger": {
            "choice": "house_cat",
            "probabilities": {"house_cat": 0.5, "duck": 0.5},
            "confidence": 0.5,
        }
    }
    fixture = await get_provider("structured").decide({}, CHALLENGER, prompt_name="example")
    assert fixture["challenger"]["choice"] == "grizzly_bear"
    empty: dict[str, base.DecisionQuestion] = {
        "q": {"type": "choice", "instructions": "Pick one.", "criteria": {}}
    }
    with pytest.raises(ValueError, match="no options"):
        await get_provider("structured").decide({}, empty, prompt_name="no-fixture")

    vectors = await get_provider("embedder").embed(["wolf", "wolf", "toaster"])
    assert vectors[0] == vectors[1] != vectors[2]
    assert len({len(v) for v in vectors}) == 1
    assert abs(sum(x * x for x in vectors[0]) - 1.0) < 1e-9

    scores = await get_provider("reranker").rerank("gray wolf bite", ["a gray wolf", "a toaster"])
    assert scores[0] > scores[1]

    assert await get_provider("doc_parser").parse(b"hello", "text/plain") == "hello"
    assert await get_provider("doc_parser").parse(b"\x00", "application/pdf") == ""


async def test_mock_media_is_a_valid_png_and_wavs_of_the_right_length() -> None:
    image = get_provider("image")
    png = await image.generate("a gray wolf")
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert png == await image.generate("a gray wolf")
    assert png != await image.generate("a toaster")
    assert (await image.edit(png, "add a hat")).startswith(b"\x89PNG")

    for audio, seconds in (
        (await get_provider("tts").speak("Let's get ready!", "stock"), 1.0),
        (await get_provider("music").compose("drum roll", 3), 3.0),
    ):
        with wave.open(BytesIO(audio)) as wav:
            assert wav.getnframes() / wav.getframerate() == seconds


async def test_canned_replies_are_keyed_by_prompt_name_and_input_hash(tmp_path: Path) -> None:
    (tmp_path / "chat").mkdir()
    messages: list[base.ChatMessage] = [{"role": "user", "content": "who wins?"}]
    replies = {"default": "fallback", input_hash(messages): {"winner": "wolf"}}
    (tmp_path / "chat" / "pick.json").write_text(json.dumps(replies), encoding="utf-8")
    chat = MockChatLLM(fixture_dir=tmp_path)
    assert json.loads(await chat.complete(messages, prompt_name="pick")) == {"winner": "wolf"}
    other: list[base.ChatMessage] = [{"role": "user", "content": "something else"}]
    assert await chat.complete(other, prompt_name="pick") == "fallback"
    with pytest.raises(LookupError, match="no-such-prompt"):
        await chat.complete(messages, prompt_name="no-such-prompt")
    (tmp_path / "structured").mkdir()
    (tmp_path / "structured" / "pick.json").write_text("{}", encoding="utf-8")
    with pytest.raises(LookupError):
        await MockStructuredLLM(fixture_dir=tmp_path).decide({}, CHALLENGER, prompt_name="pick")


def test_registry_returns_mocks_under_test_and_rejects_unknown_names() -> None:
    assert isinstance(get_provider("chat"), MockChatLLM)
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider("nope")  # type: ignore[call-overload]


def test_live_mode_fails_fast_naming_missing_settings_but_never_values() -> None:
    settings = live_settings(chat_llm_model="", course_api_key="")
    with pytest.raises(ProviderConfigError) as error:
        get_provider("chat", settings)
    assert "CHAT_LLM_MODEL" in str(error.value) and "COURSE_API_KEY" in str(error.value)
    assert DECOY_HOST not in str(error.value)
    with pytest.raises(ProviderConfigError, match="No live 'image' adapter"):
        get_provider("image", settings)


def test_live_mode_builds_the_chat_adapter_and_per_service_keys_win() -> None:
    settings = live_settings()
    assert isinstance(get_provider("chat", settings), LiveChatLLM)
    assert service_config("chat", settings).api_key.get_secret_value() == DECOY_KEY
    own = live_settings(chat_llm_api_key="decoy-own-key")
    assert service_config("chat", own).api_key.get_secret_value() == "decoy-own-key"
    config = service_config("chat", settings)
    assert DECOY_HOST not in repr(config) and DECOY_KEY not in repr(config)


# A LiveChatLLM whose HTTP calls go to handler instead of the network.
def chat_with(handler: httpx.MockTransport) -> LiveChatLLM:
    settings = live_settings()
    client = httpx.AsyncClient(transport=handler)
    return LiveChatLLM(service_config("chat", settings), settings, client=client)


async def test_live_chat_sends_bearer_key_and_schema_and_reads_the_reply() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}]})

    chat = chat_with(httpx.MockTransport(handler))
    schema = {"type": "object"}
    messages: list[base.ChatMessage] = [{"role": "user", "content": "hi"}]
    assert await chat.complete(messages, prompt_name="pick", json_schema=schema) == '{"a": 1}'
    request = seen[0]
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {DECOY_KEY}"
    body = json.loads(request.content)
    assert body["model"] == "decoy/chat-model"
    assert body["response_format"]["json_schema"] == {"name": "pick", "schema": schema}


async def test_live_chat_retries_twice_then_fails_without_leaking_host_or_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.providers.live.http.BACKOFF_S", 0)
    calls: list[int] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    messages: list[base.ChatMessage] = [{"role": "user", "content": "hi"}]
    assert await chat_with(httpx.MockTransport(flaky)).complete(messages, prompt_name="x") == "ok"
    assert len(calls) == 3

    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(ProviderError) as error:
        await chat_with(httpx.MockTransport(down)).complete(messages, prompt_name="x")
    assert "HTTP 503" in str(error.value)
    assert DECOY_HOST not in str(error.value) and DECOY_KEY not in str(error.value)


# #169: intake's chat waits 15 s and retries once; every other chat call keeps 30 s and 2 retries.
def test_intake_chat_has_a_shorter_timeout_and_fewer_retries() -> None:
    settings = live_settings()
    intake = get_intake_chat(settings)
    shared = get_provider("chat", settings)
    assert isinstance(intake, LiveChatLLM) and isinstance(shared, LiveChatLLM)
    assert (intake.timeout_s, intake.retries) == (15.0, 1)
    assert (shared.timeout_s, shared.retries) == (30.0, 2)
    assert isinstance(get_intake_chat(mock_settings()), MockChatLLM)


async def test_intake_chat_gives_up_after_one_retry_when_the_model_is_slow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.providers.live.http.BACKOFF_S", 0)
    calls: list[int] = []

    def slow(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ReadTimeout("the model took too long", request=request)

    settings = live_settings()
    client = httpx.AsyncClient(transport=httpx.MockTransport(slow))
    messages: list[base.ChatMessage] = [{"role": "user", "content": "hi"}]
    intake = LiveChatLLM(service_config("chat", settings), settings, client=client, retries=1)
    with pytest.raises(ProviderError, match="ReadTimeout"):
        await intake.complete(messages, prompt_name="x")
    assert len(calls) == 2  # one try and one retry, not three tries
    calls.clear()
    with pytest.raises(ProviderError):
        await chat_with(httpx.MockTransport(slow)).complete(messages, prompt_name="x")
    assert len(calls) == 3


async def test_intake_chat_sets_its_timeout_on_the_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeouts: list[object] = []
    real_client = httpx.AsyncClient

    def client_spy(*, timeout: object) -> httpx.AsyncClient:
        timeouts.append(timeout)
        reply = {"choices": [{"message": {"content": "ok"}}]}
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=reply))
        return real_client(transport=transport, timeout=timeout)  # type: ignore[arg-type]

    monkeypatch.setattr("app.providers.live.http.httpx.AsyncClient", client_spy)
    messages: list[base.ChatMessage] = [{"role": "user", "content": "hi"}]
    assert await get_intake_chat(live_settings()).complete(messages, prompt_name="x") == "ok"
    assert await get_provider("chat", live_settings()).complete(messages, prompt_name="x") == "ok"
    assert timeouts == [15.0, 30.0]


def test_live_mode_builds_the_structured_adapter() -> None:
    assert isinstance(get_provider("structured", live_settings()), LiveStructuredLLM)


# A LiveStructuredLLM whose HTTP calls go to handler instead of the network.
def structured_with(handler: httpx.MockTransport) -> LiveStructuredLLM:
    settings = live_settings()
    client = httpx.AsyncClient(transport=handler)
    return LiveStructuredLLM(service_config("structured", settings), settings, client=client)


async def test_live_structured_sends_the_decision_request_and_keeps_only_the_answer() -> None:
    seen: list[httpx.Request] = []
    answer = {
        "type": "choice",
        "probabilities": {"house_cat": 0.3, "duck": 0.7},
        "confidence": 0.7,
        "choice": "duck",
        "source": "local",
        "decision": "duck",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"answers": {"challenger": answer}, "model": "m"})

    state = {"winner": "gray wolf"}
    picked = await structured_with(httpx.MockTransport(handler)).decide(
        state, CHALLENGER, prompt_name="challenger"
    )
    assert picked == {
        "challenger": {
            "choice": "duck",
            "probabilities": {"house_cat": 0.3, "duck": 0.7},
            "confidence": 0.7,
        }
    }
    request = seen[0]
    assert request.url.path == "/v1/decisions"
    assert request.headers["authorization"] == f"Bearer {DECOY_KEY}"
    assert json.loads(request.content) == {
        "title": "challenger",
        "state": state,
        "questions": CHALLENGER,
    }


@pytest.mark.parametrize(
    "reply",
    [
        {"answers": {}},
        {"answers": {"challenger": {"choice": "duck", "confidence": 0.5}}},
        {
            "answers": {
                "challenger": {
                    "choice": "toaster",
                    "probabilities": {"house_cat": 0.5, "duck": 0.5},
                    "confidence": 0.5,
                }
            }
        },
        {
            "answers": {
                "challenger": {
                    "choice": ["duck"],
                    "probabilities": {"house_cat": 0.5, "duck": 0.5},
                    "confidence": 0.5,
                }
            }
        },
        {"error": "busy"},
    ],
)
async def test_live_structured_rejects_bad_answers_without_leaking_host_or_key(
    reply: dict[str, object],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reply)

    with pytest.raises(ProviderError) as error:
        await structured_with(httpx.MockTransport(handler)).decide(
            {}, CHALLENGER, prompt_name="challenger"
        )
    assert DECOY_HOST not in str(error.value) and DECOY_KEY not in str(error.value)


async def test_health_reports_mock_or_live_status_for_all_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = await health.provider_statuses(mock_settings())
    assert statuses == {name: "mock" for name in INTERFACES}

    async def fake_ping(client: httpx.AsyncClient, url: str) -> health.Status:
        return "up" if url else "down"

    monkeypatch.setattr(health, "_ping", fake_ping)
    monkeypatch.setattr(health, "_cache", None)
    live = await health.provider_statuses(live_settings())
    assert live["chat"] == "up" and live["image"] == "down" and len(live) == 8


def test_httpx_loggers_are_quiet_and_service_config_hides_secrets() -> None:
    import app.main  # noqa: F401  (sets the logger levels at import)

    for name in ("httpx", "httpcore"):
        assert logging.getLogger(name).level == logging.WARNING
    assert "base_url" not in repr(ServiceConfig("http://x", "m", live_settings().course_api_key))
