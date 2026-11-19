"""Live TTS: POST /v1/audio/speech on the course text-to-speech endpoint (Chatterbox).

Every call asks for WAV (response_format "wav"), because app/media/audio.py can only join WAV
lines; the service's default is MP3. The request sends the model, the text, the stock voice id,
and the announcer's speed when it is not 1. The endpoint has no style or pitch field, so
ANNOUNCER_VOICE_STYLE is never sent, and ref_audio (voice cloning) is never sent either
(docs/providers.md).
"""

import io
import re
import wave
from typing import TYPE_CHECKING, Any

import httpx

from app.config import Settings
from app.providers.live.http import ProviderError, get_json, post_bytes

if TYPE_CHECKING:
    from app.providers.registry import ServiceConfig

RESPONSE_FORMAT = "wav"


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

    # Return WAV bytes of text read in voice_id.
    async def speak(self, text: str, voice_id: str) -> bytes:
        payload = self.options | {
            "input": text,
            "voice": voice_id,
            "response_format": RESPONSE_FORMAT,
        }
        data = await post_bytes(
            provider="tts",
            base_url=self.config.base_url,
            path="/v1/audio/speech",
            api_key=self.config.api_key.get_secret_value(),
            payload=payload,
            timeout_s=self.timeout_s,
            client=self.client,
        )
        return _checked_wav(data)

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


# True for a voice that ships with the service (not a user-uploaded clone).
def is_stock_voice(voice: dict[str, Any]) -> bool:
    return voice.get("id") == "default" or voice.get("created") == 0


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
