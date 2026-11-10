"""Store documents, their passages, and passage vectors in the knowledge base."""

import hashlib
import sqlite3
from dataclasses import dataclass

import sqlite_vec

from app.providers.base import Embedder
from app.research.chunking import chunk_text

SIZE_PROBE = "embedding size probe"
SIZE_KEY = "embedding_dim"


@dataclass(frozen=True)
class DocumentRecord:
    """A parsed document ready to store."""

    doc_id: str
    fighter_id: str
    source: str
    title: str
    url: str
    license: str
    retrieved_at: str
    text: str


# A hash of the text, used to skip documents that have not changed.
def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Make chunks_vec match the embedder's vector size; a new size clears the old passages.
async def ensure_vector_table(connection: sqlite3.Connection, embedder: Embedder) -> int:
    size = len((await embedder.embed([SIZE_PROBE]))[0])
    row = connection.execute("SELECT value FROM kb_meta WHERE key = ?", (SIZE_KEY,)).fetchone()
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chunks_vec'"
    ).fetchone()
    if row is not None and table is not None and int(row[0]) == size:
        return size
    with connection:
        connection.execute("BEGIN")  # table changes join the transaction only if it is explicit
        connection.execute("DROP TABLE IF EXISTS chunks_vec")
        connection.execute("DELETE FROM documents")
        connection.execute(
            f"CREATE VIRTUAL TABLE chunks_vec USING vec0("
            f"chunk_id INTEGER PRIMARY KEY, embedding FLOAT[{size}])"
        )
        connection.execute(
            "INSERT OR REPLACE INTO kb_meta (key, value) VALUES (?, ?)", (SIZE_KEY, str(size))
        )
    return size


# Store a document and its passages; returns False if the same text is already stored.
async def store_document(
    connection: sqlite3.Connection, record: DocumentRecord, embedder: Embedder
) -> bool:
    digest = content_hash(record.text)
    row = connection.execute(
        "SELECT content_hash FROM documents WHERE doc_id = ?", (record.doc_id,)
    ).fetchone()
    if row is not None and row[0] == digest:
        return False
    chunks = chunk_text(record.text)
    vectors = await embedder.embed([chunk.text for chunk in chunks]) if chunks else []
    if len(vectors) != len(chunks):
        raise ValueError(f"expected {len(chunks)} vectors, got {len(vectors)}")
    with connection:
        _delete_document(connection, record.doc_id)
        connection.execute(
            "INSERT INTO documents (doc_id, fighter_id, source, title, url, license, "
            "retrieved_at, raw_text, content_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.doc_id,
                record.fighter_id,
                record.source,
                record.title,
                record.url,
                record.license,
                record.retrieved_at,
                record.text,
                digest,
            ),
        )
        for chunk, vector in zip(chunks, vectors, strict=True):
            cursor = connection.execute(
                "INSERT INTO chunks (doc_id, ordinal, heading, text) VALUES (?, ?, ?, ?)",
                (record.doc_id, chunk.ordinal, chunk.heading, chunk.text),
            )
            connection.execute(
                "INSERT INTO chunks_vec (chunk_id, embedding) VALUES (?, ?)",
                (cursor.lastrowid, sqlite_vec.serialize_float32(vector)),
            )
    return True


# Remove a document's vectors, then the document (its passages follow by cascade).
def _delete_document(connection: sqlite3.Connection, doc_id: str) -> None:
    connection.execute(
        "DELETE FROM chunks_vec WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE doc_id = ?)",
        (doc_id,),
    )
    connection.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
