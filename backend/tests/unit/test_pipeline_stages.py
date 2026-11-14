"""A05 part 2: stage order, parallel groups, time budgets, fallbacks, and the fair fight (#36)."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from app.config import use_settings
from app.models.battle import BattleRecord, StageStatus
from app.models.matchup import Matchup
from app.models.media import Asset
from app.narration import writer
from app.narration.facts import build_facts
from app.narration.templates import fair_fight_line
from app.pipeline import orchestrator, stages
from app.pipeline.orchestrator import FALLBACK_DETAILS, FALLBACK_WITH_VALUE, STUB, run_battle
from app.pipeline.stages import Stubbed
from app.pipeline.store import STAGES, BattleStore
from app.simulation import fair
from tests.conftest import mock_settings

SIM_RUNS = 20  # enough for a verdict; keeps each battle quick
HARD_TIMEOUT = 20.0  # no battle in this file may take longer than this
SMALL_BUDGET = 8.0  # every stage's limit in these tests, unless a test shrinks one further
TINY_BUDGET = 0.05  # for the "ran past its budget" tests
TOO_LONG = 5.0  # how long a slow stand-in sleeps (far past TINY_BUDGET, its patched limit)
PAUSE = 0.1  # how long recorded stages wait, so overlaps are visible
OPTIONAL = ("summary", "challenger", "script", "audio", "music", "images")
MEDIA = {"audio": "audio", "music": "music", "images": "images"}
# Stage name -> the function in stages.py that does its work.
WORK = {"summary": "summary", "challenger": "challenger", "script": "scripts", **MEDIA}
# The mock play-by-play has no canned reply on purpose, so the writer uses its template there
# and the script stage ends "fallback" with the scripts still saved.
MOCK_SCRIPT = ("fallback", FALLBACK_WITH_VALUE["script"])
NO_FAIR_CHECK = "Want a fair fight? We didn't run the fair-fight check tonight."


@pytest.fixture(autouse=True)
def _quick_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    use_settings(mock_settings(sim_runs=SIM_RUNS))
    for stage in stages.STAGE_BUDGETS_S:
        monkeypatch.setitem(stages.STAGE_BUDGETS_S, stage, SMALL_BUDGET)


@pytest.fixture
def store() -> BattleStore:
    return BattleStore()


def matchup(first: str, second: str, refs: tuple[str | None, str | None] = (None, None)) -> Matchup:
    fighters = [
        {"entity": name, "raw": name, "size_reference": ref}
        for name, ref in zip((first, second), refs, strict=True)
    ]
    return Matchup.model_validate({"fighters": fighters, "raw_text": f"{first} vs {second}"})


# Run one battle to the end (or fail the test after HARD_TIMEOUT) and return its record.
async def battle(store: BattleStore, fight: Matchup | None = None) -> BattleRecord:
    record = await store.create(fight or matchup("grizzly bear", "gray wolf"))
    await asyncio.wait_for(run_battle(record.battle_id, store), HARD_TIMEOUT)
    final = await store.get(record.battle_id)
    assert final is not None
    return final


def stage_of(record: BattleRecord, name: str) -> StageStatus:
    return next(stage for stage in record.stages if stage.stage == name)


# How a stage ends in a healthy battle on mocks: "done", except the script (see MOCK_SCRIPT).
def ran_normally(record: BattleRecord, name: str) -> bool:
    stage = stage_of(record, name)
    if name == "script":
        return (stage.status, stage.detail) == MOCK_SCRIPT
    return stage.status == "done"


def replace(
    monkeypatch: pytest.MonkeyPatch, name: str, fake: Callable[..., Awaitable[Any]]
) -> None:
    monkeypatch.setattr(stages, name, fake)


async def sleep_too_long(*_: Any, **__: Any) -> Any:
    await asyncio.sleep(TOO_LONG)


async def boom(*_: Any, **__: Any) -> Any:
    raise RuntimeError("boom")


# Wrap stage functions so each logs ("start", name) and ("end", name) around a short pause.
def record_timeline(monkeypatch: pytest.MonkeyPatch, names: list[str]) -> list[tuple[str, str]]:
    log: list[tuple[str, str]] = []
    for name in names:
        real = getattr(stages, name)

        async def wrapper(*args: Any, _name: str = name, _real: Any = real, **kwargs: Any) -> Any:
            log.append(("start", _name))
            await asyncio.sleep(PAUSE)
            try:
                return await _real(*args, **kwargs)
            finally:
                log.append(("end", _name))

        monkeypatch.setattr(stages, name, wrapper)
    return log


async def test_stages_run_in_order_with_the_parallel_groups(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = ["research", "simulate", "summary", "challenger", "scripts", "audio", "music", "images"]
    log = record_timeline(monkeypatch, names)
    record = await battle(store)
    assert record.status == "done"

    def at(event: str, name: str) -> int:
        return log.index((event, name))

    assert at("end", "research") < at("start", "simulate")
    after_sim = ["summary", "challenger", "images"]
    assert all(at("end", "simulate") < at("start", n) for n in after_sim)
    # These three all start before any of them finishes: they run side by side.
    assert max(at("start", n) for n in after_sim) < min(at("end", n) for n in after_sim)
    # The scripts wait for the summary: the outro needs the fair fight.
    assert at("end", "summary") < at("start", "scripts")
    # Audio and music wait for the scripts, then run side by side.
    assert all(at("end", "scripts") < at("start", n) for n in ("audio", "music"))
    assert max(at("start", n) for n in ("audio", "music")) < min(
        at("end", n) for n in ("audio", "music")
    )
    # Images and the challenger wait for neither the summary nor the scripts.
    assert at("start", "images") < at("end", "scripts")
    assert all(at("start", n) < at("end", "summary") for n in ("images", "challenger"))


async def test_the_verdict_is_on_the_record_before_any_media_starts(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = await store.create(matchup("grizzly bear", "gray wolf"))
    seen: dict[str, bool] = {}
    for stage, name in MEDIA.items():
        real = getattr(stages, name)

        async def check(*args: Any, _stage: str = stage, _real: Any = real, **kwargs: Any) -> Any:
            record = await store.get(created.battle_id)
            assert record is not None
            seen[_stage] = (
                record.result is not None and stage_of(record, "simulate").status == "done"
            )
            return await _real(*args, **kwargs)

        replace(monkeypatch, name, check)
    await asyncio.wait_for(run_battle(created.battle_id, store), HARD_TIMEOUT)
    assert seen == {"audio": True, "music": True, "images": True}


@pytest.mark.parametrize("stage", OPTIONAL)
async def test_a_stage_past_its_budget_falls_back_and_the_battle_is_done(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    monkeypatch.setitem(stages.STAGE_BUDGETS_S, stage, TINY_BUDGET)
    replace(monkeypatch, WORK[stage], sleep_too_long)
    loop = asyncio.get_running_loop()
    began = loop.time()
    record = await battle(store)
    assert loop.time() - began < TOO_LONG  # the slow stand-in was cut off, not waited for
    assert record.status == "done"
    assert (stage_of(record, stage).status, stage_of(record, stage).detail) == (
        "fallback",
        FALLBACK_DETAILS[stage],
    )
    others = [s for s in STAGES if s != stage]
    assert all(ran_normally(record, s) for s in others)


async def test_a_slow_fair_fight_says_no_fair_fight_within_limits(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(stages.STAGE_BUDGETS_S, "summary", TINY_BUDGET)
    replace(monkeypatch, "summary", sleep_too_long)
    record = await battle(store)
    assert stage_of(record, "summary").detail == "no fair fight within limits"
    assert record.fair_fight is None
    assert record.result is not None


@pytest.mark.parametrize("stage", list(MEDIA))
async def test_a_media_stage_raising_falls_back_and_the_battle_is_done(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    replace(monkeypatch, MEDIA[stage], boom)
    record = await battle(store)
    assert record.status == "done"
    assert stage_of(record, stage).status == "fallback"
    assert stage_of(record, stage).detail == FALLBACK_DETAILS[stage]
    assert record.result is not None


async def test_a_failing_save_falls_back_that_stage_only(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Images return real output at once, so their save fails while the siblings are mid-pause.
    async def real_images(*_: Any, **__: Any) -> Stubbed[list[Asset]]:
        asset = Asset(asset_id="sprite-1", kind="sprite", url="/media/sprite-1", prompt_hash="0")
        return Stubbed([asset])

    async def save_fails(*_: Any, **__: Any) -> None:
        raise RuntimeError("disk full")

    record_timeline(monkeypatch, ["summary", "challenger", "scripts", "audio", "music"])
    replace(monkeypatch, "images", real_images)
    monkeypatch.setattr(store, "add_assets", save_fails)
    record = await battle(store)
    assert record.status == "done"
    images = stage_of(record, "images")
    assert (images.status, images.detail) == ("fallback", FALLBACK_DETAILS["images"])
    assert all(ran_normally(record, s) for s in STAGES if s != "images")
    assert record.fair_fight is not None and record.assets == []


async def test_audio_and_music_still_run_when_the_script_falls_back(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    replace(monkeypatch, "scripts", boom)
    record = await battle(store)
    script = stage_of(record, "script")
    assert (script.status, script.detail) == ("fallback", FALLBACK_DETAILS["script"])
    assert record.scripts == []
    assert (stage_of(record, "audio").status, stage_of(record, "music").status) == ("done", "done")


async def test_a_slow_script_writer_saves_template_scripts(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A model slower than the stage budget: the battle keeps all three template scripts.
    class SlowChat:
        async def complete(self, *args: Any, **kwargs: Any) -> str:
            await asyncio.sleep(TOO_LONG)
            return ""

    monkeypatch.setitem(stages.STAGE_BUDGETS_S, "script", 0.5)
    monkeypatch.setattr(writer, "get_provider", lambda *_a, **_k: SlowChat())
    record = await battle(store)
    script = stage_of(record, "script")
    assert (script.status, script.detail) == ("fallback", FALLBACK_WITH_VALUE["script"])
    assert [s.kind for s in record.scripts] == ["intro", "play_by_play", "outro"]
    assert all(s.fallback for s in record.scripts)
    assert expected_fair_line(record) in outro_lines(record)


async def test_research_past_its_budget_fails_the_battle(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(stages.STAGE_BUDGETS_S, "research", TINY_BUDGET)
    replace(monkeypatch, "lookup_sheet", sleep_too_long)
    record = await battle(store)
    assert record.status == "failed"
    research = stage_of(record, "research")
    assert (research.status, research.detail) == ("failed", orchestrator.RESEARCH_TOO_SLOW)
    assert record.stat_sheets == [] and record.result is None
    assert all(stage_of(record, s).status == "pending" for s in STAGES[2:])


async def test_research_raising_fails_the_battle(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    replace(monkeypatch, "lookup_sheet", boom)
    record = await battle(store)
    assert record.status == "failed"
    research = stage_of(record, "research")
    assert (research.status, research.detail) == ("failed", orchestrator.RESEARCH_FAILED)


async def test_simulate_raising_fails_the_battle(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    replace(monkeypatch, "simulate", boom)
    record = await battle(store)
    assert record.status == "failed"
    simulate = stage_of(record, "simulate")
    assert (simulate.status, simulate.detail) == ("failed", orchestrator.SIMULATE_FAILED)
    assert record.result is None
    assert all(stage_of(record, s).status == "pending" for s in OPTIONAL)


async def test_simulate_past_its_budget_says_the_fight_is_too_big(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(stages.STAGE_BUDGETS_S, "simulate", TINY_BUDGET)
    replace(monkeypatch, "simulate", sleep_too_long)
    record = await battle(store)
    assert record.status == "failed"
    simulate = stage_of(record, "simulate")
    assert (simulate.status, simulate.detail) == ("failed", orchestrator.SIMULATE_TOO_SLOW)
    # Retrying the same fight can't help, so the message must not suggest it.
    assert simulate.detail is not None and "Please try again." not in simulate.detail
    assert record.result is None
    assert all(stage_of(record, s).status == "pending" for s in OPTIONAL)


async def test_size_reference_entities_are_looked_up_in_parallel(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    real, looked_up = stages.lookup_sheet, []
    in_flight = most = 0

    async def counting(entity: str, variant: str | None = None, raw: str | None = None) -> Any:
        nonlocal in_flight, most
        looked_up.append(entity)
        in_flight += 1
        most = max(most, in_flight)
        await asyncio.sleep(PAUSE)
        in_flight -= 1
        return await real(entity, variant, raw)

    replace(monkeypatch, "lookup_sheet", counting)
    record = await battle(store, matchup("duck", "horse", refs=("horse", "duck")))
    assert sorted(looked_up) == ["duck", "duck", "horse", "horse"]
    assert most == 4  # all four lookups were in flight together
    assert record.status == "done"
    assert stage_of(record, "research").detail is None
    assert [s.fighter_id for s in record.stat_sheets] == ["duck", "horse"]


async def test_a_size_reference_without_a_sheet_is_stub_marked_not_fatal(
    store: BattleStore,
) -> None:
    record = await battle(store, matchup("duck", "horse", refs=("unicorn", None)))
    assert record.status == "done"
    research = stage_of(record, "research")
    assert (research.status, research.detail) == ("done", STUB)
    assert record.result is not None


async def test_a_missing_fighter_still_fails_research(store: BattleStore) -> None:
    record = await battle(store, matchup("unicorn", "horse", refs=(None, "duck")))
    assert record.status == "failed"
    assert "unicorn" in (stage_of(record, "research").detail or "")


def _fight(
    first: dict[str, object],
    second: dict[str, object],
    raw: str = "",
    terrain: str = "arena",
) -> Matchup:
    left = {"raw": first["entity"], **first}
    right = {"raw": second["entity"], **second}
    return Matchup.model_validate(
        {
            "fighters": [left, right],
            "raw_text": raw or f"{left['entity']} vs {right['entity']}",
            "terrain": terrain,
        }
    )


@pytest.mark.parametrize(
    "entity, variant, fighter_id",
    [
        ("bear", "grizzly", "grizzly-bear"),
        ("wolf", "gray", "gray-wolf"),
        ("elephant", "african", "african-elephant"),
    ],
)
async def test_live_style_splits_find_the_seed_sheet(
    store: BattleStore, entity: str, variant: str, fighter_id: str
) -> None:
    # Live intake moves a descriptive word into variant ("bear" + "grizzly").
    record = await battle(store, _fight({"entity": entity, "variant": variant}, {"entity": "duck"}))
    assert record.status == "done"
    assert [s.fighter_id for s in record.stat_sheets] == [fighter_id, "duck"]


async def test_live_style_grey_wolf_finds_the_seed_sheet(store: BattleStore) -> None:
    # "grey" is not the sheet's spelling; the lookup maps it to gray-wolf.
    record = await battle(store, _fight({"entity": "wolf", "variant": "grey"}, {"entity": "horse"}))
    assert record.status == "done"
    assert [s.fighter_id for s in record.stat_sheets] == ["gray-wolf", "horse"]


async def test_mock_style_full_name_with_a_descriptive_variant_still_finds_the_sheet(
    store: BattleStore,
) -> None:
    # Mock intake keeps the full name and a label like "adult male".
    record = await battle(
        store,
        _fight(
            {"entity": "grizzly bear", "variant": "adult male"},
            {"entity": "gray wolf", "variant": "adult", "count": 6},
            raw="a grizzly bear vs 6 gray wolves in a forest",
            terrain="forest",
        ),
    )
    assert record.status == "done"
    assert [s.fighter_id for s in record.stat_sheets] == ["grizzly-bear", "gray-wolf"]


async def test_a_live_style_name_with_no_sheet_still_fails_with_the_plain_message(
    store: BattleStore,
) -> None:
    record = await battle(store, _fight({"entity": "bear", "variant": "polar"}, {"entity": "duck"}))
    assert record.status == "failed"
    detail = stage_of(record, "research").detail or ""
    assert "bear" in detail
    assert detail == stages.NOT_FOUND.format(name="polar bear")


async def test_live_style_raw_phrase_finds_the_seed_sheets(store: BattleStore) -> None:
    # Live intake this time left the descriptor only in raw, with variant empty.
    record = await battle(
        store,
        _fight(
            {"entity": "bear", "raw": "a grizzly bear"},
            {"entity": "wolf", "raw": "6 gray wolves", "count": 6},
            raw="a grizzly bear vs 6 gray wolves in a forest",
            terrain="forest",
        ),
    )
    assert record.status == "done"
    assert [s.fighter_id for s in record.stat_sheets] == ["grizzly-bear", "gray-wolf"]


async def test_a_vague_raw_phrase_still_fails_with_the_plain_message(store: BattleStore) -> None:
    record = await battle(store, _fight({"entity": "bear", "raw": "a bear"}, {"entity": "duck"}))
    assert record.status == "failed"
    detail = stage_of(record, "research").detail or ""
    assert detail == stages.NOT_FOUND.format(name="bear")


async def test_the_no_stat_sheet_message_names_the_fighter_as_typed(store: BattleStore) -> None:
    # A plain name, with no variant.
    record = await battle(store, _fight({"entity": "unicorn"}, {"entity": "duck"}))
    assert record.status == "failed"
    assert (stage_of(record, "research").detail or "") == stages.NOT_FOUND.format(name="unicorn")
    # A label-style variant is not shown.
    record = await battle(
        store, _fight({"entity": "unicorn", "variant": "adult male"}, {"entity": "duck"})
    )
    assert record.status == "failed"
    assert (stage_of(record, "research").detail or "") == stages.NOT_FOUND.format(name="unicorn")
    # If the variant already contains the name, do not double it.
    record = await battle(
        store, _fight({"entity": "unicorn", "variant": "white unicorn"}, {"entity": "duck"})
    )
    assert record.status == "failed"
    assert (stage_of(record, "research").detail or "") == stages.NOT_FOUND.format(
        name="white unicorn"
    )


async def test_the_fair_fight_comes_from_the_real_search(store: BattleStore) -> None:
    record = await battle(store)
    assert record.status == "done" and record.result is not None
    assert (stage_of(record, "summary").status, stage_of(record, "summary").detail) == (
        "done",
        None,
    )
    expected = fair.fair_fight(record.matchup, record.stat_sheets, record.result)
    assert record.fair_fight == expected


async def test_every_stub_stage_says_stub_and_saves_nothing(store: BattleStore) -> None:
    record = await battle(store)
    for name in ("intake", "audio", "music"):
        assert stage_of(record, name).detail == STUB, name
    for name in ("research", "simulate", "summary", "challenger", "images"):
        assert stage_of(record, name).detail is None, name
    assert (stage_of(record, "script").status, stage_of(record, "script").detail) == MOCK_SCRIPT
    # Stub output is a fixture about a different battle, so it never reaches the record;
    # the only assets are the real (mock-drawn) sprites and battlefield, real since A08.
    assert [s.kind for s in record.scripts] == ["intro", "play_by_play", "outro"]  # real (A06)
    assert sorted(a.kind for a in record.assets) == ["battlefield", "sprite", "sprite"]
    assert record.challenger is not None  # real since A05 part 3


async def test_stub_stages_return_their_contract_fixtures() -> None:
    found = await stages.research(matchup("grizzly bear", "gray wolf"))
    result = await stages.simulate(matchup("grizzly bear", "gray wolf"), found)
    written = await stages.scripts(matchup("grizzly bear", "gray wolf"), found, result)
    outputs = [await stages.audio(written.value), await stages.music(found)]
    assert all(out.stub for out in outputs)
    assert not written.stub  # the scripts are real since A06


async def test_the_script_stage_writes_three_real_scripts() -> None:
    fight = matchup("grizzly bear", "gray wolf")
    found = await stages.research(fight)
    result = await stages.simulate(fight, found)
    written = await stages.scripts(fight, found, result)
    assert not written.stub
    assert [s.kind for s in written.value] == ["intro", "play_by_play", "outro"]
    # On mocks the play-by-play is the template, so the stage reports its fallback.
    assert written.fallback == any(s.fallback for s in written.value)
    assert written.fallback


async def test_the_script_stage_passes_the_counts_and_fair_fight_to_the_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fight = _fight({"entity": "grizzly bear"}, {"entity": "gray wolf", "count": 6})
    found = await stages.research(fight)
    result = await stages.simulate(fight, found)
    fair_fight = await stages.summary(fight, found, result)
    seen: dict[str, Any] = {}
    real = writer.write_scripts

    async def spy(sheets: Any, sim: Any, fair_arg: Any, **kwargs: Any) -> list[Any]:
        seen.update(sheets=sheets, result=sim, fair_fight=fair_arg, **kwargs)
        return await real(sheets, sim, fair_arg, **kwargs)

    monkeypatch.setattr(writer, "write_scripts", spy)
    written = await stages.scripts(fight, found, result, fair_fight)
    assert seen["sheets"] == found.sheets and seen["result"] is result
    assert seen["fair_fight"] is fair_fight
    assert list(seen["counts"]) == [1, 6]
    assert len(written.value) == 3


# The fair-fight line the outro should carry for this record's verdict and fair fight.
def expected_fair_line(record: BattleRecord) -> str:
    assert record.result is not None
    counts = [f.count for f in record.matchup.fighters]
    facts = build_facts(record.stat_sheets, record.result, record.fair_fight, counts)
    return fair_fight_line(facts, [f.display_name for f in facts.fighters]).text


def outro_lines(record: BattleRecord) -> list[str]:
    outro = next(s for s in record.scripts if s.kind == "outro")
    return [line.text for line in outro.lines]


async def test_a_battle_saves_all_three_scripts_with_the_fair_fight_in_the_outro(
    store: BattleStore,
) -> None:
    record = await battle(store)
    assert record.status == "done" and record.fair_fight is not None
    assert [s.kind for s in record.scripts] == ["intro", "play_by_play", "outro"]
    # The scripts waited for the summary, so the outro has its fair-fight line.
    assert expected_fair_line(record) in outro_lines(record)
    assert NO_FAIR_CHECK not in outro_lines(record)


async def test_scripts_still_run_when_the_summary_falls_back(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    replace(monkeypatch, "summary", boom)
    record = await battle(store)
    assert record.status == "done"
    assert (stage_of(record, "summary").status, record.fair_fight) == ("fallback", None)
    assert (stage_of(record, "script").status, stage_of(record, "script").detail) == MOCK_SCRIPT
    assert [s.kind for s in record.scripts] == ["intro", "play_by_play", "outro"]
    assert NO_FAIR_CHECK in outro_lines(record)


async def test_real_media_from_several_stages_is_all_saved(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def real_asset(kind: str) -> Callable[..., Awaitable[Stubbed[list[Asset]]]]:
        async def make(*_: Any, **__: Any) -> Stubbed[list[Asset]]:
            await asyncio.sleep(PAUSE)
            asset = Asset(asset_id=f"{kind}-1", kind=kind, url=f"/media/{kind}-1", prompt_hash="0")
            return Stubbed([asset])

        return make

    replace(monkeypatch, "audio", real_asset("narration_audio"))
    replace(monkeypatch, "music", real_asset("music"))
    replace(monkeypatch, "images", real_asset("sprite"))
    record = await battle(store)
    assert sorted(a.asset_id for a in record.assets) == ["music-1", "narration_audio-1", "sprite-1"]
    assert all(stage_of(record, s).detail is None for s in MEDIA)
