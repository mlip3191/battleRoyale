"""The announcer's voice and the soundtrack (A07, pipeline step 5).

Narration: one WAV file per script (intro, play-by-play, outro). Each line is spoken by the TTS
provider and the lines are joined with a short pause. Every narration asset carries the
script_kind it reads, so the front end plays the right file in each part of the show.

Music: one track whose prompt is built in code only, from each stat sheet's media_name (checked
by app/safety/media_names.py) plus fixed sports-broadcast wording. Never from display_name or
anything the user typed; an unsafe name is left out of the prompt.

Voice consent: a cloned announcer voice needs a consent file on disk. Without one, cloning is
refused and the stock voice (ANNOUNCER_VOICE_ID) is used. There is no clone call yet, so the
stock voice is used either way for now.

Files are cached under <data_dir>/media/audio/ by a hash of the full request, so a repeat makes
no provider call. A failed item gives no asset at all (no silent stand-in file) and nothing is
cached; the public make_* functions never raise. Provider audio must be WAV for now: that is what
the mocks return, and the lines can only be joined if they are.
"""

import asyncio
import functools
import hashlib
import io
import json
import logging
import wave
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.config import Settings, get_settings
from app.media import images
from app.models.matchup import Matchup
from app.models.media import Asset
from app.models.narration import Script
from app.models.simulation import SimulationResult
from app.models.stats import StatSheet
from app.providers.base import TTS, MusicGen
from app.providers.registry import get_provider
from app.safety.media_names import safe_media_name

logger = logging.getLogger(__name__)

AUDIO_VERSION = "a1"  # bump when the way files are made changes, so old caches are not reused
ITEM_TIMEOUT_S = 48.0  # per file; the stage passes its own share of the stage budget
LINE_PAUSE_S = 0.4  # silence between two spoken lines
MUSIC_SECONDS = 30.0
MUSIC_STYLE = "upbeat retro sports-broadcast theme, brass and synth"
MUSIC_TAIL = "instrumental, no vocals"
HASH_PREFIX = 16  # hex characters of the request hash used in file names

ScriptKind = Literal["intro", "play_by_play", "outro"]


class AudioError(ValueError):
    """The provider's audio could not be read or joined."""


@dataclass(frozen=True)
class AudioRequest:
    """Everything that decides one audio file: where it is cached and the full request."""

    kind: Literal["narration_audio", "music"]
    request: dict[str, object]
    """The full request (text or prompt, voice, and every fixed parameter); its hash names it."""
    script_kind: ScriptKind | None = None

    # sha256 of the full request.
    @property
    def prompt_hash(self) -> str:
        text = json.dumps(self.request, sort_keys=True)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    # Stable id: the kind (and script) plus the start of the request hash.
    @property
    def asset_id(self) -> str:
        short = self.prompt_hash[:HASH_PREFIX]
        if self.kind == "music":
            return f"music-{short}"
        return f"narration-{self.script_kind}-{short}"

    # File path under the media folder, e.g. audio/narration-intro-0123abcd.wav.
    @property
    def path(self) -> Path:
        return Path("audio") / f"{self.asset_id}.wav"

    # The asset for the saved file (only ever built for a file that exists).
    def asset(self) -> Asset:
        return Asset(
            asset_id=self.asset_id,
            kind=self.kind,
            url=f"/media/{self.path.as_posix()}",
            prompt_hash=self.prompt_hash,
            script_kind=self.script_kind,
        )


# --- voice consent ------------------------------------------------------------------------------


# True when ANNOUNCER_VOICE_CONSENT_FILE names a file that exists.
def consent_on_file(settings: Settings) -> bool:
    path = settings.announcer_voice_consent_file
    return path is not None and path.is_file()


# The voice id to speak with. A cloned voice without consent is refused; with consent there is
# still no clone call yet, so the stock voice is used in every case for now.
def announcer_voice(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if settings.announcer_voice_source.strip().lower() == "cloned":
        if not consent_on_file(settings):
            logger.warning("cloned announcer voice refused: no consent file; using stock voice")
        else:
            logger.info("cloned announcer voice not available yet; using stock voice")
    return settings.announcer_voice_id


# --- requests -----------------------------------------------------------------------------------


# The text spoken for one script: its non-blank lines, in order.
def spoken_lines(script: Script) -> list[str]:
    return [line.text.strip() for line in script.lines if line.text.strip()]


def narration_request(script: Script, voice_id: str) -> AudioRequest:
    return AudioRequest(
        kind="narration_audio",
        script_kind=script.kind,
        request={
            "version": AUDIO_VERSION,
            "script_kind": script.kind,
            "lines": spoken_lines(script),
            "voice_id": voice_id,
            "pause_s": LINE_PAUSE_S,
        },
    )


# The music prompt: fixed broadcast wording plus each side's safe media_name (unsafe ones left
# out; a mirror match names the fighter once). With no safe name the prompt names no fighter.
def music_prompt(sheets: Sequence[StatSheet]) -> str:
    names: list[str] = []
    for sheet in sheets:
        name = safe_media_name(sheet.media_name)
        if name is not None and name not in names:
            names.append(name)
    seconds = f"{MUSIC_SECONDS:g} seconds"
    if not names:
        return f"{MUSIC_STYLE}, {seconds}, {MUSIC_TAIL}"
    matchup = " versus ".join(names)
    return f"{MUSIC_STYLE} for a showdown: {matchup}, {seconds}, {MUSIC_TAIL}"


def music_request(prompt: str) -> AudioRequest:
    return AudioRequest(
        kind="music",
        request={"version": AUDIO_VERSION, "prompt": prompt, "seconds": MUSIC_SECONDS},
    )


# --- public ------------------------------------------------------------------------------------


# One narration file per script, in the scripts' order; a script that fails is left out.
# Never raises.
async def make_audio(
    scripts: Sequence[Script],
    *,
    provider: TTS | None = None,
    media_dir: Path | None = None,
    timeout_s: float = ITEM_TIMEOUT_S,
) -> list[Asset]:
    try:
        voice_id = announcer_voice()
    except Exception as error:
        logger.warning("announcer voice unavailable (%s)", type(error).__name__)
        return []
    if provider is None:
        try:
            provider = get_provider("tts")
        except Exception as error:  # live settings missing: cached files can still be used
            logger.warning("tts provider unavailable (%s)", type(error).__name__)
    jobs = [
        _bounded(
            narration_request(script, voice_id),
            functools.partial(_speak, script=script, voice_id=voice_id),
            provider,
            media_dir,
            timeout_s,
        )
        for script in scripts
        if spoken_lines(script)
    ]
    made = await asyncio.gather(*jobs)
    return [asset for asset in made if asset is not None]


# The soundtrack, or None if it could not be made. The matchup and result do not change the
# prompt: the music plays all show long, so it must not hint at the verdict. Never raises.
async def make_music(
    matchup: Matchup,
    result: SimulationResult | None,
    sheets: Sequence[StatSheet],
    *,
    provider: MusicGen | None = None,
    media_dir: Path | None = None,
    timeout_s: float = ITEM_TIMEOUT_S,
) -> Asset | None:
    try:
        prompt = music_prompt(sheets)
    except Exception as error:
        logger.warning("music prompt could not be built (%s)", type(error).__name__)
        return None
    if provider is None:
        try:
            provider = get_provider("music")
        except Exception as error:  # live settings missing: a cached file can still be used
            logger.warning("music provider unavailable (%s)", type(error).__name__)

    async def compose(music: MusicGen) -> bytes:
        data = await music.compose(prompt, MUSIC_SECONDS)
        return await asyncio.to_thread(_checked_wav, data)

    return await _bounded(music_request(prompt), compose, provider, media_dir, timeout_s)


# --- helpers -----------------------------------------------------------------------------------


# Speak each line in turn, then join them with a short pause between lines.
async def _speak(tts: TTS, script: Script, voice_id: str) -> bytes:
    clips = [await tts.speak(text, voice_id) for text in spoken_lines(script)]
    return await asyncio.to_thread(join_wavs, clips, LINE_PAUSE_S)


# The cached file if there is one, else make it within the time limit and save it. Anything
# going wrong gives None and caches nothing.
async def _bounded[P](
    request: AudioRequest,
    make: Callable[[P], Awaitable[bytes]],
    provider: P | None,
    media_dir: Path | None,
    timeout_s: float,
) -> Asset | None:
    file = (media_dir or images.media_root()) / request.path
    try:
        if file.is_file():
            return request.asset()
        if provider is None:
            raise RuntimeError("no provider")
        data = await asyncio.wait_for(make(provider), timeout_s)
        await asyncio.to_thread(images._save, file, data)
    except Exception as error:
        logger.warning("audio %s not made (%s)", request.asset_id, type(error).__name__)
        return None
    return request.asset()


# Read WAV bytes into (channels, sample width, frame rate) and the raw frames.
def _read_wav(data: bytes) -> tuple[tuple[int, int, int], bytes]:
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            params = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError) as error:
        raise AudioError("the provider's audio is not a readable WAV file") from error
    return params, frames


# Check the bytes are a readable WAV file and return them unchanged.
def _checked_wav(data: bytes) -> bytes:
    _read_wav(data)
    return data


# One WAV file: the clips in order with `pause_s` of silence between each pair.
def join_wavs(clips: Sequence[bytes], pause_s: float) -> bytes:
    if not clips:
        raise AudioError("there is nothing to join")
    read = [_read_wav(clip) for clip in clips]
    params = read[0][0]
    if any(p != params for p, _ in read):
        raise AudioError("the clips do not share one format")
    channels, width, rate = params
    zero = b"\x80" if width == 1 else b"\x00" * width  # 8-bit WAV is unsigned
    silence = zero * (int(rate * pause_s) * channels)
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(silence.join(frames for _, frames in read))
    return out.getvalue()
