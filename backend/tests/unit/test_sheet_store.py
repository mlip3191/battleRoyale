"""G04 part 3: battles find a sheet (seed, cached, or built and cached), and /api/fighters."""

import asyncio
import sqlite3
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.fighters import get_db
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.main import create_app
from app.models.stats import StatSheet
from app.pipeline import challenger
from app.providers.registry import get_provider
from app.research import sheet_store
from app.research.seed_fighters import find_seed_fighter, find_seed_sheet
from app.research.sheet_store import cached_sheet, resolve_stat_sheet, save_sheet

# The front end's StatSheetCard shows its warning banner above this many guesses (MAX_GUESSES).
FRONT_END_MAX_GUESSES = 3


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "app.db")
    apply_migrations(connection)
    yield connection
    connection.close()


def providers():
    return get_provider("chat"), get_provider("embedder"), get_provider("reranker")


def resolve(db: sqlite3.Connection, entity: str, variant=None, raw=None) -> StatSheet | None:
    return asyncio.run(resolve_stat_sheet(db, providers(), entity, variant, raw))


def test_saved_sheets_are_read_back_newest_first(db: sqlite3.Connection) -> None:
    lion = find_seed_sheet("african lion")
    assert lion is not None
    save_sheet(db, lion)
    save_sheet(db, lion)  # the same version again changes nothing
    assert db.execute("SELECT COUNT(*) FROM stat_sheets").fetchone()[0] == 1
    newer = lion.model_copy(update={"sheet_hash": "f" * 64})
    save_sheet(db, newer)
    assert cached_sheet(db, "african-lion") == newer
    assert cached_sheet(db, "nobody") is None


def test_a_seed_sheet_wins_and_keeps_variant_and_raw(db: sqlite3.Connection) -> None:
    sheet = resolve(db, "bear", raw="a grizzly bear")
    assert sheet is not None and sheet.fighter_id == "grizzly-bear"
    assert db.execute("SELECT COUNT(*) FROM stat_sheets").fetchone()[0] == 0


def test_a_seed_list_fighter_is_built_once_then_reused(db: sqlite3.Connection) -> None:
    first = resolve(db, "pickup truck")
    assert first is not None and first.fighter_id == "pickup-truck"
    assert first.weapons == ["ramming"]
    assert cached_sheet(db, "pickup-truck") == first
    assert resolve(db, "Pickup Truck") == first


def test_variant_and_raw_find_seed_list_fighters() -> None:
    found = find_seed_fighter("retriever", "golden")
    assert found is not None and found.id == "golden-retriever"
    found = find_seed_fighter("retriever", raw="3 golden retrievers")
    assert found is not None and found.id == "golden-retriever"
    found = find_seed_fighter("bee", raw="a swarm of honey bees")
    assert found is not None and found.id == "honey-bee"
    assert find_seed_fighter("bear", raw="a bear") is None


def test_no_knowledge_base_still_builds_a_sheet(db: sqlite3.Connection) -> None:
    assert not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunks_vec'").fetchone()
    sheet = resolve(db, "chimpanzee")
    assert sheet is not None and sheet.fighter_id == "chimpanzee"


def test_unknown_and_mythical_names_get_no_sheet(db: sqlite3.Connection) -> None:
    assert resolve(db, "unicorn") is None
    assert resolve(db, "bear", "polar") is None


def test_slow_extraction_falls_back_to_facts_and_defaults(
    db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def slow(connection, providers, profile):
        await asyncio.sleep(5)

    monkeypatch.setattr(sheet_store, "build_sheet_with_evidence", slow)
    monkeypatch.setattr(sheet_store, "EXTRACTION_BUDGET_S", 0.01)
    sheet = resolve(db, "toaster")
    assert sheet is not None and sheet.fighter_id == "toaster"
    assert cached_sheet(db, "toaster") is None  # not cached, so the next battle retries


def test_a_sheet_with_no_evidence_gets_the_guesswork_banner(db: sqlite3.Connection) -> None:
    sheet = resolve(db, "house mouse")
    assert sheet is not None
    guesses = [s for s in sheet.stats.values() if s.is_estimate or s.method == "assumption"]
    assert len(guesses) > FRONT_END_MAX_GUESSES


def test_the_challenger_reads_cached_sheets(db: sqlite3.Connection, tmp_path: Path) -> None:
    built = resolve(db, "goose")
    assert built is not None
    assert challenger.cached_sheets(db_path=tmp_path / "app.db") == [built]


@pytest.fixture
def client(db: sqlite3.Connection, tmp_path: Path) -> Iterator[TestClient]:
    # The routes run on the client's thread, so they open their own connection to the same file.
    async def same_file() -> AsyncIterator[sqlite3.Connection]:
        connection = connect(tmp_path / "app.db")
        try:
            yield connection
        finally:
            connection.close()

    app = create_app(frontend_dist=tmp_path / "missing")
    app.dependency_overrides[get_db] = same_file
    with TestClient(app) as test_client:
        yield test_client


def test_search_lists_seed_and_cached_fighters(client: TestClient, db: sqlite3.Connection) -> None:
    rows = client.get("/api/fighters", params={"q": "wolf"}).json()
    assert rows == [{"fighter_id": "gray-wolf", "display_name": "Gray wolf", "cached": True}]
    assert client.get("/api/fighters", params={"q": "truck"}).json()[0]["cached"] is False
    resolve(db, "pickup truck")
    assert client.get("/api/fighters", params={"q": "TRUCK"}).json()[0]["cached"] is True
    assert client.get("/api/fighters", params={"q": "dragon"}).json() == []
    assert client.get("/api/fighters").status_code == 422


def test_read_a_fighter_returns_seed_or_cached_sheets(
    client: TestClient, db: sqlite3.Connection
) -> None:
    reply = client.get("/api/fighters/grizzly-bear")
    assert reply.status_code == 200
    assert StatSheet.model_validate(reply.json()) == find_seed_sheet("grizzly bear")
    assert client.get("/api/fighters/samurai").status_code == 404
    built = resolve(db, "samurai")
    assert StatSheet.model_validate(client.get("/api/fighters/samurai").json()) == built
