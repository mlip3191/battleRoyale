"""#592: the intro's voice is recorded first and put on the record at once, so the show can start
while the play-by-play and outro are still being recorded."""

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from app.config import use_settings
from app.media import audio
from app.models.matchup import Matchup
from app.models.media import Asset
from app.models.narration import Script, ScriptLine
from app.pipeline.orchestrator import run_battle
from app.pipeline.store import BattleStore
from app.providers.mock.audio import MockTTS
from tests.conftest import mock_settings

KINDS = ["intro", "play_by_play", "outro"]
WAIT_S = 5.0  # longest any wait in this file may take


# A whole show whose lines name their script, so a log can say which script each call was for.
def broadcast() -> list[Script]:
    return [
        Script(
            kind=kind,
            lines=[ScriptLine(speaker="announcer", text=f"{kind} line {n}.") for n in (1, 2, 3)],
        )
        for kind in KINDS
    ]


class LoggedTTS(MockTTS):
    """The mock TTS, taking `delay_s` per line (or hanging), logging each line's start and end."""

    def __init__(self, log: list[tuple[str, str]], delay_s: float = 0.02, fail: str = "") -> None:
        self.log, self.delay_s, self.fail = log, delay_s, fail

    async def speak(self, text: str, voice_id: str) -> bytes:
        kind = text.split(" line ")[0]
        if kind == self.fail:
            raise RuntimeError("tts down")
        self.log.append(("start", kind))
        await asyncio.sleep(self.delay_s)
        self.log.append(("end", kind))
        return await super().speak(text, voice_id)


@pytest.fixture(autouse=True)
def _stock_voice(tmp_path: Path) -> None:
    use_settings(mock_settings(data_dir=tmp_path, sim_runs=20, announcer_voice_id="stock"))


async def test_the_intro_is_recorded_first_and_handed_over_before_the_rest_starts(
    tmp_path: Path,
) -> None:
    log: list[tuple[str, str]] = []

    async def ready(asset: Asset) -> None:
        log.append(("ready", str(asset.script_kind)))

    tts = LoggedTTS(log)
    assets = await audio.make_audio(broadcast(), provider=tts, media_dir=tmp_path, on_ready=ready)
    assert [a.script_kind for a in assets] == KINDS  # still in the scripts' order
    first_other = next(i for i, (_, kind) in enumerate(log) if kind != "intro")
    assert log[first_other - 1] == ("ready", "intro")  # handed over before any other line
    # The play-by-play is next in line for the voice: the fight needs it before the verdict.
    starts = [kind for event, kind in log if event == "start"]
    assert starts == ["intro"] * 3 + ["play_by_play"] * 3 + ["outro"] * 3


async def test_every_file_is_handed_over_once_cache_hits_too_and_a_failing_hand_over_is_harmless(
    tmp_path: Path,
) -> None:
    for _ in range(2):  # made, then from the cache
        handed: list[Asset] = []

        async def ready(asset: Asset, into: list[Asset] = handed) -> None:
            into.append(asset)

        made = await audio.make_audio(
            broadcast(), provider=LoggedTTS([]), media_dir=tmp_path, on_ready=ready
        )
        assert [a.asset_id for a in handed] == [a.asset_id for a in made]
        assert all(a.line_times_s is not None for a in handed)  # the sidecar comes along (#576)

    async def broken(asset: Asset) -> None:
        raise RuntimeError("store down")

    again = await audio.make_audio(broadcast(), media_dir=tmp_path, on_ready=broken)
    assert [a.script_kind for a in again] == KINDS


async def test_a_failing_intro_still_voices_the_play_by_play_and_outro(tmp_path: Path) -> None:
    handed: list[str | None] = []

    async def ready(asset: Asset) -> None:
        handed.append(asset.script_kind)

    tts = LoggedTTS([], fail="intro")
    assets = await audio.make_audio(broadcast(), provider=tts, media_dir=tmp_path, on_ready=ready)
    assert [a.script_kind for a in assets] == handed == ["play_by_play", "outro"]


async def test_the_rest_shares_the_intros_time_limit_so_a_hung_voice_still_ends_in_time(
    tmp_path: Path,
) -> None:
    limit, start = 0.2, time.perf_counter()
    hung = LoggedTTS([], delay_s=60.0)
    assert (
        await audio.make_audio(broadcast(), provider=hung, media_dir=tmp_path, timeout_s=limit)
        == []
    )
    assert time.perf_counter() - start < limit * 2  # not one full limit per file


async def test_the_intros_voice_is_on_the_record_while_the_rest_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = asyncio.Event()  # every script but the intro waits for it
    real_speak = audio._speak

    async def speak(tts: Any, script: Script, voice_id: str, **kwargs: Any) -> bytes:
        if script.kind != "intro":
            await gate.wait()
        return await real_speak(tts, script, voice_id, **kwargs)

    monkeypatch.setattr(audio, "_speak", speak)
    fighters = [{"entity": n, "raw": n} for n in ("grizzly bear", "gray wolf")]
    matchup = Matchup.model_validate(
        {"fighters": fighters, "raw_text": "grizzly bear vs gray wolf"}
    )
    store = BattleStore()
    battle_id = (await store.create(matchup)).battle_id
    task = asyncio.create_task(run_battle(battle_id, store))

    def voices(record: Any) -> list[str]:
        return [str(a.script_kind) for a in record.assets if a.kind == "narration_audio"]

    try:
        deadline = time.monotonic() + WAIT_S
        while "intro" not in voices(early := await store.get(battle_id)):
            assert time.monotonic() < deadline, "the intro's voice never reached the record"
            await asyncio.sleep(0.01)
        assert early.status == "running" and early.result is not None
        audio_stage = next(s for s in early.stages if s.stage == "audio")
        assert (audio_stage.status, voices(early)) == ("running", ["intro"])
    finally:
        gate.set()
        await asyncio.wait_for(task, WAIT_S)
    record = await store.get(battle_id)
    assert record is not None and record.status == "done"
    assert next(s for s in record.stages if s.stage == "audio").status == "done"
    assert sorted(voices(record)) == sorted(KINDS)  # each file once: no duplicates at the end
