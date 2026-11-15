-- Cached stat sheets (G04): one row per fighter and sheet version; the newest row wins.
-- The challenger (#203) reads sheet_json newest first by rowid, so rows are only ever inserted.

CREATE TABLE IF NOT EXISTS stat_sheets (
    fighter_id TEXT NOT NULL,
    sheet_hash TEXT NOT NULL,
    sheet_json TEXT NOT NULL, -- the whole StatSheet as JSON
    created_at TEXT NOT NULL, -- ISO 8601 (UTC), when the sheet was saved
    PRIMARY KEY (fighter_id, sheet_hash)
);
