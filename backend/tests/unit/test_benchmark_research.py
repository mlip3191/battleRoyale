"""F07: `--sheets research` builds every sheet with the research pipeline, never from the seed."""

import asyncio
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.matchup import FighterRequest
from app.providers.registry import get_provider
from app.research.benchmark_sheets import research_sheets
from app.research.seed_fighters import find_seed_sheet
from app.simulation import benchmark as bm
from app.simulation.benchmark import BenchmarkError, Entry

MOCK = bm.MOCK_DIR


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "app.db")
    apply_migrations(connection)
    yield connection
    connection.close()


def providers():
    return get_provider("chat"), get_provider("embedder"), get_provider("reranker")


def entries() -> list[Entry]:
    return [
        *bm.load_entries(MOCK / "matchups.yaml", False),
        *bm.load_entries(MOCK / "heldout.yaml", True),
    ]


def build(db: sqlite3.Connection, items: list[Entry]):
    return asyncio.run(research_sheets(items, db, providers()))


def test_a_seed_list_fighter_gets_a_pipeline_sheet_not_the_seed_sheet(db) -> None:
    sheets = build(db, entries())
    wolf = sheets.get(FighterRequest(entity="gray-wolf", raw="a gray wolf"))
    seed = find_seed_sheet("gray wolf")
    assert wolf.fighter_id == "gray-wolf"
    assert (
        seed is not None and wolf.sheet_hash != seed.sheet_hash
    )  # built, not the hand-verified one


def test_a_fighter_the_pipeline_cannot_build_is_left_out_and_shows_as_skipped(db) -> None:
    sheets = build(db, entries())
    with pytest.raises(BenchmarkError, match="no stat sheet"):
        sheets.get(FighterRequest(entity="not-a-fighter", raw="a not-a-fighter"))


def test_each_fighter_is_built_only_once(db, monkeypatch) -> None:
    from app.research import benchmark_sheets

    calls: list[str] = []
    real = benchmark_sheets.build_sheet_with_evidence

    async def counting(connection, provs, profile):
        calls.append(profile.fighter_id)
        return await real(connection, provs, profile)

    monkeypatch.setattr(benchmark_sheets, "build_sheet_with_evidence", counting)
    build(db, entries() * 2)
    assert len(calls) == len(set(calls)) and calls
