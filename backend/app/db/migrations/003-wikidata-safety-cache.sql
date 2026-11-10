-- Safety: cached Wikidata name checks (A04 part 2). One row per lowercased name.
-- qid and label are NULL when Wikidata had no exact match; reason is NULL when not blocked.
-- Rows from an older classes_version are treated as misses. Failed lookups are never stored.

CREATE TABLE IF NOT EXISTS wikidata_safety_cache (
    query TEXT PRIMARY KEY,
    qid TEXT,
    label TEXT,
    reason TEXT,
    classes_version INTEGER NOT NULL,
    checked_at TEXT NOT NULL
);
