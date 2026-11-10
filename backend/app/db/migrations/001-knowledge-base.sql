-- Knowledge base: downloaded documents and the passages cut from them (G02).
-- The chunks_vec vector table is created in code, because its size depends on the embedding model.

CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY,
    fighter_id TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    license TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    content_hash TEXT NOT NULL
);

CREATE INDEX documents_by_fighter ON documents (fighter_id);

CREATE TABLE chunks (
    chunk_id INTEGER PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    heading TEXT,
    text TEXT NOT NULL,
    UNIQUE (doc_id, ordinal)
);

CREATE TABLE kb_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
