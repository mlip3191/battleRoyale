"""A07 (#45): the live TTS adapter against a fake speech server (no network)."""

import io
import json
import wave
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings, use_settings
from app.media import audio
from app.models.narration import Script, ScriptLine
from app.providers.live import http
from app.providers.live.http import ProviderError, post_bytes
from app.providers.live.tts import (
    LiveTTS,
    audition_filename,
    is_stock_voice,
    is_usable_voice,
    speech_options,
)
from app.providers.registry import ServiceConfig, get_provider
from tests.conftest import mock_settings

DECOY_KEY = "decoy-key-0000"
DECOY_URL = "http://decoy-host.invalid:9008"
MODEL = "chatterbox-v3"
VOICES = {
    "object": "list",
    "data": [
        {
            "id": "default",
            "object": "voice",
            "name": "Bundled voice",
            "created": 0,
            "duration": 0.0,
        },
        {"id": "clone-1", "object": "voice", "name": "<b>x</b>", "created": 17, "duration": 4.2},
    ],
}


def tiny_wav(rate: int = 24000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * 240)
    return out.getvalue()


class Recorder:
    """A fake TTS server that keeps every request and answers with WAV or the voice list."""

    def __init__(self, speech: httpx.Response | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.speech = speech or httpx.Response(
            200, content=tiny_wav(), headers={"content-type": "audio/wav"}
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["authorization"] == f"Bearer {DECOY_KEY}"
        if request.url.path == "/v1/voices":
            return httpx.Response(200, json=VOICES)
        assert request.url.path == "/v1/audio/speech"
        return self.speech

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests if r.method == "POST"]


def live_tts(handler: Callable[[httpx.Request], httpx.Response], **settings: Any) -> LiveTTS:
    config = ServiceConfig(base_url=DECOY_URL, model=MODEL, api_key=SecretStr(DECOY_KEY))
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LiveTTS(config, Settings(_env_file=None, **settings), client=client)


# --- the speech request --------------------------------------------------------------------


async def test_speak_sends_model_text_voice_wav_and_the_default_speed() -> None:
    server = Recorder()
    data = await live_tts(server).speak("THE GRIZZLY!", "default")
    assert data == tiny_wav()
    assert server.bodies() == [
        {
            "model": MODEL,
            "input": "THE GRIZZLY!",
            "voice": "default",
            "response_format": "wav",
            "speed": 0.9,
        }
    ]


async def test_speed_one_is_left_out_and_no_style_pitch_or_cloning_is_sent() -> None:
    server = Recorder()
    live = live_tts(server, announcer_voice_speed=1.0, announcer_voice_style="gruff")
    await live.speak("Hello", "default")
    [body] = server.bodies()
    assert body == {"model": MODEL, "input": "Hello", "voice": "default", "response_format": "wav"}
    for field in ("speed", "style", "pitch", "ref_audio", "exaggeration"):
        assert field not in body


@pytest.mark.parametrize("voice_id", ["", "   ", "replace-me", "REPLACE-ME-voice"])
async def test_a_blank_or_placeholder_voice_id_is_left_out(voice_id: str) -> None:
    server = Recorder()
    await live_tts(server).speak("Hello", voice_id)
    [body] = server.bodies()
    assert "voice" not in body
    assert body == {"model": MODEL, "input": "Hello", "response_format": "wav", "speed": 0.9}


async def test_the_default_voice_id_is_still_sent() -> None:
    server = Recorder()
    await live_tts(server).speak("Hello", "default")
    [body] = server.bodies()
    assert body["voice"] == "default"


async def test_a_voice_id_with_stray_spaces_is_sent_trimmed() -> None:
    server = Recorder()
    await live_tts(server).speak("Hello", " default ")
    [body] = server.bodies()
    assert body["voice"] == "default"


@pytest.mark.parametrize(
    ("voice_id", "usable"),
    [("default", True), (" default ", True), ("", False), ("  ", False), ("Replace-Me", False)],
)
def test_is_usable_voice_rejects_blank_and_placeholder_ids(voice_id: str, usable: bool) -> None:
    assert is_usable_voice(voice_id) is usable


@pytest.mark.parametrize("reply", [b"ID3\x04fake mp3 bytes", b"", b"RIFF\x00\x00"])
async def test_a_reply_that_is_not_a_wav_raises(reply: bytes) -> None:
    server = Recorder(httpx.Response(200, content=reply, headers={"content-type": "audio/mpeg"}))
    with pytest.raises(ProviderError, match="not a WAV"):
        await live_tts(server).speak("Hello", "default")


async def test_an_http_error_raises_without_the_host_or_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http, "BACKOFF_S", 0.0)
    server = Recorder(httpx.Response(422, text="bad voice"))
    with pytest.raises(ProviderError) as error:
        await live_tts(server).speak("Hello", "nope")
    assert error.value.status == 422 and error.value.detail == "bad voice"
    assert "decoy-host" not in str(error.value) and DECOY_KEY not in str(error.value)
    assert len(server.requests) == 1  # a 422 is not retried


async def test_a_busy_server_is_retried_then_gives_the_wav(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http, "BACKOFF_S", 0.0)
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(503)
        return httpx.Response(200, content=tiny_wav())

    assert await live_tts(handler).speak("Hello", "default") == tiny_wav()
    assert len(attempts) == 2


async def test_post_bytes_returns_the_raw_reply_without_parsing_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"a": 1}
        return httpx.Response(200, content=b"\xff\xfe not json")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    data = await post_bytes(
        provider="tts",
        base_url=DECOY_URL,
        path="/x",
        api_key=DECOY_KEY,
        payload={"a": 1},
        timeout_s=1.0,
        client=client,
    )
    assert data == b"\xff\xfe not json"


# --- voices --------------------------------------------------------------------------------


async def test_list_voices_parses_the_documented_shape_and_spots_the_stock_voice() -> None:
    voices = await live_tts(Recorder()).list_voices()
    assert [v["id"] for v in voices] == ["default", "clone-1"]
    assert [v["id"] for v in voices if is_stock_voice(v)] == ["default"]


async def test_a_voice_list_without_data_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"object": "list"})

    with pytest.raises(ProviderError, match="no data list"):
        await live_tts(handler).list_voices()


# --- settings and the registry -------------------------------------------------------------


def test_live_mode_builds_the_tts_adapter_with_the_default_model() -> None:
    # Build settings from a dict so a decoy key is not a keyword argument (gitleaks false positive).
    values: dict[str, object] = {
        "provider_mode": "live",
        "course_api_key": DECOY_KEY,
        "tts_url": DECOY_URL,
    }
    settings = Settings(_env_file=None, **values)
    assert settings.tts_model == MODEL and settings.announcer_voice_speed == 0.9
    assert isinstance(get_provider("tts", settings), LiveTTS)


@pytest.mark.parametrize("speed", [0.25, 4.0])
def test_the_speed_accepts_the_ends_of_the_service_range(speed: float) -> None:
    assert Settings(_env_file=None, announcer_voice_speed=speed).announcer_voice_speed == speed


@pytest.mark.parametrize("speed", [0.2, 4.1])
def test_a_speed_outside_the_service_range_is_rejected(speed: float) -> None:
    with pytest.raises(ValidationError, match="announcer_voice_speed"):
        Settings(_env_file=None, announcer_voice_speed=speed)


def test_the_narration_cache_key_changes_with_the_speed_and_model() -> None:
    script = Script(kind="intro", lines=[ScriptLine(speaker="announcer", text="Hello!")])

    def asset_id(**settings: Any) -> str:
        options = speech_options(Settings(_env_file=None, **settings))
        return audio.narration_request(script, "default", options).asset_id

    base = asset_id()
    assert asset_id(announcer_voice_speed=1.0) != base
    assert asset_id(announcer_voice_speed=0.8) != base
    assert asset_id(tts_model="other-model") != base
    assert asset_id() == base  # the same settings reuse the same file
    request = audio.narration_request(script, "default", speech_options(Settings(_env_file=None)))
    assert request.request["model"] == MODEL and request.request["speed"] == 0.9


async def test_make_audio_hashes_the_speech_options_from_settings(tmp_path: Any) -> None:
    use_settings(mock_settings(data_dir=tmp_path, announcer_voice_speed=0.75))
    script = Script(kind="intro", lines=[ScriptLine(speaker="announcer", text="Hello!")])
    [asset] = await audio.make_audio([script], media_dir=tmp_path)
    options = {"model": MODEL, "speed": 0.75}
    assert asset.asset_id == audio.narration_request(script, "", options).asset_id


# --- audition file names -------------------------------------------------------------------


def test_audition_filenames_are_safe_and_include_id_and_name() -> None:
    name = audition_filename({"id": "default", "name": "Bundled voice"})
    assert name == "default-Bundled-voice.wav"
    ugly = audition_filename({"id": "voice_abc", "name": "<img src=x onerror=alert(1)>"})
    assert ugly.startswith("voice_abc-") and ugly.endswith(".wav")
    assert "<" not in ugly and ">" not in ugly and "/" not in ugly and "\\" not in ugly
    assert audition_filename({"id": "just-id"}) == "just-id.wav"
