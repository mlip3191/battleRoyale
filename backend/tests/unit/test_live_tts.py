"""A07 (#45): the live TTS adapter against a fake speech server (no network)."""

import asyncio
import base64
import hashlib
import io
import json
import wave
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.config import REPO_ROOT, Settings, use_settings
from app.media import audio
from app.models.narration import Script, ScriptLine
from app.providers.live import http
from app.providers.live import tts as tts_module
from app.providers.live.http import ProviderError, post_bytes
from app.providers.live.tts import (
    REF_CONCURRENCY,
    REF_RETRIES,
    REF_TIMEOUT_S,
    LiveTTS,
    SpokenWav,
    audition_filename,
    is_stock_voice,
    is_usable_voice,
    reference_clip,
    reference_fingerprint,
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


# --- the reference voice (#45, D-67) ---------------------------------------------------------


def clip_settings(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    """Settings for a usable reference clip; overrides switch one gate off."""
    consent = tmp_path / "consent.md"
    consent.write_text("synthetic voice record", encoding="utf-8")
    clip = tmp_path / "ref.wav"
    clip.write_bytes(tiny_wav(16000))
    values: dict[str, Any] = {
        "announcer_voice_source": "cloned",
        "announcer_voice_consent_file": consent,
        "announcer_voice_ref_clip": clip,
    }
    return values | overrides


async def test_a_usable_clip_is_sent_as_base64_ref_audio(tmp_path: Path) -> None:
    server = Recorder()
    settings = clip_settings(tmp_path)
    assert await live_tts(server, **settings).speak("Hello", "default") == tiny_wav()
    [body] = server.bodies()
    assert base64.b64decode(body.pop("ref_audio")) == tiny_wav(16000)
    assert body == {
        "model": MODEL,
        "input": "Hello",
        "voice": "default",
        "response_format": "wav",
        "speed": 0.9,
    }


@pytest.mark.parametrize(
    "gate",
    ["stock_source", "no_consent", "missing_consent", "no_clip", "missing_clip", "empty", "mp3"],
)
async def test_without_every_gate_no_ref_audio_is_sent(tmp_path: Path, gate: str) -> None:
    settings = clip_settings(tmp_path)
    if gate == "stock_source":
        settings["announcer_voice_source"] = "stock"
    elif gate == "no_consent":
        settings["announcer_voice_consent_file"] = None
    elif gate == "missing_consent":
        settings["announcer_voice_consent_file"] = tmp_path / "nope.md"
    elif gate == "no_clip":
        settings["announcer_voice_ref_clip"] = ""
    elif gate == "missing_clip":
        settings["announcer_voice_ref_clip"] = tmp_path / "nope.wav"
    elif gate == "empty":
        (tmp_path / "ref.wav").write_bytes(b"")
    else:
        (tmp_path / "ref.wav").write_bytes(b"ID3\x04fake mp3 bytes")
    assert reference_clip(Settings(_env_file=None, **settings)) is None
    assert reference_fingerprint(Settings(_env_file=None, **settings)) is None
    server = Recorder()
    await live_tts(server, **settings).speak("Hello", "default")
    [body] = server.bodies()
    assert "ref_audio" not in body


@pytest.mark.parametrize(
    "first",
    [
        httpx.Response(422, text="bad ref"),
        httpx.Response(503),
        httpx.Response(200, content=b"ID3\x04fake mp3 bytes"),
    ],
)
async def test_a_failed_reference_voice_falls_back_to_the_plain_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, first: httpx.Response
) -> None:
    monkeypatch.setattr(http, "BACKOFF_S", 0.0)
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        return first if "ref_audio" in body else httpx.Response(200, content=tiny_wav())

    assert await live_tts(handler, **clip_settings(tmp_path)).speak("Hi", "default") == tiny_wav()
    with_ref = [b for b in bodies if "ref_audio" in b]
    # 503/429 are retried; a 422 or a non-WAV body is not.
    expected = REF_RETRIES + 1 if first.status_code in http.RETRY_STATUSES else 1
    assert len(with_ref) == expected
    assert bodies[-1] == {
        "model": MODEL,
        "input": "Hi",
        "voice": "default",
        "response_format": "wav",
        "speed": 0.9,
    }


async def test_a_network_error_on_the_reference_voice_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http, "BACKOFF_S", 0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        if "ref_audio" in json.loads(request.content):
            raise httpx.ConnectError("down")
        return httpx.Response(200, content=tiny_wav())

    assert await live_tts(handler, **clip_settings(tmp_path)).speak("Hi", "default") == tiny_wav()


async def test_a_reference_timeout_is_retried_then_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http, "BACKOFF_S", 0.0)
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "ref_audio" in body:
            raise httpx.ReadTimeout("hung", request=request)
        return httpx.Response(200, content=tiny_wav())

    assert await live_tts(handler, **clip_settings(tmp_path)).speak("Hi", "default") == tiny_wav()
    assert ["ref_audio" in b for b in bodies] == [True] * (REF_RETRIES + 1) + [False]


async def test_after_one_reference_failure_the_show_skips_the_clip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http, "BACKOFF_S", 0.0)
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "ref_audio" in body:
            return httpx.Response(422, text="bad ref")
        return httpx.Response(200, content=tiny_wav())

    live = live_tts(handler, **clip_settings(tmp_path))
    await live.speak("One", "default")
    bodies.clear()
    assert await live.speak("Two", "default") == tiny_wav()
    assert len(bodies) == 1 and "ref_audio" not in bodies[0]


async def test_the_reference_try_fits_the_per_file_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_post_bytes(**kwargs: Any) -> bytes:
        calls.append(kwargs)
        if "ref_audio" in kwargs["payload"]:
            raise ProviderError("down")
        return tiny_wav()

    monkeypatch.setattr(tts_module, "post_bytes", fake_post_bytes)
    live = live_tts(Recorder(), **clip_settings(tmp_path))
    await live.speak("Hi", "default")
    ref, stock = calls
    assert ref["timeout_s"] <= REF_TIMEOUT_S and ref["retries"] == REF_RETRIES == 2
    default_timeout = Settings(_env_file=None).provider_timeout_s
    assert stock["timeout_s"] == default_timeout and "retries" not in stock
    # Worst case: every clip retry, then one stock fallback, still inside the per-file limit.
    assert (REF_RETRIES + 1) * REF_TIMEOUT_S + default_timeout < audio.ITEM_TIMEOUT_S


async def test_a_blank_voice_with_a_clip_sends_ref_audio_and_no_voice(tmp_path: Path) -> None:
    server = Recorder()
    await live_tts(server, **clip_settings(tmp_path)).speak("Hello", "")
    [body] = server.bodies()
    assert "ref_audio" in body and "voice" not in body


async def test_a_failed_fallback_still_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http, "BACKOFF_S", 0.0)
    server = Recorder(httpx.Response(422, text="bad"))
    with pytest.raises(ProviderError):
        await live_tts(server, **clip_settings(tmp_path)).speak("Hi", "default")
    assert ["ref_audio" in b for b in server.bodies()] == [True, False]


def test_relative_and_blank_clip_paths_are_handled() -> None:
    assert Settings(_env_file=None, announcer_voice_ref_clip="").announcer_voice_ref_clip is None
    path = Settings(_env_file=None, announcer_voice_ref_clip="data/x.wav").announcer_voice_ref_clip
    assert path is not None and path.is_absolute()


def test_the_cache_key_changes_only_when_the_reference_voice_is_used(tmp_path: Path) -> None:
    script = Script(kind="intro", lines=[ScriptLine(speaker="announcer", text="Hello!")])
    options = speech_options(Settings(_env_file=None))
    plain = audio.narration_request(script, "default", options)
    assert "voice_ref" not in plain.request
    fingerprint = reference_fingerprint(Settings(_env_file=None, **clip_settings(tmp_path)))
    assert fingerprint is not None and len(fingerprint) == 16
    with_ref = audio.narration_request(script, "default", options, fingerprint)
    assert with_ref.request == plain.request | {"voice_ref": fingerprint}
    assert with_ref.asset_id != plain.asset_id


async def test_make_audio_hashes_the_clip_fingerprint(tmp_path: Path) -> None:
    settings = clip_settings(tmp_path)
    use_settings(mock_settings(data_dir=tmp_path, **settings))
    script = Script(kind="intro", lines=[ScriptLine(speaker="announcer", text="Hello!")])
    [asset] = await audio.make_audio([script], media_dir=tmp_path)
    fingerprint = reference_fingerprint(Settings(_env_file=None, **settings))
    options = {"model": MODEL, "speed": 0.9}
    assert asset.asset_id == audio.narration_request(script, "", options, fingerprint).asset_id


# --- which voice really spoke (#483) ---------------------------------------------------------

CLONED_RATE = 16000  # the fake server answers reference-voice requests at this rate
STOCK_RATE = 22050  # and stock requests at this one, so a saved file shows which voice it holds


class VoiceServer:
    """A fake TTS server whose reference voice fails while `ref_up` is False."""

    def __init__(self, ref_up: bool = True) -> None:
        self.ref_up = ref_up
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        if "ref_audio" not in body:
            return httpx.Response(200, content=tiny_wav(STOCK_RATE))
        if not self.ref_up:
            return httpx.Response(503)
        return httpx.Response(200, content=tiny_wav(CLONED_RATE))

    def ref_tries(self) -> int:
        return sum("ref_audio" in body for body in self.bodies)


def wav_rate(path: Path) -> int:
    with wave.open(str(path), "rb") as wav:
        return wav.getframerate()


def saved_file(media: Path, asset: Any) -> Path:
    return media / asset.url.removeprefix("/media/")


# The reference-key and stock-key requests make_audio uses for this script (mock-mode folder).
def both_keys(script: Script, settings: dict[str, Any]) -> tuple[Any, Any]:
    options = {"model": MODEL, "speed": 0.9}
    fingerprint = reference_fingerprint(Settings(_env_file=None, **settings))
    ref = audio.narration_request(script, "", options, fingerprint)
    stock = audio.narration_request(script, "", options)
    return replace(ref, mode="mock"), replace(stock, mode="mock")


async def test_speak_reports_which_voice_really_spoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http, "BACKOFF_S", 0.0)
    cloned = await live_tts(VoiceServer(), **clip_settings(tmp_path)).speak("Hi", "default")
    assert isinstance(cloned, SpokenWav) and cloned.voice == "cloned"
    fallback = live_tts(VoiceServer(ref_up=False), **clip_settings(tmp_path))
    assert (await fallback.speak("Hi", "default")).voice == "stock"
    assert fallback.ref_audio is not None  # a 503 is transient; later lines still try the clip
    assert (await fallback.speak("Again", "default")).voice == "stock"
    no_clip = await live_tts(VoiceServer(), announcer_voice_source="stock").speak("Hi", "default")
    assert no_clip.voice == "stock" and no_clip == tiny_wav(STOCK_RATE)


async def test_a_failed_reference_voice_is_not_cached_and_a_later_battle_gets_the_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http, "BACKOFF_S", 0.0)
    settings = clip_settings(tmp_path)
    use_settings(mock_settings(data_dir=tmp_path, **settings))
    media = tmp_path / "media"
    script = Script(kind="intro", lines=[ScriptLine(speaker="announcer", text="Hello!")])
    ref_key, stock_key = both_keys(script, settings)
    server = VoiceServer(ref_up=False)

    [first] = await audio.make_audio(
        [script], provider=live_tts(server, **settings), media_dir=media
    )
    assert not (media / ref_key.cached_path).exists()  # the stock file is not under the ref key
    assert first.asset_id == stock_key.asset_id
    assert wav_rate(saved_file(media, first)) == STOCK_RATE

    server.ref_up = True  # the service recovers before the next battle
    server.bodies.clear()
    [second] = await audio.make_audio(
        [script], provider=live_tts(server, **settings), media_dir=media
    )
    assert server.ref_tries() == 1  # battle 2 really sent the clip
    assert second.asset_id == ref_key.asset_id
    assert wav_rate(saved_file(media, second)) == CLONED_RATE


async def test_later_lines_and_scripts_after_a_failure_stay_off_the_reference_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http, "BACKOFF_S", 0.0)
    settings = clip_settings(tmp_path)
    use_settings(mock_settings(data_dir=tmp_path, **settings))
    media = tmp_path / "media"
    intro = Script(
        kind="intro",
        lines=[ScriptLine(speaker="announcer", text=t) for t in ("One", "Two", "Three")],
    )
    outro = Script(kind="outro", lines=[ScriptLine(speaker="announcer", text="Bye")])
    server = VoiceServer(ref_up=False)
    live = live_tts(server, **settings)  # one adapter for the whole show, as in make_audio

    assets = await audio.make_audio([intro, outro], provider=live, media_dir=media)
    # 503 is transient: the clip stays loaded and every line still tries it, then falls back.
    assert live.ref_audio is not None and server.ref_tries() >= 4
    stock_keys = {both_keys(s, settings)[1].asset_id for s in (intro, outro)}
    assert {a.asset_id for a in assets} == stock_keys
    for script in (intro, outro):
        assert not (media / both_keys(script, settings)[0].cached_path).exists()
    saved = sorted(media.rglob("*.wav"))
    assert saved == sorted(saved_file(media, a) for a in assets)
    assert all(wav_rate(path) == STOCK_RATE for path in saved)


async def test_a_script_spoken_in_both_voices_is_not_cached_under_either_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http, "BACKOFF_S", 0.0)
    settings = clip_settings(tmp_path)
    use_settings(mock_settings(data_dir=tmp_path, **settings))
    media = tmp_path / "media"
    script = Script(
        kind="intro", lines=[ScriptLine(speaker="announcer", text=t) for t in ("One", "Two")]
    )
    # Same sample rate so the two lines can be joined (VoiceServer uses different rates).
    stock_same = tiny_wav()  # 24000 Hz, 240 frames
    longer = io.BytesIO()
    with wave.open(longer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * 480)
    cloned_same = longer.getvalue()
    ref_up = True

    def flaky(request: httpx.Request) -> httpx.Response:
        nonlocal ref_up
        body = json.loads(request.content)
        if "ref_audio" not in body:
            return httpx.Response(200, content=stock_same)
        if not ref_up:
            return httpx.Response(503)
        ref_up = False  # the first line gets the clone, the second falls back
        return httpx.Response(200, content=cloned_same)

    [asset] = await audio.make_audio(
        [script], provider=live_tts(flaky, **settings), media_dir=media
    )
    ref_key, stock_key = both_keys(script, settings)
    assert not (media / ref_key.cached_path).exists()
    assert not (media / stock_key.cached_path).exists()
    assert asset.asset_id != ref_key.asset_id and asset.asset_id != stock_key.asset_id
    assert saved_file(media, asset).is_file()


async def test_a_429_on_one_line_does_not_drop_the_clip_for_later_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http, "BACKOFF_S", 0.0)
    seen: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        has_ref = "ref_audio" in body
        seen.append(has_ref)
        # First clip attempt (and its retries) are 429; later clip attempts succeed.
        if has_ref and seen.count(True) <= (REF_RETRIES + 1):
            return httpx.Response(429, json={"error": {"code": "queue_full"}})
        return httpx.Response(200, content=tiny_wav(CLONED_RATE if has_ref else STOCK_RATE))

    live = live_tts(handler, **clip_settings(tmp_path))
    first = await live.speak("One", "default")
    second = await live.speak("Two", "default")
    assert first.voice == "stock"
    assert live.ref_audio is not None
    assert second.voice == "cloned"
    assert seen.count(True) >= 2


async def test_reference_voice_requests_on_one_adapter_do_not_overlap(tmp_path: Path) -> None:
    in_flight = 0
    most = 0
    live = live_tts(Recorder(), **clip_settings(tmp_path))
    orig = live._post

    async def slow_post(payload, retries=None, timeout_s=None):
        nonlocal in_flight, most
        if "ref_audio" in payload:
            in_flight += 1
            most = max(most, in_flight)
            try:
                await asyncio.sleep(0.05)
                return await orig(payload, retries, timeout_s)
            finally:
                in_flight -= 1
        return await orig(payload, retries, timeout_s)

    live._post = slow_post  # type: ignore[method-assign]
    assert REF_CONCURRENCY == 1
    results = await asyncio.gather(*(live.speak(f"Line {i}", "default") for i in range(6)))
    assert most == 1
    assert all(getattr(wav, "voice", None) == "cloned" for wav in results)


# The committed synthetic voice files (D-67).
VOICE_DIR = REPO_ROOT / "data" / "voice"
COMMITTED_CLIP = VOICE_DIR / "announcer-reference.wav"
COMMITTED_RECORD = VOICE_DIR / "announcer-voice-record.md"


def test_the_committed_reference_clip_and_record_are_usable() -> None:
    assert COMMITTED_CLIP.stat().st_size < 1_000_000
    with wave.open(str(COMMITTED_CLIP), "rb") as clip:
        assert clip.getnchannels() == 1
        assert clip.getframerate() == 24000
        assert 0 < clip.getnframes() / clip.getframerate() < 15
    record = COMMITTED_RECORD.read_text(encoding="utf-8")
    assert "synthetic" in record and "Apache" in record


def test_settings_with_the_committed_files_load_the_reference_clip() -> None:
    settings = Settings(
        _env_file=None,
        announcer_voice_source="cloned",
        announcer_voice_consent_file="data/voice/announcer-voice-record.md",
        announcer_voice_ref_clip="data/voice/announcer-reference.wav",
    )
    assert reference_clip(settings) == COMMITTED_CLIP.read_bytes()


def test_the_record_names_the_sha256_of_the_committed_clip() -> None:
    record = COMMITTED_RECORD.read_text(encoding="utf-8")
    section = record.split("The file in the repo", 1)[1]
    line = next(x for x in section.splitlines() if x.strip().startswith("- SHA-256:"))
    written = line.split(":", 1)[1].strip().strip("`")
    assert written == hashlib.sha256(COMMITTED_CLIP.read_bytes()).hexdigest()


# --- audition file names -------------------------------------------------------------------


def test_audition_filenames_are_safe_and_include_id_and_name() -> None:
    name = audition_filename({"id": "default", "name": "Bundled voice"})
    assert name == "default-Bundled-voice.wav"
    ugly = audition_filename({"id": "voice_abc", "name": "<img src=x onerror=alert(1)>"})
    assert ugly.startswith("voice_abc-") and ugly.endswith(".wav")
    assert "<" not in ugly and ">" not in ugly and "/" not in ugly and "\\" not in ugly
    assert audition_filename({"id": "just-id"}) == "just-id.wav"
