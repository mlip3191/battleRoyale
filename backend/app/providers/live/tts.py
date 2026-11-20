"""Live TTS: POST /v1/audio/speech on the course text-to-speech endpoint (Chatterbox).

Every call asks for WAV (response_format "wav"), because app/media/audio.py can only join WAV
lines; the service's default is MP3. The request sends the model, the text, the stock voice id,
and the announcer's speed when it is not 1. A blank or "replace-me" voice id is left out, so the
service's default voice reads the line instead of the call failing. The endpoint has no style or
pitch field, so ANNOUNCER_VOICE_STYLE is never sent (docs/providers.md).

Reference voice (#45, D-67, synthetic only): when ANNOUNCER_VOICE_SOURCE is "cloned", a consent
file is on disk, and ANNOUNCER_VOICE_REF_CLIP names a readable WAV, each line is first requested
with the clip added as base64 `ref_audio` (one try, a shorter timeout, no retry). If that fails
or the reply is not a WAV, the same line is requested again exactly as without a clip, so the
show still gets the stock voice, and the rest of that show skips the clip.
"""

import base64
import hashlib
import io
import logging
import re
import wave
from typing import TYPE_CHECKING, Any

import httpx

from app.config import Settings
from app.providers.live.http import ProviderError, get_json, post_bytes

if TYPE_CHECKING:
    from app.providers.registry import ServiceConfig

logger = logging.getLogger(__name__)

RESPONSE_FORMAT = "wav"
REF_RETRIES = 0  # one reference-voice try; the stock request after it keeps the normal retries
# A normal line takes about 5 s; a hung clip request must leave time for the stock fallback
# inside the per-file limit (audio.ITEM_TIMEOUT_S).
REF_TIMEOUT_S = 12.0
FINGERPRINT_CHARS = 16  # hex characters of the clip's sha256 used in the audio cache key


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

    # Return WAV bytes of text read in voice_id (blank or placeholder ids use the service default).
    # With a reference clip loaded, try it first and fall back to the plain request if it fails.
    async def speak(self, text: str, voice_id: str) -> bytes:
        payload = self.options | {"input": text, "response_format": RESPONSE_FORMAT}
        if is_usable_voice(voice_id):
            payload["voice"] = voice_id.strip()
        if self.ref_audio is not None:
            try:
                timeout_s = min(self.timeout_s, REF_TIMEOUT_S)
                data = await self._post(
                    payload | {"ref_audio": self.ref_audio}, REF_RETRIES, timeout_s
                )
                return _checked_wav(data)
            except (ProviderError, httpx.HTTPError) as error:  # a timeout arrives as ProviderError
                # make_audio builds one adapter per show (get_provider returns a new one each
                # call), so dropping the clip here means the rest of this show skips it.
                if self.ref_audio is not None:
                    self.ref_audio = None
                    logger.warning(
                        "reference voice failed (%s); the rest of this show uses the stock voice",
                        type(error).__name__,
                    )
        return _checked_wav(await self._post(payload))

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
