"""Export the seed fighters' knowledge base to committed files, and load them into an empty one.

A fresh setup can then skip the half-hour `npm run ingest` (D-66, #438). The files hold the
passages (chunks) and their vectors only: no article HTML, no model name, host, URL or key, and
no export time, so the same knowledge base always exports to the same bytes.

  knowledge-base.json  the documents and their passages, plus a manifest (format, vector size,
                       a SHA-256 fingerprint of the embedding model name, the vectors files'
                       names in order, and the SHA-256 of their joined bytes)
  vectors-1.f16, ...   one little-endian float16 vector per passage, in the JSON's order, split
                       into parts under 4.5 MiB so each stays under the pre-commit hook's 5 MB
                       limit (Mike, #438); the loader joins them. The database keeps float32;
                       half precision halves the size and leaves the retrieval ranking unchanged
                       (checked on the 15 retrieval cases, #438)
"""

import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from app.config import REPO_ROOT, get_settings
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.research.kb_store import SIZE_KEY
from app.research.seed_fighters import load_seed_fighters

PREBUILT_KB_DIR = REPO_ROOT / "data" / "prebuilt-kb"
MANIFEST_FILE = "knowledge-base.json"
VECTORS_GLOB = "vectors*.f16"  # every vectors file an export writes (and replaces)
FORMAT = 3
PART_MAX_BYTES = 9 * 512 * 1024  # 4.5 MiB: each part stays under the hook's 5 MiB file limit
FLOAT_BYTES = 4  # float32, as the database stores each vector
FILE_FLOAT_BYTES = 2  # float16, as the file stores it


class LoadOutcome(Enum):
    """What load_prebuilt did, so startup can say it in plain words."""

    LOADED = "loaded"
    MISSING = "missing"  # no prebuilt files (e.g. a checkout without them)
    NOT_EMPTY = "not_empty"  # the knowledge base already has documents: never overwritten
    MODEL_MISMATCH = "model_mismatch"  # built with another embedding model (or none is set)


@dataclass(frozen=True)
class LoadResult:
    """The outcome and how many documents and passages were loaded."""

    outcome: LoadOutcome
    documents: int = 0
    chunks: int = 0


# A fingerprint of the embedding model name, so the file never holds the name itself.
def model_fingerprint(model_name: str) -> str:
    return hashlib.sha256(model_name.strip().encode("utf-8")).hexdigest()


# Float32 vector bytes as float16 bytes (rounded to nearest); a value too big for float16 fails.
def to_half(blob: bytes) -> bytes:
    with np.errstate(over="ignore"):  # an overflow becomes inf, refused just below
        half = np.frombuffer(blob, dtype="<f4").astype("<f2")
    if not np.isfinite(half).all():
        raise ValueError("a vector holds a number too large for float16")
    return half.tobytes()


# Float16 vector bytes back as float32 bytes, the form the database stores.
def to_single(blob: bytes) -> bytes:
    return np.frombuffer(blob, dtype="<f2").astype("<f4").tobytes()


# Write the given fighters' documents, passages and vectors to folder; returns the passage count.
def export_prebuilt(
    connection: sqlite3.Connection,
    fighter_ids: list[str],
    model_name: str,
    folder: Path,
    part_bytes: int = PART_MAX_BYTES,
) -> int:
    if not model_name.strip():
        raise ValueError("no embedding model name is set, so the file can't record a fingerprint")
    size_row = connection.execute("SELECT value FROM kb_meta WHERE key = ?", (SIZE_KEY,)).fetchone()
    if size_row is None:
        raise ValueError("the knowledge base has no vector size; run `npm run ingest` first")
    size = int(size_row[0])
    documents, vectors = _collect(connection, sorted(set(fighter_ids)), size)
    _require_every_fighter(documents, fighter_ids)
    blob = to_half(b"".join(vectors))
    manifest = {
        "format": FORMAT,
        "vector_type": "float16",
        "embedding_dim": size,
        "embedding_model_sha256": model_fingerprint(model_name),
        "vectors_sha256": hashlib.sha256(blob).hexdigest(),
        "vector_files": write_vector_parts(blob, folder, part_bytes),
        "chunks": len(vectors),
        "documents": documents,
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    (folder / MANIFEST_FILE).write_bytes(text.encode("utf-8"))  # bytes: LF on every OS
    return len(vectors)


# Refuse a partial export: every requested fighter must have at least one document.
def _require_every_fighter(documents: list[dict[str, Any]], fighter_ids: list[str]) -> None:
    missing = sorted(set(fighter_ids) - {document["fighter_id"] for document in documents})
    if missing:
        raise ValueError(
            f"no passages for {', '.join(missing)}; run "
            "`uv run --directory backend python -m scripts.ingest_seed --refresh` first"
        )


# Replace folder's vectors files with blob cut into numbered parts; returns their names in order.
def write_vector_parts(blob: bytes, folder: Path, part_bytes: int = PART_MAX_BYTES) -> list[str]:
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(VECTORS_GLOB):  # a shorter export must not leave a stale last part
        old.unlink()
    names: list[str] = []
    for index, start in enumerate(range(0, max(len(blob), 1), part_bytes), start=1):
        name = f"vectors-{index}.f16"
        (folder / name).write_bytes(blob[start : start + part_bytes])
        names.append(name)
    return names


# The documents (sorted by id) with their passages in order, and each passage's vector bytes.
def _collect(
    connection: sqlite3.Connection, fighter_ids: list[str], size: int
) -> tuple[list[dict[str, Any]], list[bytes]]:
    documents: list[dict[str, Any]] = []
    vectors: list[bytes] = []
    marks = ",".join("?" * len(fighter_ids))
    rows = connection.execute(
        "SELECT doc_id, fighter_id, source, title, url, license, retrieved_at, content_hash "
        f"FROM documents WHERE fighter_id IN ({marks}) ORDER BY doc_id",
        fighter_ids,
    ).fetchall()
    for row in rows:
        chunks = connection.execute(
            "SELECT c.ordinal, c.heading, c.text, v.embedding FROM chunks AS c "
            "JOIN chunks_vec AS v ON v.chunk_id = c.chunk_id WHERE c.doc_id = ? ORDER BY c.ordinal",
            (row[0],),
        ).fetchall()
        for chunk in chunks:
            if len(chunk[3]) != size * FLOAT_BYTES:
                raise ValueError(f"a passage of {row[0]} has a vector of the wrong size")
            vectors.append(bytes(chunk[3]))
        keys = ("doc_id", "fighter_id", "source", "title", "url", "license", "retrieved_at")
        document: dict[str, Any] = dict(zip(keys, row[:7], strict=True))
        document["content_hash"] = row[7]
        document["chunks"] = [{"ordinal": c[0], "heading": c[1], "text": c[2]} for c in chunks]
        documents.append(document)
    return documents, vectors


# Load the prebuilt files into an empty knowledge base, if they match this setup's model.
def load_prebuilt(
    connection: sqlite3.Connection, model_name: str, folder: Path = PREBUILT_KB_DIR
) -> LoadResult:
    if not (folder / MANIFEST_FILE).is_file():
        return LoadResult(LoadOutcome.MISSING)
    if connection.execute("SELECT 1 FROM documents LIMIT 1").fetchone() is not None:
        return LoadResult(LoadOutcome.NOT_EMPTY)
    manifest = json.loads((folder / MANIFEST_FILE).read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT:
        raise ValueError(f"{MANIFEST_FILE} is format {manifest.get('format')}, expected {FORMAT}")
    if not model_name.strip() or manifest["embedding_model_sha256"] != model_fingerprint(
        model_name
    ):
        return LoadResult(LoadOutcome.MODEL_MISMATCH)
    size = int(manifest["embedding_dim"])
    blob = _read_vector_parts(manifest, folder)
    _check_vectors(manifest, blob, size)
    _store(connection, manifest["documents"], to_single(blob), size)
    return LoadResult(LoadOutcome.LOADED, len(manifest["documents"]), int(manifest["chunks"]))


# The manifest's vectors files, read in order and joined; a missing or path-like name is refused.
def _read_vector_parts(manifest: dict[str, Any], folder: Path) -> bytes:
    names = manifest.get("vector_files")
    if not isinstance(names, list) or not names:
        raise ValueError(f"{MANIFEST_FILE} doesn't list its vectors files")
    parts: list[bytes] = []
    for name in names:
        if not isinstance(name, str) or Path(name).name != name or not name.endswith(".f16"):
            raise ValueError(f"{MANIFEST_FILE} names an unexpected vectors file: {name!r}")
        if not (folder / name).is_file():
            raise ValueError(f"the vectors file {name} is missing from {folder.name}/")
        parts.append((folder / name).read_bytes())
    return b"".join(parts)


# The joined vectors must be whole, unchanged, and hold one vector per passage.
def _check_vectors(manifest: dict[str, Any], blob: bytes, size: int) -> None:
    count = sum(len(document["chunks"]) for document in manifest["documents"])
    if count != manifest["chunks"] or len(blob) != count * size * FILE_FLOAT_BYTES:
        raise ValueError(f"the vectors files don't hold one {size}-number vector per passage")
    if hashlib.sha256(blob).hexdigest() != manifest["vectors_sha256"]:
        raise ValueError(f"the vectors files don't match the fingerprint in {MANIFEST_FILE}")


# Write everything in one transaction, so a failure leaves the knowledge base empty.
def _store(
    connection: sqlite3.Connection, documents: list[dict[str, Any]], blob: bytes, size: int
) -> None:
    step = size * FLOAT_BYTES
    offset = 0
    with connection:
        # An explicit BEGIN, under sqlite3's default transaction handling, makes the vector-table
        # DROP/CREATE roll back with the inserts; changing isolation_level would break that.
        connection.execute("BEGIN")
        connection.execute("DROP TABLE IF EXISTS chunks_vec")
        connection.execute(
            f"CREATE VIRTUAL TABLE chunks_vec USING vec0("
            f"chunk_id INTEGER PRIMARY KEY, embedding FLOAT[{size}])"
        )
        connection.execute(
            "INSERT OR REPLACE INTO kb_meta (key, value) VALUES (?, ?)", (SIZE_KEY, str(size))
        )
        for document in documents:
            _insert_document(connection, document)
            for chunk in document["chunks"]:
                cursor = connection.execute(
                    "INSERT INTO chunks (doc_id, ordinal, heading, text) VALUES (?, ?, ?, ?)",
                    (document["doc_id"], chunk["ordinal"], chunk["heading"], chunk["text"]),
                )
                connection.execute(
                    "INSERT INTO chunks_vec (chunk_id, embedding) VALUES (?, ?)",
                    (cursor.lastrowid, blob[offset : offset + step]),
                )
                offset += step


# Store a document row. Its text is its passages joined, since the article itself isn't shipped:
# every quote taken from a passage is still found in it (the trace's quote check).
def _insert_document(connection: sqlite3.Connection, document: dict[str, Any]) -> None:
    text = "\n\n".join(chunk["text"] for chunk in document["chunks"])
    connection.execute(
        "INSERT INTO documents (doc_id, fighter_id, source, title, url, license, "
        "retrieved_at, raw_text, content_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            document["doc_id"],
            document["fighter_id"],
            document["source"],
            document["title"],
            document["url"],
            document["license"],
            document["retrieved_at"],
            text,
            document["content_hash"],
        ),
    )


# Export the configured database's seed-fighter passages to data/prebuilt-kb/ (D-66).
# From the backend folder, after a full live `npm run ingest`:
#   uv run python -m app.research.kb_prebuilt
# Run it rarely (only when the seed list or embedding model changes): each re-export adds about
# 16 MB to the git history.
def main(folder: Path = PREBUILT_KB_DIR) -> int:
    settings = get_settings()
    connection = connect(settings.data_dir / "app.db")
    try:
        apply_migrations(connection)
        ids = [fighter.id for fighter in load_seed_fighters()]
        count = export_prebuilt(connection, ids, settings.embeddings_model, folder)
    except ValueError as error:
        print(f"Nothing was exported: {error}", file=sys.stderr)
        return 2
    finally:
        connection.close()
    print(f"Exported {count} passages for {len(ids)} seed fighters to {folder}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
