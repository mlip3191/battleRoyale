"""A07 (first slice, #45): announcer narration and music through the mock TTS and MusicGen."""

import asyncio
import io
import math
import time
import wave
from pathlib import Path
from typing import Any

import pytest

from app.config import use_settings
from app.media import audio
from app.models.battle import BattleRecord
from app.models.matchup import Matchup
from app.models.media import Asset
from app.models.narration import Script, ScriptLine
from app.models.stats import StatSheet
from app.pipeline import stages
from app.pipeline.orchestrator import FALLBACK_DETAILS, FALLBACK_WITH_VALUE, run_battle
from app.pipeline.store import BattleStore
from app.providers.live.tts import SpokenVoice, SpokenWav
from app.providers.mock.audio import MOCK_SAMPLE_RATE, MockMusicGen, MockTTS
from app.research.seed_fighters import find_seed_sheet
from tests.conftest import mock_settings

STOCK_VOICE = "stock-announcer"
KINDS = ["intro", "play_by_play", "outro"]


class SpyTTS(MockTTS):
    """The mock TTS, keeping every (text, voice_id) it was asked to speak."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_on = fail_on  # text that makes speak() raise; "*" fails every line

    async def speak(self, text: str, voice_id: str) -> bytes:
        self.calls.append((text, voice_id))
        if self.fail_on in ("*", text):
            raise RuntimeError("tts down")
        return await super().speak(text, voice_id)


class SpyMusic(MockMusicGen):
    """The mock music generator, keeping every (prompt, seconds) it was asked for."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, float]] = []
        self.fail = fail

    async def compose(self, prompt: str, seconds: float) -> bytes:
        self.calls.append((prompt, seconds))
        if self.fail:
            raise RuntimeError("music down")
        return await super().compose(prompt, seconds)


def script(kind: str, *texts: str) -> Script:
    lines = [ScriptLine(speaker="announcer", text=t) for t in texts]
    return Script.model_validate({"kind": kind, "lines": lines})


def broadcast() -> list[Script]:
    return [
        script("intro", "Welcome to the arena!", "What a night."),
        script("play_by_play", "Here they come!"),
        script("outro", "That's the ballgame.", "Goodnight.", "Drive home safe."),
    ]


def sheet(name: str) -> StatSheet:
    found = find_seed_sheet(name)
    assert found is not None
    return found


def matchup(first: str = "grizzly bear", second: str = "gray wolf") -> Matchup:
    fighters = [{"entity": first, "raw": first}, {"entity": second, "raw": second}]
    return Matchup.model_validate({"fighters": fighters, "raw_text": f"{first} vs {second}"})


def sheets() -> list[StatSheet]:
    return [sheet("grizzly bear"), sheet("gray wolf")]


def wav_seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


@pytest.fixture(autouse=True)
def _stock_voice(tmp_path: Path) -> None:
    use_settings(mock_settings(data_dir=tmp_path, announcer_voice_id=STOCK_VOICE))


# --- what gets made -----------------------------------------------------------------------------


async def test_one_tagged_narration_file_per_script_in_broadcast_order(tmp_path: Path) -> None:
    tts = SpyTTS()
    assets = await audio.make_audio(broadcast(), provider=tts, media_dir=tmp_path)
    assert [(a.kind, a.script_kind) for a in assets] == [("narration_audio", k) for k in KINDS]
    assert not any(a.fallback for a in assets)
    for asset in assets:
        assert asset.url.startswith("/media/mock/audio/narration-") and asset.url.endswith(".wav")
        assert asset.asset_id == f"narration-{asset.script_kind}-{asset.prompt_hash[:16]}"
        assert (tmp_path / asset.url.removeprefix("/media/")).is_file()
    assert len(tts.calls) == 6 and {voice for _, voice in tts.calls} == {STOCK_VOICE}


async def test_the_lines_are_joined_with_a_short_pause(tmp_path: Path) -> None:
    outro = broadcast()[2]  # three lines, one second each from the mock
    [asset] = await audio.make_audio([outro], provider=SpyTTS(), media_dir=tmp_path)
    data = (tmp_path / asset.url.removeprefix("/media/")).read_bytes()
    pause = int(MOCK_SAMPLE_RATE * audio.LINE_PAUSE_S) / MOCK_SAMPLE_RATE
    assert wav_seconds(data) == pytest.approx(3 * 1.0 + 2 * pause)


def tone_wav(level: int, frames: int) -> bytes:
    """A mono 16-bit mock-rate WAV whose every sample is `level`, so each clip is recognisable."""
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(MOCK_SAMPLE_RATE)
        wav.writeframes(level.to_bytes(2, "little", signed=True) * frames)
    return out.getvalue()


def wav_frames(data: bytes) -> bytes:
    with wave.open(io.BytesIO(data), "rb") as wav:
        return wav.readframes(wav.getnframes())


class DelayedTTS(MockTTS):
    """A TTS where each line takes `delay(i)` seconds; it counts how many calls overlap."""

    def __init__(self, texts: list[str], delay: Any, clip: Any = None) -> None:
        self.texts = texts
        self.delay = delay  # index of the line -> seconds
        self.clip = clip  # index of the line -> WAV bytes (the mock's one-second clip if None)
        self.in_flight = 0
        self.most_in_flight = 0

    async def speak(self, text: str, voice_id: str) -> bytes:
        i = self.texts.index(text)
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay(i))
        finally:
            self.in_flight -= 1
        if self.clip is None:
            return await super().speak(text, voice_id)
        return self.clip(i)


async def test_the_lines_are_spoken_a_few_at_a_time_not_one_after_another() -> None:
    # #548: six lines at 0.4 s each took 2.4 s one by one; three at a time takes about 0.8 s.
    assert audio.SPEAK_CONCURRENCY == 3
    texts = [f"Line number {n}." for n in range(1, 7)]
    delay = 0.4
    tts = DelayedTTS(texts, lambda _: delay)
    start = time.perf_counter()
    joined = await audio._speak(tts, script("outro", *texts), STOCK_VOICE)
    elapsed = time.perf_counter() - start
    rounds = math.ceil(len(texts) / audio.SPEAK_CONCURRENCY)  # 2
    assert elapsed >= rounds * delay * 0.9
    assert elapsed < (rounds + 1.5) * delay  # one by one would be 6 delays
    assert tts.most_in_flight == audio.SPEAK_CONCURRENCY
    assert tts.in_flight == 0 and wav_seconds(joined) > 0


async def test_the_joined_file_keeps_line_order_when_later_lines_finish_first() -> None:
    texts = ["First!", "Second!", "Third!", "Fourth!", "Fifth!"]
    clips = [tone_wav(level=100 * (i + 1), frames=50 * (i + 1)) for i in range(len(texts))]
    # Earlier lines take longer, so the clips finish in reverse order.
    tts = DelayedTTS(texts, lambda i: 0.05 * (len(texts) - i), lambda i: clips[i])
    joined = await audio._speak(tts, script("intro", *texts), STOCK_VOICE)
    silence = b"\x00\x00" * int(MOCK_SAMPLE_RATE * audio.LINE_PAUSE_S)
    assert wav_frames(joined) == silence.join(wav_frames(clip) for clip in clips)


async def test_the_joined_file_is_tagged_with_the_voice_that_spoke_it() -> None:
    texts = ["One.", "Two.", "Three.", "Four."]
    wav = tone_wav(level=1, frames=10)

    async def joined(voices: list[SpokenVoice | None]) -> bytes:
        def clip(i: int) -> bytes:
            voice = voices[i]
            return wav if voice is None else SpokenWav(wav, voice)

        tts = DelayedTTS(texts, lambda i: 0.02 * (len(texts) - i), clip)
        return await audio._speak(tts, script("intro", *texts), STOCK_VOICE)

    cloned = await joined(["cloned"] * 4)
    assert isinstance(cloned, SpokenWav) and cloned.voice == "cloned"
    stock = await joined(["stock"] * 4)
    assert isinstance(stock, SpokenWav) and stock.voice == "stock"
    mixed = await joined(["cloned", "cloned", "stock", "stock"])
    assert isinstance(mixed, SpokenWav) and mixed.voice == "mixed"
    plain = await joined([None] * 4)
    assert not isinstance(plain, SpokenWav)


async def test_music_is_one_untagged_music_file(tmp_path: Path) -> None:
    music = SpyMusic()
    track = await audio.make_music(matchup(), None, sheets(), provider=music, media_dir=tmp_path)
    assert track is not None and not track.fallback
    assert (track.kind, track.script_kind) == ("music", None)
    assert track.url.startswith("/media/mock/audio/music-") and track.url.endswith(".wav")
    assert (tmp_path / track.url.removeprefix("/media/")).is_file()
    assert music.calls == [(audio.music_prompt(sheets()), audio.MUSIC_SECONDS)]


async def test_only_narration_carries_a_script_kind_across_all_media(tmp_path: Path) -> None:
    use_settings(mock_settings(data_dir=tmp_path, announcer_voice_id=STOCK_VOICE))
    found = await stages.research(matchup())
    result = await stages.simulate(matchup(), found)
    voice = await stages.audio(broadcast())
    music = await stages.music(matchup(), found, result)
    pictures = await stages.images(matchup(), found)
    assert voice.value is not None and music.value is not None
    every: list[Asset] = voice.value + music.value + pictures.value
    for asset in every:
        if asset.kind == "narration_audio":
            assert asset.script_kind in KINDS
        else:
            assert asset.script_kind is None, asset.kind


# --- caching ------------------------------------------------------------------------------------


async def test_a_repeat_makes_no_provider_calls(tmp_path: Path) -> None:
    tts, music = SpyTTS(), SpyMusic()
    first = await audio.make_audio(broadcast(), provider=tts, media_dir=tmp_path)
    track = await audio.make_music(matchup(), None, sheets(), provider=music, media_dir=tmp_path)
    tts.calls.clear()
    music.calls.clear()
    again = await audio.make_audio(broadcast(), provider=tts, media_dir=tmp_path)
    track_again = await audio.make_music(
        matchup(), None, sheets(), provider=music, media_dir=tmp_path
    )
    assert again == first and track_again == track
    assert tts.calls == [] and music.calls == []


async def test_new_words_a_new_voice_or_a_new_prompt_miss_the_cache(tmp_path: Path) -> None:
    tts = SpyTTS()
    [old] = await audio.make_audio([script("intro", "Hello!")], provider=tts, media_dir=tmp_path)
    [reworded] = await audio.make_audio(
        [script("intro", "Hello there!")], provider=tts, media_dir=tmp_path
    )
    use_settings(mock_settings(data_dir=tmp_path, announcer_voice_id="another-voice"))
    [revoiced] = await audio.make_audio(
        [script("intro", "Hello!")], provider=tts, media_dir=tmp_path
    )
    assert len(tts.calls) == 3
    assert len({old.prompt_hash, reworded.prompt_hash, revoiced.prompt_hash}) == 3
    assert tts.calls[-1] == ("Hello!", "another-voice")

    music = SpyMusic()
    bears = await audio.make_music(matchup(), None, sheets(), provider=music, media_dir=tmp_path)
    ducks = [sheet("duck"), sheet("gray wolf")]
    other = await audio.make_music(matchup(), None, ducks, provider=music, media_dir=tmp_path)
    assert len(music.calls) == 2
    assert bears is not None and other is not None and bears.prompt_hash != other.prompt_hash


async def test_a_three_digit_count_is_spoken_in_words_but_captioned_in_digits(
    tmp_path: Path,
) -> None:
    tts = SpyTTS()
    show = script("intro", "A tiger vs 128 geese!", "1,000 fans and 1000 more.")
    [asset] = await audio.make_audio([show], provider=tts, media_dir=tmp_path)
    assert [text for text, _ in tts.calls] == [
        "A tiger vs one hundred twenty-eight geese!",
        "one thousand fans and one thousand more.",
    ]
    assert not any("28" in text for text, _ in tts.calls)
    # The caption, the saved script and the display lines keep the digits.
    assert [line.text for line in show.lines] == [
        "A tiger vs 128 geese!",
        "1,000 fans and 1000 more.",
    ]
    assert audio.spoken_lines(show) == ["A tiger vs 128 geese!", "1,000 fans and 1000 more."]
    # The cache key is the spoken form, so a file once spoken from the digits is not reused.
    request = audio.narration_request(show, STOCK_VOICE)
    assert request.request["lines"] == [text for text, _ in tts.calls]
    digits = {**request.request, "lines": audio.spoken_lines(show)}
    old = audio.AudioRequest(kind="narration_audio", script_kind="intro", request=digits)
    assert old.prompt_hash != request.prompt_hash
    assert asset.asset_id.startswith("narration-intro-")


async def test_a_line_with_no_big_count_keeps_its_cache_key(tmp_path: Path) -> None:
    show = script("intro", "Welcome to the arena!", "Only 42 geese tonight.")
    request = audio.narration_request(show, STOCK_VOICE)
    assert request.request["lines"] == audio.spoken_lines(show)


# --- failures -----------------------------------------------------------------------------------


async def test_a_failing_tts_gives_no_files_and_caches_nothing(tmp_path: Path) -> None:
    assets = await audio.make_audio(broadcast(), provider=SpyTTS("*"), media_dir=tmp_path)
    assert assets == []
    assert not list(tmp_path.rglob("*.wav")) and not list(tmp_path.rglob("*.tmp"))
    redo = await audio.make_audio(broadcast(), provider=SpyTTS(), media_dir=tmp_path)
    assert len(redo) == 3  # the failure was not cached


async def test_one_failing_script_is_left_out_and_the_others_are_kept(tmp_path: Path) -> None:
    tts = SpyTTS(fail_on="Here they come!")
    assets = await audio.make_audio(broadcast(), provider=tts, media_dir=tmp_path)
    assert [a.script_kind for a in assets] == ["intro", "outro"]
    assert not any(a.fallback for a in assets)  # saved files are real, never marked fallback


async def test_a_slow_tts_or_music_times_out_into_nothing(tmp_path: Path) -> None:
    class SlowTTS(MockTTS):
        async def speak(self, text: str, voice_id: str) -> bytes:
            await asyncio.sleep(5)
            return b""

    class SlowMusic(MockMusicGen):
        async def compose(self, prompt: str, seconds: float) -> bytes:
            await asyncio.sleep(5)
            return b""

    voice = await audio.make_audio(
        broadcast(), provider=SlowTTS(), media_dir=tmp_path, timeout_s=0.05
    )
    track = await audio.make_music(
        matchup(), None, sheets(), provider=SlowMusic(), media_dir=tmp_path, timeout_s=0.05
    )
    assert voice == [] and track is None


async def test_audio_that_is_not_a_wav_file_gives_nothing(tmp_path: Path) -> None:
    class Garbled(MockTTS):
        async def speak(self, text: str, voice_id: str) -> bytes:
            return b"not audio"

    class GarbledMusic(MockMusicGen):
        async def compose(self, prompt: str, seconds: float) -> bytes:
            return b"not audio"

    assert await audio.make_audio(broadcast(), provider=Garbled(), media_dir=tmp_path) == []
    track = await audio.make_music(
        matchup(), None, sheets(), provider=GarbledMusic(), media_dir=tmp_path
    )
    assert track is None and not list(tmp_path.rglob("*.wav"))


async def test_make_audio_and_music_never_raise_when_live_settings_are_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*_: Any, **__: Any) -> Any:
        raise RuntimeError("Live 'tts' provider needs these .env settings: TTS_URL.")

    monkeypatch.setattr(audio, "get_provider", missing)
    assert await audio.make_audio(broadcast(), media_dir=tmp_path) == []
    assert await audio.make_music(matchup(), None, sheets(), media_dir=tmp_path) is None


async def test_the_audio_stage_reports_fallback_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audio, "get_provider", lambda *_, **__: SpyTTS("*"))
    none = await stages.audio(broadcast())
    assert (none.value, none.fallback, none.stub) == (None, True, False)
    monkeypatch.setattr(audio, "get_provider", lambda *_, **__: SpyTTS("Here they come!"))
    some = await stages.audio(broadcast())
    assert some.fallback and not some.stub and some.value is not None
    assert [a.script_kind for a in some.value] == ["intro", "outro"]


async def test_the_music_stage_reports_fallback_with_no_track(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audio, "get_provider", lambda *_, **__: SpyMusic(fail=True))
    found = await stages.research(matchup())
    result = await stages.simulate(matchup(), found)
    out = await stages.music(matchup(), found, result)
    assert (out.value, out.fallback, out.stub) == (None, True, False)


async def run_to_the_end(tmp_path: Path) -> BattleRecord:
    use_settings(mock_settings(sim_runs=20, data_dir=tmp_path, announcer_voice_id=STOCK_VOICE))
    store = BattleStore()
    created = await store.create(matchup())
    await asyncio.wait_for(run_battle(created.battle_id, store), 20.0)
    record = await store.get(created.battle_id)
    assert isinstance(record, BattleRecord)
    return record


def stage(record: BattleRecord, name: str) -> tuple[str, str | None]:
    found = next(s for s in record.stages if s.stage == name)
    return found.status, found.detail


async def test_the_battle_completes_when_the_tts_provider_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tts = SpyTTS("*")
    real = audio.get_provider
    monkeypatch.setattr(audio, "get_provider", lambda n, *a: tts if n == "tts" else real(n, *a))
    record = await run_to_the_end(tmp_path)
    assert record.status == "done" and record.result is not None
    assert stage(record, "audio") == ("fallback", FALLBACK_DETAILS["audio"])
    assert stage(record, "music") == ("done", None)
    assert not any(a.kind == "narration_audio" for a in record.assets)
    assert tts.calls  # it really tried


async def test_a_partial_narration_keeps_the_saved_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Only the play-by-play's narration fails; the real scripts' text isn't known up front.
    real_speak = audio._speak

    async def speak(tts: Any, script: Script, voice_id: str) -> bytes:
        if script.kind == "play_by_play":
            raise RuntimeError("tts down")
        return await real_speak(tts, script, voice_id)

    monkeypatch.setattr(audio, "_speak", speak)
    record = await run_to_the_end(tmp_path)
    assert record.status == "done"
    assert stage(record, "audio") == ("fallback", FALLBACK_WITH_VALUE["audio"])
    narration = [a for a in record.assets if a.kind == "narration_audio"]
    assert [a.script_kind for a in narration] == ["intro", "outro"]


async def test_the_battle_completes_when_the_music_provider_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    music = SpyMusic(fail=True)
    real = audio.get_provider
    monkeypatch.setattr(audio, "get_provider", lambda n, *a: music if n == "music" else real(n, *a))
    record = await run_to_the_end(tmp_path)
    assert record.status == "done" and record.result is not None
    assert stage(record, "music") == ("fallback", FALLBACK_DETAILS["music"])
    assert stage(record, "audio") == ("done", None)
    assert not any(a.kind == "music" for a in record.assets)
    assert music.calls  # it really tried


# --- voice consent ------------------------------------------------------------------------------


@pytest.mark.parametrize("consent", [None, "no-such-consent.txt"])
async def test_a_cloned_voice_without_consent_uses_the_stock_voice(
    tmp_path: Path, consent: str | None
) -> None:
    consent_file = None if consent is None else tmp_path / consent
    use_settings(
        mock_settings(
            data_dir=tmp_path,
            announcer_voice_source="cloned",
            announcer_voice_id=STOCK_VOICE,
            announcer_voice_consent_file=consent_file,
        )
    )
    tts = SpyTTS()
    assets = await audio.make_audio(broadcast(), provider=tts, media_dir=tmp_path)
    assert len(assets) == 3
    assert {voice for _, voice in tts.calls} == {STOCK_VOICE}


async def test_a_cloned_voice_with_consent_still_speaks_with_the_stock_voice_for_now(
    tmp_path: Path,
) -> None:
    consent_file = tmp_path / "consent.txt"
    consent_file.write_text("signed", encoding="utf-8")
    settings = mock_settings(
        data_dir=tmp_path,
        announcer_voice_source="cloned",
        announcer_voice_id=STOCK_VOICE,
        announcer_voice_consent_file=consent_file,
    )
    assert audio.consent_on_file(settings)
    assert audio.announcer_voice(settings) == STOCK_VOICE  # the stock id is always the fallback


# --- the music prompt ---------------------------------------------------------------------------


def branded(media_name: str) -> StatSheet:
    return sheet("main battle tank").model_copy(update={"media_name": media_name})


def test_the_music_prompt_names_each_safe_fighter_and_the_broadcast_style() -> None:
    prompt = audio.music_prompt(sheets())
    assert audio.MUSIC_STYLE in prompt and "30 seconds" in prompt
    assert "grizzly bear" in prompt and "gray wolf" in prompt
    mirror = audio.music_prompt([sheet("gray wolf"), sheet("gray wolf")])
    assert mirror.count("gray wolf") == 1


def test_a_branded_media_name_is_left_out_of_the_music_prompt() -> None:
    prompt = audio.music_prompt([branded("tesla truck"), sheet("gray wolf")])
    assert "tesla" not in prompt.lower() and "truck" not in prompt.lower()
    assert "gray wolf" in prompt


def test_with_no_safe_name_the_music_prompt_names_no_fighter() -> None:
    prompt = audio.music_prompt([branded("tesla truck"), branded("Tesla Cybertruck")])
    assert "tesla" not in prompt.lower() and "cybertruck" not in prompt.lower()
    assert prompt == f"{audio.MUSIC_STYLE}, 30 seconds, {audio.MUSIC_TAIL}"


async def test_the_music_prompt_never_uses_the_display_name(tmp_path: Path) -> None:
    truck = sheet("main battle tank").model_copy(
        update={"display_name": "Tesla Cybertruck", "media_name": "electric pickup truck"}
    )
    music = SpyMusic()
    await audio.make_music(matchup(), None, [truck], provider=music, media_dir=tmp_path)
    [(prompt, _)] = music.calls
    assert "electric pickup truck" in prompt and "tesla" not in prompt.lower()
