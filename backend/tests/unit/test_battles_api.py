"""The thin A05 stub path: start a battle, watch its stages, and read the verdict (#36)."""

import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import Future
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.battles import get_store
from app.config import Settings, use_settings
from app.main import create_app
from app.models.battle import BattleRecord, StageStatus
from app.models.matchup import Matchup
from app.pipeline import orchestrator, stages
from app.pipeline.orchestrator import FALLBACK_WITH_VALUE, STUB, run_battle
from app.pipeline.store import STAGES, BattleStore
from app.research.seed_fighters import find_seed_sheet
from tests.conftest import mock_settings

SIM_RUNS = 20  # enough to get a verdict; keeps the tests fast
WAIT_SECONDS = 30.0
SSE_TIMEOUT = 10.0  # hard deadline for reading an event stream


def matchup_body(first: str, second: str, **extra: Any) -> dict[str, Any]:
    fighters = [{"entity": first, "raw": first}, {"entity": second, "raw": second}]
    for side, fields in extra.items():
        fighters[int(side[-1])].update(fields)
    return {"fighters": fighters, "raw_text": f"{first} vs {second}"}


def matchup(first: str, second: str, **extra: Any) -> Matchup:
    return Matchup.model_validate(matchup_body(first, second, **extra))


# Few simulation runs, so each battle finishes in well under a second.
@pytest.fixture(autouse=True)
def _quick_simulation() -> None:
    use_settings(mock_settings(sim_runs=SIM_RUNS))


@pytest.fixture
def store() -> BattleStore:
    return BattleStore()


# A running app (its event loop stays up between requests) with a fresh, empty store.
@pytest.fixture
def client(settings: Settings, store: BattleStore, tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(settings, frontend_dist=tmp_path / "missing")
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client


def start(client: TestClient, body: dict[str, Any]) -> str:
    response = client.post("/api/battles", json=body)
    assert response.status_code == 202, response.text
    return response.json()["battle_id"]


# Poll GET until the battle stops running.
def wait_until_finished(client: TestClient, battle_id: str) -> BattleRecord:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        response = client.get(f"/api/battles/{battle_id}")
        assert response.status_code == 200
        record = BattleRecord.model_validate(response.json())
        if record.status != "running":
            return record
        time.sleep(0.02)
    raise AssertionError(f"battle {battle_id} never finished")


def final_stage(record: BattleRecord, name: str) -> StageStatus:
    return next(stage for stage in record.stages if stage.stage == name)


def test_post_returns_202_with_a_battle_id(client: TestClient) -> None:
    response = client.post("/api/battles", json=matchup_body("grizzly bear", "gray wolf"))
    assert response.status_code == 202
    assert response.json()["battle_id"].startswith("b-")


def test_battle_reaches_done_with_a_verdict(client: TestClient) -> None:
    record = wait_until_finished(client, start(client, matchup_body("grizzly bear", "gray wolf")))
    assert record.status == "done"
    assert [sheet.fighter_id for sheet in record.stat_sheets] == ["grizzly-bear", "gray-wolf"]
    assert record.result is not None
    assert record.result.runs == SIM_RUNS
    assert record.result.outcome in {"win_0", "win_1", "draw", "no_contest"}
    assert all(stage.status == "done" for stage in record.stages if stage.stage != "script")
    # The mock play-by-play is the template on purpose, so the script stage ends "fallback"
    # with all three scripts still saved.
    script = final_stage(record, "script")
    assert (script.status, script.detail) == ("fallback", FALLBACK_WITH_VALUE["script"])
    assert [s.kind for s in record.scripts] == ["intro", "play_by_play", "outro"]
    # The real challenger stage ran on the mock decision model and saved its pick.
    assert record.challenger is not None
    assert record.challenger.entity not in {s.display_name for s in record.stat_sheets}
    assert 0.0 <= record.challenger.tested_win_prob <= 1.0


def test_every_stub_stage_says_stub(client: TestClient) -> None:
    record = wait_until_finished(client, start(client, matchup_body("horse", "duck")))
    for name in STAGES:
        detail = final_stage(record, name).detail
        if name in ("research", "simulate", "summary", "challenger", "script", "images"):
            assert detail != STUB, name
        else:
            assert detail == STUB, name


# Each stage went running -> done exactly once; research and simulate came first, in order.
# The script ends "fallback" instead: on mocks the play-by-play is the template on purpose.
def assert_each_stage_ran(changes: list[StageStatus]) -> None:
    pairs = [(c.stage, c.status) for c in changes]
    assert pairs[:6] == [(stage, status) for stage in STAGES[:3] for status in ("running", "done")]
    for stage in STAGES:
        end = "fallback" if stage == "script" else "done"
        assert [status for name, status in pairs if name == stage] == ["running", end], stage


async def test_new_battle_starts_with_every_stage_pending(store: BattleStore) -> None:
    record = await store.create(matchup("grizzly bear", "gray wolf"))
    assert [stage.stage for stage in record.stages] == list(STAGES)
    assert {stage.status for stage in record.stages} == {"pending"}
    assert record.status == "running"


async def test_stages_move_pending_running_done(store: BattleStore) -> None:
    record = await store.create(matchup("grizzly bear", "gray wolf"))
    await run_battle(record.battle_id, store)
    assert_each_stage_ran(await store.changes(record.battle_id))


def test_unknown_fighter_fails_the_battle_with_a_reason(client: TestClient) -> None:
    record = wait_until_finished(client, start(client, matchup_body("grizzly bear", "unicorn")))
    assert record.status == "failed"
    research = final_stage(record, "research")
    assert research.status == "failed"
    assert research.detail and "unicorn" in research.detail
    assert record.result is None
    assert final_stage(record, "simulate").status == "pending"


def test_size_swap_with_a_seed_reference_reaches_done(client: TestClient) -> None:
    body = matchup_body("duck", "horse", side0={"size_reference": "horse"})
    record = wait_until_finished(client, start(client, body))
    assert record.status == "done"
    assert (final_stage(record, "research").status, final_stage(record, "research").detail) == (
        "done",
        None,
    )
    assert record.result is not None


def test_simulation_error_fails_the_battle(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: Any, **__: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(stages.engine, "run", broken)
    record = wait_until_finished(client, start(client, matchup_body("horse", "duck")))
    assert record.status == "failed"
    assert final_stage(record, "simulate").detail == orchestrator.SIMULATE_FAILED


async def test_two_battles_at_once_never_mix_records(store: BattleStore) -> None:
    first = await store.create(matchup("grizzly bear", "gray wolf"))
    second = await store.create(matchup("horse", "duck"))
    await asyncio.gather(run_battle(first.battle_id, store), run_battle(second.battle_id, store))
    one, two = await store.get(first.battle_id), await store.get(second.battle_id)
    assert one is not None and two is not None
    assert [s.fighter_id for s in one.stat_sheets] == ["grizzly-bear", "gray-wolf"]
    assert [s.fighter_id for s in two.stat_sheets] == ["horse", "duck"]
    assert one.matchup.raw_text == "grizzly bear vs gray wolf"
    assert two.matchup.raw_text == "horse vs duck"
    assert one.result is not None and two.result is not None
    assert one.result.seed != two.result.seed
    assert len(await store.changes(first.battle_id)) == 2 * len(STAGES)
    assert len(await store.changes(second.battle_id)) == 2 * len(STAGES)


def test_two_battles_through_the_api_never_mix_records(client: TestClient) -> None:
    first = start(client, matchup_body("grizzly bear", "gray wolf"))
    second = start(client, matchup_body("horse", "duck"))
    assert first != second
    one, two = wait_until_finished(client, first), wait_until_finished(client, second)
    assert (one.battle_id, two.battle_id) == (first, second)
    assert [s.fighter_id for s in one.stat_sheets] == ["grizzly-bear", "gray-wolf"]
    assert [s.fighter_id for s in two.stat_sheets] == ["horse", "duck"]


async def test_a_copy_from_the_store_cannot_change_the_record(store: BattleStore) -> None:
    record = await store.create(matchup("grizzly bear", "gray wolf"))
    record.stages[0].status = "failed"
    stored = await store.get(record.battle_id)
    assert stored is not None and stored.stages[0].status == "pending"


def test_unknown_battle_id_is_404(client: TestClient) -> None:
    assert client.get("/api/battles/b-missing").status_code == 404
    assert client.get("/api/battles/b-missing/events").status_code == 404


# Split a Server-Sent Events body into (event name, data) pairs.
def parse_sse(body: str) -> list[tuple[str, str]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], fields["data"]))
    return events


# Start reading the event stream on a daemon thread, so a stream that never ends can't hang
# the test run; call .result(timeout=...) on the returned future.
def open_events(client: TestClient, battle_id: str) -> Future[httpx.Response]:
    future: Future[httpx.Response] = Future()

    def fetch() -> None:
        try:
            future.set_result(client.get(f"/api/battles/{battle_id}/events"))
        except BaseException as error:
            future.set_exception(error)

    threading.Thread(target=fetch, daemon=True).start()
    return future


# Read the whole event stream, failing the test if it hasn't ended within SSE_TIMEOUT.
def read_events(client: TestClient, battle_id: str) -> httpx.Response:
    return open_events(client, battle_id).result(timeout=SSE_TIMEOUT)


def test_event_stream_sends_every_stage_change_then_end(client: TestClient) -> None:
    battle_id = start(client, matchup_body("grizzly bear", "gray wolf"))
    response = read_events(client, battle_id)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names == ["stage"] * (2 * len(STAGES)) + ["end"]
    assert_each_stage_ran([StageStatus.model_validate_json(data) for _, data in events[:-1]])
    assert json.loads(events[-1][1]) == {"status": "done"}
    # Polling after the stream ends returns the same final record.
    assert wait_until_finished(client, battle_id).status == "done"


def test_event_stream_ends_for_a_failed_battle(client: TestClient) -> None:
    battle_id = start(client, matchup_body("unicorn", "gray wolf"))
    events = parse_sse(read_events(client, battle_id).text)
    assert events[-1] == ("end", json.dumps({"status": "failed"}))
    last_change = StageStatus.model_validate_json(events[-2][1])
    assert (last_change.stage, last_change.status) == ("research", "failed")


def test_event_stream_follows_a_battle_that_is_still_running(
    client: TestClient, store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Hold the simulation until the stream is subscribed, so this is the live path, not replay.
    release, subscribed = threading.Event(), threading.Event()
    real_run, real_follow = stages.engine.run, store.follow

    def held_run(*args: Any, **kwargs: Any) -> Any:
        assert release.wait(timeout=SSE_TIMEOUT)
        return real_run(*args, **kwargs)

    def watched_follow(battle_id: str) -> AsyncIterator[StageStatus]:
        subscribed.set()
        return real_follow(battle_id)

    monkeypatch.setattr(stages.engine, "run", held_run)
    # The held simulation must not trip its own time limit while the test waits.
    monkeypatch.setitem(stages.STAGE_BUDGETS_S, "simulate", SSE_TIMEOUT)
    monkeypatch.setattr(store, "follow", watched_follow)
    try:
        battle_id = start(client, matchup_body("grizzly bear", "gray wolf"))
        future = open_events(client, battle_id)
        assert subscribed.wait(timeout=SSE_TIMEOUT)
        assert client.get(f"/api/battles/{battle_id}").json()["status"] == "running"
        assert not future.done()
    finally:
        release.set()
    events = parse_sse(future.result(timeout=SSE_TIMEOUT).text)
    assert [name for name, _ in events] == ["stage"] * (2 * len(STAGES)) + ["end"]
    assert json.loads(events[-1][1]) == {"status": "done"}


def test_a_crash_in_set_stage_still_ends_the_battle_failed(
    client: TestClient, store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_set_stage = store.set_stage
    calls = 0

    async def flaky_set_stage(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("store hiccup")
        await real_set_stage(*args, **kwargs)

    monkeypatch.setattr(store, "set_stage", flaky_set_stage)
    battle_id = start(client, matchup_body("grizzly bear", "gray wolf"))
    record = wait_until_finished(client, battle_id)
    assert record.status == "failed"
    first = final_stage(record, STAGES[0])
    assert (first.status, first.detail) == ("failed", orchestrator.UNEXPECTED)
    events = parse_sse(read_events(client, battle_id).text)
    assert events[-1] == ("end", json.dumps({"status": "failed"}))


def test_seed_sheet_lookup_matches_names_and_rejects_others() -> None:
    sheet = find_seed_sheet("Grizzly Bear")
    assert sheet is not None and sheet.fighter_id == "grizzly-bear"
    assert find_seed_sheet("unicorn") is None
    assert find_seed_sheet("../fighters") is None
    assert find_seed_sheet("") is None


def test_seed_sheet_lookup_tries_variant_plus_entity_then_entity_alone() -> None:
    for entity, variant, fighter_id in (
        ("bear", "grizzly", "grizzly-bear"),
        ("wolf", "gray", "gray-wolf"),
        ("elephant", "african", "african-elephant"),
    ):
        sheet = find_seed_sheet(entity, variant)
        assert sheet is not None and sheet.fighter_id == fighter_id
    # Mock-style: full name as entity, descriptive variant with no sheet of its own.
    sheet = find_seed_sheet("grizzly bear", "adult male")
    assert sheet is not None and sheet.fighter_id == "grizzly-bear"
    # Same slug and empty-name rules when a variant is present.
    assert find_seed_sheet("../fighters", "grizzly") is None
    assert find_seed_sheet("", "grizzly") is None
    assert find_seed_sheet("unicorn", "adult") is None


def test_seed_sheet_lookup_uses_a_unique_match_from_the_raw_phrase() -> None:
    for entity, raw, fighter_id in (
        ("bear", "a grizzly bear", "grizzly-bear"),
        ("wolf", "6 gray wolves", "gray-wolf"),
        ("elephant", "an african elephant", "african-elephant"),
    ):
        sheet = find_seed_sheet(entity, raw=raw)
        assert sheet is not None and sheet.fighter_id == fighter_id
    # Vague raw has no unique sheet: "grizzly" is not in the phrase.
    assert find_seed_sheet("bear", raw="a bear") is None
    assert find_seed_sheet("unicorn", raw="a fluffy unicorn") is None
    assert find_seed_sheet("bear", raw="../fighters") is None
    assert find_seed_sheet("", raw="a grizzly bear") is None


def test_seed_sheet_lookup_accepts_grey_and_plural_names() -> None:
    # Live-style split: entity wolf + British spelling in variant.
    sheet = find_seed_sheet("wolf", "grey")
    assert sheet is not None and sheet.fighter_id == "gray-wolf"
    # Raw phrase with a British spelling and a plural; the aliases map both words.
    sheet = find_seed_sheet("wolf", raw="6 grey wolves")
    assert sheet is not None and sheet.fighter_id == "gray-wolf"
    sheet = find_seed_sheet("wolves", "grey")
    assert sheet is not None and sheet.fighter_id == "gray-wolf"
    # Plural entity finds the singular sheet when one exists.
    sheet = find_seed_sheet("ducks")
    assert sheet is not None and sheet.fighter_id == "duck"
    # Bare "wolves" must not grab gray-wolf.
    assert find_seed_sheet("wolves") is None
    assert find_seed_sheet("wolves", raw="wolves") is None
    # Names that should still miss still miss.
    assert find_seed_sheet("bear", "polar") is None
    assert find_seed_sheet("bear") is None
    assert find_seed_sheet("bear", raw="a bear") is None
    # Slugs stay [a-z0-9-]; aliases do not loosen the path check.
    assert find_seed_sheet("../fighters", "grey") is None
    assert find_seed_sheet("wolves", raw="../fighters") is None
