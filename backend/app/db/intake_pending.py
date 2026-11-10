"""Clarifying questions waiting for an answer: saved on "clarify", taken once, gone in 30 min."""

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass

PENDING_TTL_SECONDS = 30 * 60


@dataclass(frozen=True)
class PendingQuestion:
    """What intake asked, and the text it was asked about."""

    original_text: str
    question: str
    options: list[str]


# Save a question and return the new pending_id the front end sends back with the answer.
def save_pending(
    connection: sqlite3.Connection, pending: PendingQuestion, now: float | None = None
) -> str:
    pending_id = f"p-{uuid.uuid4().hex[:12]}"
    connection.execute(
        "INSERT INTO intake_pending (pending_id, original_text, question, options, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            pending_id,
            pending.original_text,
            pending.question,
            json.dumps(pending.options),
            time.time() if now is None else now,
        ),
    )
    connection.commit()
    return pending_id


# Fetch and delete a question, so each id can be answered once; None if unknown or expired.
def take_pending(
    connection: sqlite3.Connection, pending_id: str, now: float | None = None
) -> PendingQuestion | None:
    cutoff = (time.time() if now is None else now) - PENDING_TTL_SECONDS
    connection.execute("DELETE FROM intake_pending WHERE created_at < ?", (cutoff,))
    row = connection.execute(
        "DELETE FROM intake_pending WHERE pending_id = ? "
        "RETURNING original_text, question, options",
        (pending_id,),
    ).fetchone()
    connection.commit()
    if row is None:
        return None
    return PendingQuestion(row["original_text"], row["question"], json.loads(row["options"]))
