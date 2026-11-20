"""The prebuilt knowledge base (D-66, #438): export, load into an empty one, and the model check."""

import asyncio
import hashlib
import json
import sqlite3
import struct
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.main import PREBUILT_MISMATCH, create_app
from app.providers.mock.text import MockEmbedder
from app.research.kb_prebuilt import (
    MANIFEST_FILE,
    PART_MAX_BYTES,
    LoadOutcome,
    export_prebuilt,
    load_prebuilt,
    model_fingerprint,
    to_half,
)
from app.research.kb_store import DocumentRecord, ensure_vector_table, store_document
from app.research.retrieve import retrieve

FIXTURE = Path(__file__).parents[1] / "fixtures" / "prebuilt-kb"
MODEL = "fixture-embedder"  # a made-up name: the fixture's fingerprint is of this
DIM = 8
EMBEDDER = MockEmbedder(dim=DIM)
QUERY = "adult body mass weight kg lb weighs"
TEXTS = {
    "horse": (
        "Horse",
        "## Size\n\nA large horse weighs 500 kg and stands 1.6 m at the shoulder.\n\n"
        "## Behaviour\n\nHorses are herd animals that can run at 88 km/h in a short sprint.",
    ),
    "duck": (
        "Mallard",
        "## Description\n\nThe mallard weighs about 1.1 kg and is 60 cm long.\n\n"
        "## Diet\n\nMallards eat plants, insects and small fish they find near the water.",
    ),
}


def record(fighter_id: str, title: str, text: str) -> DocumentRecord:
    return DocumentRecord(
        doc_id=f"{fighter_id}/wikipedia",
        fighter_id=fighter_id,
        source="wikipedia",
        title=title,
        url=f"https://en.wikipedia.org/wiki/{title}",
        license="CC BY-SA 4.0",
        retrieved_at="2026-11-01T00:00:00+00:00",
        text=text,
    )


def database(path: Path) -> sqlite3.Connection:
    connection = connect(path)
    apply_migrations(connection)
    return connection


# A knowledge base built the normal way (store_document), as `npm run ingest` would.
def ingested(path: Path, fighters: dict[str, tuple[str, str]] = TEXTS) -> sqlite3.Connection:
    connection = database(path)

    async def build() -> None:
        await ensure_vector_table(connection, EMBEDDER)
        for fighter_id, (title, text) in fighters.items():
            await store_document(connection, record(fighter_id, title, text), EMBEDDER)

    asyncio.run(build())
    return connection


@pytest.fixture
def fresh(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = database(tmp_path / "fresh.db")
    yield connection
    connection.close()


# Every file in folder by name, to compare whole exports.
def files(folder: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(folder.iterdir())}


def top(connection: sqlite3.Connection, fighter_id: str) -> list[tuple[str, float]]:
    passages = asyncio.run(retrieve(connection, EMBEDDER, fighter_id, QUERY))
    return [(p.text, round(p.distance, 6)) for p in passages]


def test_a_fresh_database_loads_the_fixture_and_retrieval_finds_its_passages(
    fresh: sqlite3.Connection,
) -> None:
    result = load_prebuilt(fresh, MODEL, FIXTURE)
    assert result.outcome is LoadOutcome.LOADED
    assert (result.documents, result.chunks) == (
        2,
        fresh.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
    )
    passages = top(fresh, "horse")
    assert passages and all("orse" in text for text, _ in passages)
    assert fresh.execute("SELECT value FROM kb_meta WHERE key = 'embedding_dim'").fetchone()[
        0
    ] == str(DIM)


def test_a_different_model_is_refused_and_nothing_is_loaded(fresh: sqlite3.Connection) -> None:
    assert load_prebuilt(fresh, "another-model", FIXTURE).outcome is LoadOutcome.MODEL_MISMATCH
    assert load_prebuilt(fresh, "", FIXTURE).outcome is LoadOutcome.MODEL_MISMATCH
    assert fresh.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


def test_startup_says_plainly_when_the_model_does_not_match(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(
        _env_file=None, provider_mode="live", data_dir=tmp_path, embeddings_model="another-model"
    )
    with TestClient(create_app(settings, tmp_path / "missing", None, FIXTURE)):
        pass
    assert PREBUILT_MISMATCH in capsys.readouterr().out
    connection = connect(tmp_path / "app.db")
    try:
        assert connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
    finally:
        connection.close()


def test_startup_loads_the_prebuilt_files_into_an_empty_knowledge_base(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(
        _env_file=None, provider_mode="live", data_dir=tmp_path, embeddings_model=MODEL
    )
    with TestClient(create_app(settings, tmp_path / "missing", None, FIXTURE)):
        pass
    out = capsys.readouterr().out
    assert "Loaded the prebuilt knowledge base" in out and "npm run ingest` once" not in out
    connection = connect(tmp_path / "app.db")
    try:
        assert top(connection, "duck")
    finally:
        connection.close()


def test_mock_mode_never_loads_the_prebuilt_files(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None, provider_mode="mock", data_dir=tmp_path, embeddings_model=MODEL
    )
    with TestClient(create_app(settings, tmp_path / "missing", None, FIXTURE)):
        pass
    connection = connect(tmp_path / "app.db")
    try:
        assert connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
    finally:
        connection.close()


# The file stores float16, so distances move by rounding only; the ranking must not change.
def test_round_trip_keeps_the_same_top_passages_and_close_distances(
    tmp_path: Path, fresh: sqlite3.Connection
) -> None:
    source = ingested(tmp_path / "source.db")
    try:
        export_prebuilt(source, ["horse", "duck"], MODEL, tmp_path / "out")
        before = {fighter: top(source, fighter) for fighter in TEXTS}
    finally:
        source.close()
    assert load_prebuilt(fresh, MODEL, tmp_path / "out").outcome is LoadOutcome.LOADED
    after = {fighter: top(fresh, fighter) for fighter in TEXTS}
    for fighter in TEXTS:
        assert [text for text, _ in after[fighter]] == [text for text, _ in before[fighter]]
        for (_, new), (_, old) in zip(after[fighter], before[fighter], strict=True):
            assert new == pytest.approx(old, abs=1e-3)


# Once rounded to float16, a load and a second export give back the very same files.
def test_loading_and_exporting_again_gives_the_same_bytes(
    tmp_path: Path, fresh: sqlite3.Connection
) -> None:
    assert load_prebuilt(fresh, MODEL, FIXTURE).outcome is LoadOutcome.LOADED
    export_prebuilt(fresh, ["horse", "duck"], MODEL, tmp_path / "again")
    assert files(tmp_path / "again") == files(FIXTURE)


def test_a_number_too_large_for_float16_is_refused() -> None:
    with pytest.raises(ValueError, match="too large for float16"):
        to_half(struct.pack("<2f", 0.5, 1e6))


def test_export_is_the_same_bytes_every_time_and_holds_no_model_name(tmp_path: Path) -> None:
    source = ingested(tmp_path / "source.db")
    try:
        export_prebuilt(source, ["horse", "duck"], MODEL, tmp_path / "a")
        export_prebuilt(source, ["duck", "horse"], MODEL, tmp_path / "b")
    finally:
        source.close()
    assert files(tmp_path / "a") == files(tmp_path / "b")
    manifest_bytes = (tmp_path / "a" / MANIFEST_FILE).read_bytes()
    assert MODEL.encode() not in manifest_bytes and b"\r\n" not in manifest_bytes
    assert json.loads(manifest_bytes)["embedding_model_sha256"] == model_fingerprint(MODEL)


def test_the_committed_fixture_matches_a_fresh_export(tmp_path: Path) -> None:
    source = ingested(tmp_path / "source.db")
    try:
        export_prebuilt(source, ["horse", "duck"], MODEL, tmp_path / "out")
    finally:
        source.close()
    assert files(tmp_path / "out") == files(FIXTURE)


def test_export_leaves_out_fighters_off_the_list(tmp_path: Path) -> None:
    source = ingested(tmp_path / "source.db")
    try:
        export_prebuilt(source, ["duck"], MODEL, tmp_path / "out")
    finally:
        source.close()
    manifest = json.loads((tmp_path / "out" / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert [d["fighter_id"] for d in manifest["documents"]] == ["duck"]


def test_a_knowledge_base_with_documents_is_never_overwritten(tmp_path: Path) -> None:
    own = ingested(tmp_path / "own.db", {"duck": TEXTS["duck"]})
    try:
        assert load_prebuilt(own, MODEL, FIXTURE).outcome is LoadOutcome.NOT_EMPTY
        assert own.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    finally:
        own.close()


def test_a_later_ingest_adds_to_the_prebuilt_passages_instead_of_replacing_them(
    fresh: sqlite3.Connection,
) -> None:
    load_prebuilt(fresh, MODEL, FIXTURE)
    before = fresh.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    async def later() -> tuple[bool, bool]:
        await ensure_vector_table(fresh, EMBEDDER)  # same size: keeps what is stored
        same = await store_document(fresh, record("horse", *TEXTS["horse"]), EMBEDDER)
        new = await store_document(
            fresh, record("cobra", "King cobra", "A king cobra is 4 m long."), EMBEDDER
        )
        return same, new

    same, new = asyncio.run(later())
    assert (same, new) == (False, True)  # the unchanged article is skipped by its content hash
    assert fresh.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == before + 1
    assert top(fresh, "horse") and top(fresh, "cobra")


def test_a_damaged_vectors_file_is_refused_and_leaves_the_database_empty(
    tmp_path: Path, fresh: sqlite3.Connection
) -> None:
    folder = tmp_path / "damaged"
    folder.mkdir()
    (folder / MANIFEST_FILE).write_bytes((FIXTURE / MANIFEST_FILE).read_bytes())
    vectors = bytearray((FIXTURE / "vectors-1.f16").read_bytes())
    vectors[0] ^= 0xFF
    (folder / "vectors-1.f16").write_bytes(bytes(vectors))
    with pytest.raises(ValueError, match="fingerprint"):
        load_prebuilt(fresh, MODEL, folder)
    (folder / "vectors-1.f16").write_bytes(bytes(vectors[:-4]))
    with pytest.raises(ValueError, match="one 8-number vector"):
        load_prebuilt(fresh, MODEL, folder)
    assert fresh.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


def test_a_missing_folder_is_reported_as_missing(fresh: sqlite3.Connection, tmp_path: Path) -> None:
    assert load_prebuilt(fresh, MODEL, tmp_path / "none").outcome is LoadOutcome.MISSING


# Split into small parts, the loader joins them back: same fingerprint, same search results.
def test_vectors_split_into_parts_load_the_same_as_one_file(
    tmp_path: Path, fresh: sqlite3.Connection
) -> None:
    source = ingested(tmp_path / "source.db")
    try:
        export_prebuilt(source, ["horse", "duck"], MODEL, tmp_path / "parts", part_bytes=24)
    finally:
        source.close()
    manifest = json.loads((tmp_path / "parts" / MANIFEST_FILE).read_text(encoding="utf-8"))
    whole = json.loads((FIXTURE / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["vector_files"] == ["vectors-1.f16", "vectors-2.f16", "vectors-3.f16"]
    assert manifest["vectors_sha256"] == whole["vectors_sha256"]
    joined = b"".join((tmp_path / "parts" / name).read_bytes() for name in manifest["vector_files"])
    assert joined == (FIXTURE / "vectors-1.f16").read_bytes()
    assert load_prebuilt(fresh, MODEL, tmp_path / "parts").outcome is LoadOutcome.LOADED
    assert top(fresh, "horse")


# A second, shorter export into the same folder leaves no stale last part behind.
def test_exporting_again_replaces_the_old_parts(tmp_path: Path) -> None:
    source = ingested(tmp_path / "source.db")
    try:
        export_prebuilt(source, ["horse", "duck"], MODEL, tmp_path / "out", part_bytes=24)
        export_prebuilt(source, ["horse", "duck"], MODEL, tmp_path / "out")
    finally:
        source.close()
    assert files(tmp_path / "out") == files(FIXTURE)


def test_a_missing_or_path_like_part_is_refused_and_leaves_the_database_empty(
    tmp_path: Path, fresh: sqlite3.Connection
) -> None:
    folder = tmp_path / "parts"
    source = ingested(tmp_path / "source.db")
    try:
        export_prebuilt(source, ["horse", "duck"], MODEL, folder, part_bytes=24)
    finally:
        source.close()
    (folder / "vectors-2.f16").unlink()
    with pytest.raises(ValueError, match="vectors-2.f16 is missing"):
        load_prebuilt(fresh, MODEL, folder)
    manifest = json.loads((folder / MANIFEST_FILE).read_text(encoding="utf-8"))
    manifest["vector_files"] = ["../vectors-1.f16"]
    (folder / MANIFEST_FILE).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected vectors file"):
        load_prebuilt(fresh, MODEL, folder)
    assert fresh.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


# The committed data: every file under the hook's 5 MiB limit, and the joined parts whole.
def test_the_committed_prebuilt_files_fit_the_hook_and_match_their_fingerprint() -> None:
    folder = REPO_ROOT / "data" / "prebuilt-kb"
    if not (folder / MANIFEST_FILE).is_file():
        pytest.skip("no prebuilt knowledge base in this checkout")
    assert PART_MAX_BYTES < 5 * 1024 * 1024
    assert all(path.stat().st_size <= 5 * 1024 * 1024 for path in folder.iterdir())
    manifest = json.loads((folder / MANIFEST_FILE).read_text(encoding="utf-8"))
    joined = b"".join((folder / name).read_bytes() for name in manifest["vector_files"])
    assert hashlib.sha256(joined).hexdigest() == manifest["vectors_sha256"]
    count = sum(len(document["chunks"]) for document in manifest["documents"])
    assert len(joined) == count * manifest["embedding_dim"] * 2
