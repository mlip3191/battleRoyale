"""Live TTS: POST /v1/audio/speech on the course text-to-speech endpoint (Chatterbox).

Every call asks for WAV (response_format "wav"), because app/media/audio.py can only join WAV
lines; the service's default is MP3. The request sends the model, the text, the stock voice id,
and the announcer's speed when it is not 1. A blank or "replace-me" voice id is left out, so the
service's default voice reads the line instead of the call failing. The endpoint has no style or
pitch field, so ANNOUNCER_VOICE_STYLE is never sent (docs/providers.md).

Reference voice (#45, D-67, synthetic only): when ANNOUNCER_VOICE_SOURCE is "cloned", a consent
file is on disk, and ANNOUNCER_VOICE_REF_CLIP names a readable WAV, each line is first requested
with the clip added as base64 `ref_audio` (a shorter timeout, with retries
on a full queue). If that fails
or the reply is not a WAV, the same line is requested again exactly as without a clip, so the
show still gets the stock voice. A 429 is retried and does not disable the clip for later
lines. A response that rejects the clip (such as HTTP 422) disables it at once, and so do two
lines in a row that time out or get a 5xx (#570); after the first such line the next clip try
gets no retries, so a hung service leaves time for the stock voice. Any clip success resets the
count. Reference requests on one adapter are spoken one at a time, because make_audio speaks a
few lines at once (the play-by-play and outro together) and a burst of clip requests fills the
speech queue.

speak() returns a SpokenWav: plain WAV bytes plus `.voice`, "cloned" when the reference clip
spoke the line and "stock" otherwise. app/media/audio.py reads it per line, so a stock-voiced file
is never cached under the reference-voice key (#483).
"""

import asyncio
import base64
import hashlib
import io
import logging
import re
import wave
from typing import TYPE_CHECKING, Any, Literal, Self

import httpx

from app.config import Settings
from app.providers.live.http import ProviderError, get_json, post_bytes

if TYPE_CHECKING:
    from app.providers.registry import ServiceConfig

logger = logging.getLogger(__name__)

RESPONSE_FORMAT = "wav"
REF_RETRIES = 2  # retry 429/5xx/timeout on the clip request; a queue-full is transient
REF_CONCURRENCY = 1  # one in-flight clip request; make_audio speaks several lines at once
# Statuses that mean the clip itself was rejected, so later lines should not resend it. 400 is
# left out: nothing shows the service uses it for a bad clip, and a bad line of text would
# otherwise switch the whole show to the stock voice (#570).
REF_REJECTED_STATUSES = frozenset({413, 415, 422})
# Clip lines in a row that may time out or get a 5xx before the show stops trying the clip (#570).
REF_FAILURES_TO_STOP = 2
# Retries for the clip once a line has just failed that way: one quick check, so a hung service
# costs about 50 s, not 75 s, and the rest of the show still fits audio.ITEM_TIMEOUT_S (#570).
REF_PROBE_RETRIES = 0
# A normal line takes about 5 s; a hung clip request must leave time for the stock fallback
# inside the per-file limit (audio.ITEM_TIMEOUT_S), including retries.
REF_TIMEOUT_S = 12.0
FINGERPRINT_CHARS = 16  # hex characters of the clip's sha256 used in the audio cache key

SpokenVoice = Literal["cloned", "stock", "mixed"]


class SpokenWav(bytes):
    """WAV bytes that also say which voice really spoke them (compares equal to plain bytes).

    The voice rides on the returned value, not on the adapter, because make_audio speaks several
    scripts at once on one adapter.
    """

    voice: SpokenVoice

    def __new__(cls, data: bytes, voice: SpokenVoice) -> Self:
        wav = super().__new__(cls, data)
        wav.voice = voice
        return wav


# The fixed speech fields that change the sound of every line: the model, and the speed when
# it is not 1. audio.py hashes these too, so a new speed or model never reuses an old file.
def speech_options(settings: Settings) -> dict[str, Any]:
    options: dict[str, Any] = {"model": settings.tts_model}
    if settings.announcer_voice_speed != 1:
        options["speed"] = settings.announcer_voice_speed
    return options


class LiveTTS:
    """Reads one line aloud in a stock voice and returns WAV bytes."""

    def __init__(
        self, config: "ServiceConfig", settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        self.config = config
        self.timeout_s = settings.provider_timeout_s
        self.client = client
        self.options = speech_options(settings) | {"model": config.model}
        clip = reference_clip(settings)
        self.ref_audio = None if clip is None else base64.b64encode(clip).decode("ascii")
        self._ref_limit = asyncio.Semaphore(REF_CONCURRENCY)
        self._ref_failures = 0  # clip lines in a row that timed out or got a 5xx (#570)

    # Return WAV bytes of text read in voice_id (blank or placeholder ids use the service default).
    # With a reference clip loaded, try it first and fall back to the plain request if it fails.
    # The reply's .voice says which one spoke: "cloned" or "stock".
    async def speak(self, text: str, voice_id: str) -> SpokenWav:
        payload = self.options | {"input": text, "response_format": RESPONSE_FORMAT}
        if is_usable_voice(voice_id):
            payload["voice"] = voice_id.strip()
        if self.ref_audio is not None:
            cloned = await self._speak_cloned(payload)
            if cloned is not None:
                return cloned
        return SpokenWav(_checked_wav(await self._post(payload)), "stock")

    # The line in the reference voice, or None when the stock voice should read it. One clip
    # request at a time on this adapter (shared by the whole show); a clip turned off while
    # this line waited is not sent, and right after a timeout or 5xx it is tried only once.
    # A 429, another 4xx, or a non-WAV reply between two failing lines neither counts nor
    # resets, so "fail, 429, fail" turns the clip off; after one failure, clip tries stay single
    # requests until a success.
    async def _speak_cloned(self, payload: dict[str, Any]) -> SpokenWav | None:
        timeout_s = min(self.timeout_s, REF_TIMEOUT_S)
        async with self._ref_limit:
            if self.ref_audio is None:
                return None
            retries = REF_RETRIES if self._ref_failures == 0 else REF_PROBE_RETRIES
            try:
                data = await self._post(payload | {"ref_audio": self.ref_audio}, retries, timeout_s)
            except (ProviderError, httpx.HTTPError) as error:  # a timeout arrives as ProviderError
                self._clip_failed(error, service_failing=_service_failing(error))
                return None
            try:
                wav = SpokenWav(_checked_wav(data), "cloned")
            except ProviderError as error:  # a reply, but not a WAV: not the service failing
                self._clip_failed(error, service_failing=False)
                return None
            self._ref_failures = 0
            return wav

    # Log one failed clip line and decide whether later lines still try the clip: a rejected
    # clip stops at once; REF_FAILURES_TO_STOP timeouts or 5xx in a row stop it too (#570).
    def _clip_failed(self, error: BaseException, service_failing: bool) -> None:
        label = _ref_failure_label(error)
        if _clip_rejected(error):
            self.ref_audio = None
            logger.warning(
                "reference voice rejected (%s); the rest of this show uses the stock voice", label
            )
            return
        if service_failing:
            self._ref_failures += 1
            if self._ref_failures >= REF_FAILURES_TO_STOP:
                self.ref_audio = None
                logger.warning(
                    "reference voice turned off for this show after %d failures in a row (%s)",
                    self._ref_failures,
                    label,
                )
                return
        logger.warning(
            "reference voice failed for this line (%s); using stock for this line", label
        )

    # POST one speech request and return the raw reply bytes.
    async def _post(
        self, payload: dict[str, Any], retries: int | None = None, timeout_s: float | None = None
    ) -> bytes:
        extra = {} if retries is None else {"retries": retries}
        return await post_bytes(
            provider="tts",
            base_url=self.config.base_url,
            path="/v1/audio/speech",
            api_key=self.config.api_key.get_secret_value(),
            payload=payload,
            timeout_s=self.timeout_s if timeout_s is None else timeout_s,
            client=self.client,
            **extra,
        )

    # Every voice the service lists, as dicts with id, name, created, and duration.
    async def list_voices(self) -> list[dict[str, Any]]:
        reply = await get_json(
            provider="tts",
            base_url=self.config.base_url,
            path="/v1/voices",
            api_key=self.config.api_key.get_secret_value(),
            timeout_s=self.timeout_s,
            client=self.client,
        )
        try:
            voices = [voice for voice in reply["data"] if isinstance(voice, dict)]
        except (KeyError, TypeError) as error:
            raise ProviderError("Live 'tts' voice list had no data list.") from error
        return [voice for voice in voices if isinstance(voice.get("id"), str)]


# True when the speech service rejected the clip itself, not a transient queue or timeout.
def _clip_rejected(error: BaseException) -> bool:
    return getattr(error, "status", None) in REF_REJECTED_STATUSES


# True when a clip request failed because the service is struggling: a 5xx, or no reply at
# all (a timeout or lost connection, which post_bytes raises as a ProviderError without a
# status). A 429 (queue full) or another 4xx is not counted.
def _service_failing(error: BaseException) -> bool:
    status = getattr(error, "status", None)
    if isinstance(status, int):
        return status >= 500
    return isinstance(error, (ProviderError, httpx.TransportError))


# HTTP status when we have one, otherwise the error type. Never includes a host or key.
def _ref_failure_label(error: BaseException) -> str:
    status = getattr(error, "status", None)
    if isinstance(status, int):
        return f"HTTP {status}"
    return type(error).__name__


# False for a blank or "replace-me" voice id (422 risk); speak() skips it, startup warns.
def is_usable_voice(voice_id: str) -> bool:
    return bool(voice_id.strip()) and "replace-me" not in voice_id.lower()


# True for a voice that ships with the service (not a user-uploaded clone).
def is_stock_voice(voice: dict[str, Any]) -> bool:
    return voice.get("id") == "default" or voice.get("created") == 0


# The reference clip's bytes when the source is cloned, consent is on file, and the clip is a
# readable non-empty WAV; else None (with one warning saying why if the source is cloned).
# Never raises. warn=False skips the warning for callers that log their own message.
def reference_clip(settings: Settings, *, warn: bool = True) -> bytes | None:
    if settings.announcer_voice_source.strip().lower() != "cloned":
        return None
    problem, clip = _load_clip(settings)
    if problem is not None and warn:
        logger.warning("announcer reference clip not used: %s; using stock voice", problem)
    return clip


# Short sha256 of the reference clip in use (for the audio cache key), or None if none is used.
def reference_fingerprint(settings: Settings) -> str | None:
    clip = reference_clip(settings, warn=False)
    if clip is None:
        return None
    return hashlib.sha256(clip).hexdigest()[:FINGERPRINT_CHARS]


# (why the clip can't be used, None) or (None, the clip's bytes). Logs nothing.
def _load_clip(settings: Settings) -> tuple[str | None, bytes | None]:
    consent = settings.announcer_voice_consent_file
    path = settings.announcer_voice_ref_clip
    try:
        if consent is None or not consent.is_file():
            return "no consent file", None
        if path is None:
            return "ANNOUNCER_VOICE_REF_CLIP is not set", None
        if not path.is_file():
            return "the clip file does not exist", None
        clip = path.read_bytes()
        _checked_wav(clip)
    except ProviderError:
        return "the clip is not a readable WAV", None
    except Exception as error:
        return f"the clip could not be read ({type(error).__name__})", None
    return None, clip


# Check the reply is a readable WAV file and return it unchanged.
def _checked_wav(data: bytes) -> bytes:
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            if wav.getnframes() <= 0:
                raise ProviderError("Live 'tts' reply was an empty WAV.")
    except (wave.Error, EOFError) as error:
        raise ProviderError("Live 'tts' reply was not a WAV file.") from error
    return data


# A safe WAV file name from the voice id and name (ids and names are untrusted text).
NAME_MAX = 80


def audition_filename(voice: dict[str, Any]) -> str:
    voice_id = str(voice.get("id") or "unknown")
    name = str(voice.get("name") or "")
    raw = f"{voice_id}-{name}" if name else voice_id
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-.")
    if not cleaned:
        cleaned = "voice"
    return f"{cleaned[:NAME_MAX]}.wav"
