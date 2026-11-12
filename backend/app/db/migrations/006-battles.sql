-- Saved battles (A05): the durable copy of every BattleRecord, plus the repeat-battle cache key.
-- Numbered 006 on purpose: 003-005 are claimed by the on-hold A04 stack.

CREATE TABLE IF NOT EXISTS battles (
    battle_id TEXT PRIMARY KEY,
    cache_key TEXT, -- NULL until research finishes; same key = same matchup, sheets, engine
    status TEXT NOT NULL, -- running, done, or failed
    created_at TEXT NOT NULL, -- ISO 8601 (UTC), when the battle was requested
    record_json TEXT NOT NULL -- the whole BattleRecord as JSON
);

CREATE INDEX IF NOT EXISTS battles_cache_key ON battles (cache_key);
