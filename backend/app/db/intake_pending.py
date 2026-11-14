"""Clarifying questions waiting for an answer: saved on "clarify", taken once, gone in 30 min."""

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass

PENDING_TTL_SECONDS = 30 * 60
MAX_QUESTION_CHARS = 500
MAX_ORIGINAL_CHARS = 500  # the parser refuses longer text, so nothing past this is ever read


@dataclass(frozen=True)
class PendingQuestion:
    """What intake asked, and the text it was asked about."""

    original_text: str
    question: str
    options: list[str]
    created_at: float | None = None  # set when read back, so a restored question keeps its age


# Drop questions older than 30 minutes, so the table never grows without bound.
def _purge_expired(connection: sqlite3.Connection, now: float) -> None:
    connection.execute(
        "DELETE FROM intake_pending WHERE created_at < ?", (now - PENDING_TTL_SECONDS,)
    )


# Save a question and return the new pending_id the front end sends back with the answer.
def save_pending(
    connection: sqlite3.Connection, pending: PendingQuestion, now: float | None = None
) -> str:
    now = time.time() if now is None else now
    _purge_expired(connection, now)
    pending_id = f"p-{uuid.uuid4().hex}"
    connection.execute(
        "INSERT INTO intake_pending (pending_id, original_text, question, options, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            pending_id,
            pending.original_text[:MAX_ORIGINAL_CHARS],
            pending.question[:MAX_QUESTION_CHARS],
            json.dumps(pending.options),
            now,
        ),
    )
    connection.commit()
    return pending_id


# Fetch and delete a question, so each id can be answered once; None if unknown or expired.
def take_pending(
    connection: sqlite3.Connection, pending_id: str, now: float | None = None
) -> PendingQuestion | None:
    _purge_expired(connection, time.time() if now is None else now)
    row = connection.execute(
        "DELETE FROM intake_pending WHERE pending_id = ? "
        "RETURNING original_text, question, options, created_at",
        (pending_id,),
    ).fetchone()
    connection.commit()
    if row is None:
        return None
    options = json.loads(row["options"])
    return PendingQuestion(row["original_text"], row["question"], options, row["created_at"])


# Put a taken question back under the same id and age (the model was down), so a retry works.
def restore_pending(
    connection: sqlite3.Connection, pending_id: str, pending: PendingQuestion
) -> None:
    created_at = time.time() if pending.created_at is None else pending.created_at
    connection.execute(
        "INSERT OR IGNORE INTO intake_pending "
        "(pending_id, original_text, question, options, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            pending_id,
            pending.original_text[:MAX_ORIGINAL_CHARS],
            pending.question[:MAX_QUESTION_CHARS],
            json.dumps(pending.options),
            created_at,
        ),
    )
    connection.commit()
