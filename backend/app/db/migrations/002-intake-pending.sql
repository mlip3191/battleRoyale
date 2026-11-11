-- Clarifying questions waiting for the user's answer (D08). Rows expire after 30 minutes.

CREATE TABLE intake_pending (
    pending_id TEXT PRIMARY KEY,
    original_text TEXT NOT NULL,
    question TEXT NOT NULL,
    options TEXT NOT NULL, -- JSON list of the suggested answers
    created_at REAL NOT NULL -- seconds since 1970 (UTC)
);
