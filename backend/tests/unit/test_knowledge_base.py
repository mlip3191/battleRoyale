"""Database setup, chunking, and passage storage, using the mock embedder."""

import re
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
import sqlite_vec

from app.db.connection import connect
from app.db.migrate import MIGRATIONS_DIR, apply_migrations
from app.providers.mock.text import MockEmbedder
from app.research.chunking import CHUNK_CHARS, OVERLAP_CHARS, chunk_text
from app.research.kb_store import DocumentRecord, ensure_vector_table, store_document

RECORD = DocumentRecord(
    doc_id="horse/wikipedia",
    fighter_id="horse",
    source="wikipedia",
    title="Horse",
    url="https://example.test/Horse",
    license="CC BY-SA 4.0",
    retrieved_at="2026-11-10T00:00:00+00:00",
    text="## Size\n" + "A horse weighs from 500 to 600 kilograms. " * 60,
)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "nested" / "app.db")
    apply_migrations(connection)
    yield connection
    connection.close()


def count(connection: sqlite3.Connection, table: str) -> int:
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_connection_uses_wal_foreign_keys_and_sqlite_vec(database: sqlite3.Connection) -> None:
    assert database.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert database.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert database.execute("SELECT vec_version()").fetchone()[0]


def test_migrations_apply_once(database: sqlite3.Connection) -> None:
    assert apply_migrations(database) == []
    # One row per migration file, however many there are (D08 added the second).
    files = list(MIGRATIONS_DIR.glob("*.sql"))
    assert len(files) >= 2
    assert count(database, "schema_migrations") == len(files)


def test_a_failed_migration_leaves_nothing_behind(tmp_path: Path) -> None:
    (tmp_path / "001-bad.sql").write_text("CREATE TABLE half (x);\nNOT VALID SQL;", "utf-8")
    connection = connect(tmp_path / "app.db")
    with pytest.raises(sqlite3.Error):
        apply_migrations(connection, tmp_path)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    assert "half" not in tables
    assert count(connection, "schema_migrations") == 0
    connection.close()


def test_chunks_respect_the_size_and_overlap() -> None:
    chunks = chunk_text(" ".join(f"word{n}" for n in range(1000)))
    assert len(chunks) > 1
    assert all(len(chunk.text) <= CHUNK_CHARS for chunk in chunks)
    tail = chunks[0].text[-OVERLAP_CHARS // 2 :].split(" ", 1)[1]
    assert chunks[1].text.startswith(tail) or tail in chunks[1].text
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))


def test_chunks_never_cut_a_number_in_half() -> None:
    text = " ".join(str(100000 + n) for n in range(2000))
    for chunk in chunk_text(text):
        assert all(re.fullmatch(r"\d{6}", part) for part in chunk.text.split())


def test_chunks_keep_their_section_heading() -> None:
    chunks = chunk_text("Intro text.\n\n## Diet\nEats grass.\n\n### Foals\nDrink milk.")
    assert [(c.heading, c.text) for c in chunks] == [
        (None, "Intro text."),
        ("Diet", "Eats grass."),
        ("Foals", "Drink milk."),
    ]


def test_a_heading_ending_in_a_hash_keeps_it() -> None:
    assert chunk_text("## Learning C#\nBody.")[0].heading == "Learning C#"
    assert chunk_text("## Closed heading ##\nBody.")[0].heading == "Closed heading"


def test_chunking_empty_text_and_bad_settings() -> None:
    assert chunk_text("   \n ") == []
    with pytest.raises(ValueError):
        chunk_text("text", size=10, overlap=10)


async def test_storing_a_document_twice_changes_nothing(database: sqlite3.Connection) -> None:
    embedder = MockEmbedder()
    await ensure_vector_table(database, embedder)
    assert await store_document(database, RECORD, embedder) is True
    rows = (count(database, "documents"), count(database, "chunks"), count(database, "chunks_vec"))
    assert rows[1] > 1 and rows[1] == rows[2]
    assert await store_document(database, RECORD, embedder) is False
    assert (
        count(database, "documents"),
        count(database, "chunks"),
        count(database, "chunks_vec"),
    ) == rows


async def test_same_text_still_updates_its_attribution(database: sqlite3.Connection) -> None:
    embedder = MockEmbedder()
    await ensure_vector_table(database, embedder)
    await store_document(database, RECORD, embedder)
    newer = replace(RECORD, url="https://example.test/new", license="CC0 1.0")
    assert await store_document(database, newer, embedder) is False
    row = database.execute("SELECT url, license FROM documents").fetchone()
    assert (row["url"], row["license"]) == ("https://example.test/new", "CC0 1.0")


async def test_a_document_must_say_where_it_came_from(database: sqlite3.Connection) -> None:
    embedder = MockEmbedder()
    await ensure_vector_table(database, embedder)
    with pytest.raises(sqlite3.IntegrityError):
        await store_document(database, replace(RECORD, license=""), embedder)
    assert count(database, "documents") == 0


async def test_changed_text_replaces_the_old_passages(database: sqlite3.Connection) -> None:
    embedder = MockEmbedder()
    await ensure_vector_table(database, embedder)
    await store_document(database, RECORD, embedder)
    assert await store_document(database, replace(RECORD, text="Short new text."), embedder)
    assert count(database, "chunks") == 1 and count(database, "chunks_vec") == 1


async def test_a_new_embedding_size_rebuilds_the_table(database: sqlite3.Connection) -> None:
    await ensure_vector_table(database, MockEmbedder(dim=64))
    await store_document(database, RECORD, MockEmbedder(dim=64))
    larger = MockEmbedder(dim=128)
    assert await ensure_vector_table(database, larger) == 128
    assert count(database, "documents") == 0 and count(database, "chunks_vec") == 0
    assert await store_document(database, RECORD, larger) is True


async def test_a_missing_vector_table_is_rebuilt(database: sqlite3.Connection) -> None:
    embedder = MockEmbedder()
    await ensure_vector_table(database, embedder)
    database.execute("DROP TABLE chunks_vec")
    assert await ensure_vector_table(database, embedder) == 64
    assert await store_document(database, RECORD, embedder) is True
    assert count(database, "chunks_vec") > 0


async def test_a_failed_rebuild_keeps_the_old_table(database: sqlite3.Connection) -> None:
    await ensure_vector_table(database, MockEmbedder(dim=64))
    await store_document(database, RECORD, MockEmbedder(dim=64))
    database.execute(
        "CREATE TRIGGER fail_rebuild BEFORE INSERT ON kb_meta "
        "BEGIN SELECT RAISE(ABORT, 'simulated crash'); END"
    )
    with pytest.raises(sqlite3.Error):
        await ensure_vector_table(database, MockEmbedder(dim=128))
    assert count(database, "documents") == 1 and count(database, "chunks_vec") > 0


async def test_a_failed_vector_insert_stores_nothing(database: sqlite3.Connection) -> None:
    await ensure_vector_table(database, MockEmbedder(dim=64))
    with pytest.raises(sqlite3.Error):
        await store_document(database, RECORD, MockEmbedder(dim=32))
    assert count(database, "documents") == 0 and count(database, "chunks") == 0


async def test_stored_passages_can_be_found_by_vector(database: sqlite3.Connection) -> None:
    embedder = MockEmbedder()
    await ensure_vector_table(database, embedder)
    await store_document(database, RECORD, embedder)
    first = database.execute("SELECT chunk_id, text FROM chunks WHERE ordinal = 0").fetchone()
    vector = (await embedder.embed([first["text"]]))[0]
    match = database.execute(
        "SELECT chunk_id FROM chunks_vec WHERE embedding MATCH ? AND k = 1",
        (sqlite_vec.serialize_float32(vector),),
    ).fetchone()
    assert match["chunk_id"] == first["chunk_id"]
