"""A05 part 4 (#36): battles saved to SQLite, read back after a restart, and the repeat cache."""

import asyncio
import json
import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.battles import get_store
from app.config import REPO_ROOT, Settings, get_settings, use_settings
from app.db import battles as saved
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.main import create_app
from app.models.battle import BattleRecord
from app.models.matchup import Matchup
from app.pipeline import challenger, stages
from app.pipeline.orchestrator import CACHED, run_battle
from app.pipeline.store import STAGES, BattleStore
from app.research.seed_fighters import find_seed_sheet
from tests.conftest import mock_settings

SIM_RUNS = 20


def matchup(first: str, second: str) -> Matchup:
    fighters = [{"entity": first, "raw": first}, {"entity": second, "raw": second}]
    return Matchup.model_validate({"fighters": fighters, "raw_text": f"{first} vs {second}"})


def stage(record: BattleRecord, name: str) -> tuple[str, str | None]:
    found = next(s for s in record.stages if s.stage == name)
    return found.status, found.detail


@pytest.fixture(autouse=True)
def _quick_simulation() -> None:
    use_settings(mock_settings(sim_runs=SIM_RUNS))


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "app.db"


@pytest.fixture
def store(db_path: Path) -> BattleStore:
    return BattleStore(db_path=db_path)


# Start and finish one battle on the store; hand back its final record.
async def fight(store: BattleStore, first: str, second: str) -> BattleRecord:
    record = await store.create(matchup(first, second))
    await run_battle(record.battle_id, store)
    final = await store.get(record.battle_id)
    assert final is not None
    return final


def test_migration_006_applies_once_and_creates_the_table(db_path: Path) -> None:
    connection = connect(db_path)
    try:
        assert "006-battles.sql" in apply_migrations(connection)
        assert apply_migrations(connection) == []
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
        assert {"battles", "battles_cache_key"} <= names
    finally:
        connection.close()


async def test_repeat_battle_is_served_from_cache_without_simulating(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = await fight(store, "grizzly bear", "gray wolf")
    assert first.status == "done" and first.result is not None

    calls: list[Any] = []
    monkeypatch.setattr(stages.engine, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(stages.fair, "fair_fight", lambda *a, **k: calls.append(a))

    async def no_suggest(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        raise AssertionError("challenger should come from the cache")

    monkeypatch.setattr(challenger, "suggest", no_suggest)
    second = await fight(store, "grizzly bear", "gray wolf")

    assert calls == []
    assert second.battle_id != first.battle_id
    assert second.status == "done"
    assert second.result == first.result
    assert (second.fair_fight, second.challenger) == (first.fair_fight, first.challenger)
    for name in ("simulate", "summary", "challenger"):
        assert stage(second, name) == ("done", CACHED), name
    assert stage(second, "images") == ("done", "stub")
    # The repeat battle still sends its own running -> done change for every stage.
    assert len(await store.changes(second.battle_id)) == 2 * len(STAGES)


async def test_a_cache_hit_without_fair_fight_or_challenger_works_them_out_fresh(
    store: BattleStore, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = await fight(store, "grizzly bear", "gray wolf")
    # Strip the saved fair fight and challenger, keeping the row's cache key.
    stripped = first.model_copy(update={"fair_fight": None, "challenger": None})
    connection = connect(db_path)
    connection.execute(
        "UPDATE battles SET record_json = ? WHERE battle_id = ?",
        (stripped.model_dump_json(), first.battle_id),
    )
    connection.commit()
    connection.close()

    sims: list[Any] = []
    fresh: list[str] = []
    monkeypatch.setattr(stages.engine, "run", lambda *a, **k: sims.append(a))
    for name in ("summary", "challenger"):
        original = getattr(stages, name)

        async def spy(*args: Any, _name: str = name, _work: Any = original) -> Any:
            fresh.append(_name)
            return await _work(*args)

        monkeypatch.setattr(stages, name, spy)
    second = await fight(store, "grizzly bear", "gray wolf")

    assert sims == []
    assert sorted(fresh) == ["challenger", "summary"]
    assert stage(second, "simulate") == ("done", CACHED)
    assert stage(second, "summary")[1] != CACHED
    assert stage(second, "challenger")[1] != CACHED


def test_battles_left_running_by_a_restart_are_marked_failed(db_path: Path) -> None:
    async def leave_running() -> tuple[str, str]:
        before = BattleStore(db_path=db_path)
        finished = await fight(before, "horse", "duck")
        cut_off = await before.create(matchup("grizzly bear", "gray wolf"))
        await before.set_stage(cut_off.battle_id, "intake", "done")
        await before.set_stage(cut_off.battle_id, "research", "running")
        return finished.battle_id, cut_off.battle_id

    done_id, cut_id = asyncio.run(leave_running())
    after = BattleStore(db_path=db_path)  # the store opened after the restart
    cut, finished = asyncio.run(after.get(cut_id)), asyncio.run(after.get(done_id))
    assert cut is not None and finished is not None
    assert cut.status == "failed"
    assert stage(cut, "intake") == ("done", None)
    for name in STAGES[1:]:
        assert stage(cut, name) == ("failed", saved.INTERRUPTED), name
    assert finished.status == "done"  # a finished battle is left alone
    assert all(s.detail != saved.INTERRUPTED for s in finished.stages)


def test_tests_never_use_the_real_data_folder() -> None:
    assert get_settings().data_dir != (REPO_ROOT / "data").resolve()


async def test_a_different_matchup_is_not_served_from_cache(store: BattleStore) -> None:
    await fight(store, "grizzly bear", "gray wolf")
    other = await fight(store, "gray wolf", "grizzly bear")
    assert stage(other, "simulate") == ("done", None)


async def test_two_battles_at_once_never_mix_saved_records(
    store: BattleStore, db_path: Path
) -> None:
    one = await store.create(matchup("grizzly bear", "gray wolf"))
    two = await store.create(matchup("horse", "duck"))
    await asyncio.gather(run_battle(one.battle_id, store), run_battle(two.battle_id, store))
    restarted = BattleStore(db_path=db_path)  # empty memory: reads come from the database
    first, second = await restarted.get(one.battle_id), await restarted.get(two.battle_id)
    assert first is not None and second is not None
    assert [s.fighter_id for s in first.stat_sheets] == ["grizzly-bear", "gray-wolf"]
    assert [s.fighter_id for s in second.stat_sheets] == ["horse", "duck"]
    assert first == await store.get(one.battle_id)
    assert second == await store.get(two.battle_id)


# The app on a fresh store over the same database, as after a restart.
@pytest.fixture
def restarted_client(settings: Settings, db_path: Path, tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(settings, frontend_dist=tmp_path / "missing")
    app.dependency_overrides[get_store] = lambda: BattleStore(db_path=db_path)
    with TestClient(app) as client:
        yield client


def test_a_battle_can_be_read_after_memory_is_cleared(
    db_path: Path, restarted_client: TestClient
) -> None:
    record = asyncio.run(fight(BattleStore(db_path=db_path), "grizzly bear", "gray wolf"))
    client = restarted_client
    response = client.get(f"/api/battles/{record.battle_id}")
    assert response.status_code == 200
    assert BattleRecord.model_validate(response.json()) == record
    # The event stream replays the saved stages, then ends.
    events = client.get(f"/api/battles/{record.battle_id}/events").text.strip().split("\n\n")
    assert len(events) == len(STAGES) + 1
    assert events[-1] == f"event: end\ndata: {json.dumps({'status': 'done'})}"
    assert client.get("/api/battles/b-missing").status_code == 404


async def test_a_failing_database_never_fails_the_battle(
    store: BattleStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(*_: Any, **__: Any) -> None:
        raise sqlite3.OperationalError("disk I/O error at /secret/path")

    monkeypatch.setattr(saved, "save", broken)
    monkeypatch.setattr(saved, "find_done_by_cache_key", broken)
    with caplog.at_level(logging.WARNING):
        record = await fight(store, "grizzly bear", "gray wolf")
    assert record.status == "done" and record.result is not None
    assert "OperationalError" in caplog.text
    assert "/secret/path" not in caplog.text


def test_cached_sheets_is_empty_without_a_database_or_table(tmp_path: Path) -> None:
    missing = tmp_path / "none.db"
    assert challenger.cached_sheets(db_path=missing) == []
    assert not missing.exists()
    connection = connect(tmp_path / "app.db")
    connection.close()
    assert challenger.cached_sheets(db_path=tmp_path / "app.db") == []


def test_cached_sheets_reads_the_newest_rows(tmp_path: Path) -> None:
    sheets = [find_seed_sheet(name) for name in ("horse", "duck", "gray wolf")]
    connection = connect(tmp_path / "app.db")
    connection.execute("CREATE TABLE stat_sheets (fighter_id TEXT, sheet_json TEXT)")
    for sheet in sheets:
        assert sheet is not None
        connection.execute(
            "INSERT INTO stat_sheets VALUES (?, ?)", (sheet.fighter_id, sheet.model_dump_json())
        )
    connection.execute("INSERT INTO stat_sheets VALUES ('broken', '{not json')")
    connection.commit()
    connection.close()
    found = challenger.cached_sheets(limit=3, db_path=tmp_path / "app.db")
    assert [s.fighter_id for s in found] == ["gray-wolf", "duck"]
