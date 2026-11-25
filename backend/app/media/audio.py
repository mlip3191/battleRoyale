"""The announcer's voice and the soundtrack (A07, pipeline step 5).

Narration: one WAV file per script (intro, play-by-play, outro). Each line is spoken by the TTS
provider and the lines are joined with a short pause. Every narration asset carries the
script_kind it reads, so the front end plays the right file in each part of the show.

Music: one track whose prompt is built in code only, from each stat sheet's media_name (checked
by app/safety/media_names.py) plus fixed sports-broadcast wording. Never from display_name or
anything the user typed; an unsafe name is left out of the prompt.

Voice consent: a cloned announcer voice needs a consent file on disk. Without one, cloning is
refused and the stock voice (ANNOUNCER_VOICE_ID) is used. With consent and a readable reference
clip (ANNOUNCER_VOICE_REF_CLIP, a synthetic voice, #45, D-67), the live TTS adapter sends the
clip as `ref_audio` and falls back to the stock voice if that fails. The clip's fingerprint is
then part of the narration cache key, but the request alone does not say which voice spoke, so
the save path follows what the adapter reports (SpokenWav.voice, #483): a file spoken all in the
reference voice is saved under the reference key, one spoken all in the stock voice under the
stock key (no fingerprint), and a file mixing the two is saved under a one-off key so this show
can still play it, but not under the reference or stock key. A later show whose reference voice
works again then misses the reference key and gets the cloned voice. A provider that reports no
voice (the mocks) is taken as speaking the voice that was asked for.

Counts of 3+ digits are sent to TTS in words ("128" -> "one hundred twenty-eight",
app/media/spoken_numbers.py, #502); the captions and saved scripts keep the digits.

Files are cached under <data_dir>/media/audio/ by a hash of the full request, so a repeat makes
no provider call (a cache hit needs a non-empty file). In mock mode they go under
<data_dir>/media/mock/audio/ instead, so mock audio is never reused live (app/media/files.py).
A failed item gives no asset at all (no silent stand-in file) and nothing is
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
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Self

from app.config import Settings, get_settings
from app.media import files
from app.media.spoken_numbers import speech_text
from app.models.matchup import Matchup
from app.models.media import Asset
from app.models.narration import Script
from app.models.simulation import SimulationResult
from app.models.stats import StatSheet
from app.providers.base import TTS, MusicGen, ProviderName
from app.providers.live.tts import SpokenVoice, SpokenWav, reference_fingerprint, speech_options
from app.providers.registry import ProviderMode, get_provider, provider_mode
from app.safety.media_names import safe_media_name

logger = logging.getLogger(__name__)

# Bump when the way files are made changes, so old caches are not reused. a2: every narration
# file is saved with its line times (#576), so the voice can follow the fight.
AUDIO_VERSION = "a2"
ITEM_TIMEOUT_S = 96.0  # per file (120 s audio budget x 0.8, D-68); the stage passes its own share
LINE_PAUSE_S = 0.4  # silence between two spoken lines
# At most this many TTS calls run at once, so a long script's voice takes about ceil(lines / 3)
# line latencies instead of one per line and fits the audio budget (#548). The three scripts of
# a show share one limit, so a stock-voice show never fills the speech service's queue (#568).
SPEAK_CONCURRENCY = 3
MUSIC_SECONDS = 30.0
MUSIC_STYLE = "upbeat retro sports-broadcast theme, brass and synth"
MUSIC_TAIL = "instrumental, no vocals"
HASH_PREFIX = 16  # hex characters of the request hash used in file names

ScriptKind = Literal["intro", "play_by_play", "outro"]
AudioKind = Literal["narration_audio", "music"]
PROVIDER_FOR: dict[AudioKind, ProviderName] = {"narration_audio": "tts", "music": "music"}
FIRST_SCRIPT: ScriptKind = "intro"  # recorded before the others: the show starts on it (#592)
# Told about each narration file as soon as it is made, e.g. to put it on the battle's record.
OnReady = Callable[[Asset], Awaitable[None]]


class AudioError(ValueError):
    """The provider's audio could not be read or joined."""


@dataclass(frozen=True)
class AudioRequest:
    """Everything that decides one audio file: where it is cached and the full request."""

    kind: AudioKind
    request: dict[str, object]
    """The full request (text or prompt, voice, and every fixed parameter); its hash names it."""
    script_kind: ScriptKind | None = None
    mode: ProviderMode = "live"

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

    # File name under the media folder in live mode, e.g. audio/narration-intro-0123abcd.wav.
    @property
    def path(self) -> Path:
        return Path("audio") / f"{self.asset_id}.wav"

    # Where the file really is under the media folder: mock audio lives in mock/.
    @property
    def cached_path(self) -> Path:
        return files.cache_path(self.path, self.mode)

    # The asset for the saved file (only ever built for a file that exists), with where each
    # line sits in it when that is known (#576).
    def asset(self, line_times: "LineTimes | None" = None) -> Asset:
        return Asset(
            asset_id=self.asset_id,
            kind=self.kind,
            url=f"/media/{self.cached_path.as_posix()}",
            prompt_hash=self.prompt_hash,
            script_kind=self.script_kind,
            line_times_s=line_times,
        )


# --- voice consent ------------------------------------------------------------------------------


# True when ANNOUNCER_VOICE_CONSENT_FILE names a file that exists.
def consent_on_file(settings: Settings) -> bool:
    path = settings.announcer_voice_consent_file
    return path is not None and path.is_file()


# The voice id to speak with: always the stock voice id. A cloned voice without consent is
# refused; with consent and a usable reference clip, the TTS adapter adds the clip to each request
# and this stock voice is the fallback.
def announcer_voice(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if settings.announcer_voice_source.strip().lower() == "cloned":
        if not consent_on_file(settings):
            logger.warning("cloned announcer voice refused: no consent file; using stock voice")
        elif reference_fingerprint(settings) is None:
            logger.warning("announcer reference clip not usable; using stock voice")
        else:
            logger.info("announcer reference voice in use; stock voice is the fallback")
    return settings.announcer_voice_id


# --- requests -----------------------------------------------------------------------------------


# The text spoken for one script: its non-blank lines, in order, exactly as captioned.
def spoken_lines(script: Script) -> list[str]:
    return [line.text.strip() for line in script.lines if line.text.strip()]


# The same lines as sent to the speech service: counts of 3+ digits in words, so "128 geese" is
# not misread as "28 geese" (#502). Only the voice hears this; captions keep the digits.
def speech_lines(script: Script) -> list[str]:
    return [speech_text(text) for text in spoken_lines(script)]


# The request for one script's file. options holds the fixed speech fields the TTS adapter sends
# (model, and speed when not 1), so changing either makes a new file instead of reusing one.
# voice_ref is the reference clip's fingerprint when one is in use; it is left out otherwise, so
# stock-voice requests (and their cached files) stay exactly as before.
def narration_request(
    script: Script,
    voice_id: str,
    options: Mapping[str, object] | None = None,
    voice_ref: str | None = None,
) -> AudioRequest:
    request: dict[str, object] = {
        "version": AUDIO_VERSION,
        "script_kind": script.kind,
        "lines": speech_lines(script),  # what is spoken, so a "128" spoken as digits is not reused
        "voice_id": voice_id,
        "pause_s": LINE_PAUSE_S,
        **(options or {}),
    }
    if voice_ref is not None:
        request["voice_ref"] = voice_ref
    return AudioRequest(kind="narration_audio", script_kind=script.kind, request=request)


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
# The intro is recorded first, then the play-by-play and outro together, so the show can start on
# the intro's voice while the rest is recorded (#592). Each file is handed to `on_ready` as soon
# as it is made (or found in the cache). Every file must be done within timeout_s of the start,
# as when all three started at once. Never raises.
async def make_audio(
    scripts: Sequence[Script],
    *,
    provider: TTS | None = None,
    media_dir: Path | None = None,
    timeout_s: float = ITEM_TIMEOUT_S,
    on_ready: OnReady | None = None,
) -> list[Asset]:
    try:
        voice_id = announcer_voice()
        options = speech_options(get_settings())
        voice_ref = reference_fingerprint(get_settings())
    except Exception as error:
        logger.warning("announcer voice unavailable (%s)", type(error).__name__)
        return []
    if provider is None:
        try:
            provider = get_provider("tts")
        except Exception as error:  # live settings missing: cached files can still be used
            logger.warning("tts provider unavailable (%s)", type(error).__name__)
    limit = asyncio.Semaphore(SPEAK_CONCURRENCY)  # one for the whole show (#568)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s

    # One script's file within the time left, handed over as soon as it is there.
    async def record(script: Script) -> Asset | None:
        asset = await _bounded(
            narration_request(script, voice_id, options, voice_ref),
            functools.partial(_speak, script=script, voice_id=voice_id, limit=limit),
            provider,
            media_dir,
            max(0.0, deadline - loop.time()),
            stock=None if voice_ref is None else narration_request(script, voice_id, options),
        )
        if asset is not None and on_ready is not None:
            await _hand_over(on_ready, asset)
        return asset

    spoken = [script for script in scripts if spoken_lines(script)]
    first = [i for i, script in enumerate(spoken) if script.kind == FIRST_SCRIPT]
    rest = [i for i in range(len(spoken)) if i not in first]
    made: list[Asset | None] = [None] * len(spoken)
    for i in first:
        made[i] = await record(spoken[i])
    # In broadcast order the play-by-play's lines queue for the shared limit before the outro's.
    later = await asyncio.gather(*(record(spoken[i]) for i in rest))
    for i, asset in zip(rest, later, strict=True):
        made[i] = asset
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


# Where each line of a script sits in its joined file: (start, end) in seconds, in the script's
# line order, None for a blank line (not spoken). The page plays each line with its event (#576).
LineTimes = list[tuple[float, float] | None]


class TimedWav(bytes):
    """A script's joined voice file, with each line's place in it."""

    line_times: LineTimes

    def __new__(cls, data: bytes, line_times: LineTimes) -> Self:
        wav = super().__new__(cls, data)
        wav.line_times = line_times
        return wav


class TimedSpokenWav(SpokenWav):
    """The same, for a file whose provider says which voice spoke it (cloned, stock or mixed)."""

    line_times: LineTimes

    def __new__(cls, data: bytes, voice: SpokenVoice, line_times: LineTimes) -> Self:
        wav = super().__new__(cls, data, voice)
        wav.line_times = line_times
        return wav


# The line times of a joined file: each clip's length, with join_wavs' pause between them.
def line_times(script: Script, clips: Sequence[bytes], pause_s: float) -> LineTimes:
    read = [_read_wav(clip) for clip in clips]
    lengths = [len(frames) / (ch * width) / rate for (ch, width, rate), frames in read]
    rate = read[0][0][2] if read else 1
    pause = int(rate * pause_s) / rate  # join_wavs pauses for a whole number of frames
    times: LineTimes = []
    start, spoken = 0.0, iter(lengths)
    for line in script.lines:
        if not line.text.strip():
            times.append(None)
            continue
        length = next(spoken)
        times.append((round(start, 3), round(start + length, 3)))
        start += length + pause
    return times


# A narration file's line times are kept next to it, e.g. narration-intro-0123abcd.lines.json.
def _times_file(file: Path) -> Path:
    return file.with_suffix(".lines.json")


# The line times saved next to a cached file, or None for a file made without them.
def _saved_times(file: Path) -> LineTimes | None:
    try:
        raw = json.loads(_times_file(file).read_text("utf-8"))
        return [None if t is None else (float(t[0]), float(t[1])) for t in raw]
    except (OSError, ValueError, TypeError, IndexError):
        return None


# Speak the lines a few at a time (SPEAK_CONCURRENCY, #548), sharing the show's `limit` when given
# one (#568), keep the clips in the script's line order, then join them with a short pause between
# lines. If the provider says which voice spoke (live TTS), the joined file says it too; lines in
# two voices are tagged "mixed" so they are not cached under the reference or stock key.
async def _speak(
    tts: TTS, script: Script, voice_id: str, limit: asyncio.Semaphore | None = None
) -> bytes:
    slots = asyncio.Semaphore(SPEAK_CONCURRENCY) if limit is None else limit

    # One line, waiting for a free slot first.
    async def one(text: str) -> bytes:
        async with slots:
            return await tts.speak(text, voice_id)

    # A TaskGroup cancels the script's other lines as soon as one fails (#568). Re-raise that
    # line's own error, so the audio log still names it rather than ExceptionGroup.
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(one(text)) for text in speech_lines(script)]
    except ExceptionGroup as errors:
        raise errors.exceptions[0] from None
    clips = [task.result() for task in tasks]  # in the script's line order
    voices = {getattr(clip, "voice", None) for clip in clips}
    joined = await asyncio.to_thread(join_wavs, clips, LINE_PAUSE_S)
    times = line_times(script, clips, LINE_PAUSE_S)
    if voices == {None}:
        return TimedWav(joined, times)
    if len(voices) == 1:
        [voice] = voices
        return TimedSpokenWav(joined, voice, times)
    return TimedSpokenWav(joined, "mixed", times)


# The cached file if there is one (in this provider mode's folder), else make it within the time
# limit and save it. Anything going wrong gives None and caches nothing. `stock` is the request
# without the reference clip: a file the provider says was spoken in the stock voice is saved
# under it instead, never under the reference key.
async def _bounded[P](
    request: AudioRequest,
    make: Callable[[P], Awaitable[bytes]],
    provider: P | None,
    media_dir: Path | None,
    timeout_s: float,
    stock: AudioRequest | None = None,
) -> Asset | None:
    try:
        mode = provider_mode(PROVIDER_FOR[request.kind])
        request = replace(request, mode=mode)
        root = media_dir or files.media_root()
        if files.is_cached(root / request.cached_path):
            return request.asset(_saved_times(root / request.cached_path))
        if provider is None:
            raise RuntimeError("no provider")
        data = await asyncio.wait_for(make(provider), timeout_s)
        voice = getattr(data, "voice", None)
        if stock is not None and voice == "stock":
            request = replace(stock, mode=mode)
        elif voice == "mixed":
            # Serve this show, but do not reuse the file as cloned or as stock.
            request = replace(request, request={**request.request, "spoken": "mixed"})
        times = getattr(data, "line_times", None)
        if times is not None:  # saved first, so a cached voice file always has its line times
            text = json.dumps(times).encode("utf-8")
            await asyncio.to_thread(files.save, _times_file(root / request.cached_path), text)
        await asyncio.to_thread(files.save, root / request.cached_path, data)
    except Exception as error:
        logger.warning("audio %s not made (%s)", request.asset_id, type(error).__name__)
        return None
    return request.asset(times)


# Tell on_ready about a made file; its trouble is logged, never raised: the file is still returned.
async def _hand_over(on_ready: OnReady, asset: Asset) -> None:
    try:
        await on_ready(asset)
    except Exception as error:
        logger.warning("audio %s not handed over early (%s)", asset.asset_id, type(error).__name__)


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
