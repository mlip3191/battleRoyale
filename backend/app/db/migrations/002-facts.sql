-- Structured facts about fighters, such as a body mass from Wikidata (G02).
-- Every row says where it came from, so G04 can cite it.

CREATE TABLE facts (
    fact_id INTEGER PRIMARY KEY,
    fighter_id TEXT NOT NULL,
    source TEXT NOT NULL,
    field TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    reference TEXT NOT NULL,
    license TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    UNIQUE (fighter_id, source, field, reference),
    CHECK (source <> '' AND field <> '' AND unit <> '' AND reference <> '')
);

CREATE INDEX facts_by_fighter ON facts (fighter_id);
