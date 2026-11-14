"""Saved battles: the durable copy of each BattleRecord, and the lookup behind the repeat cache."""

import sqlite3

from app.models.battle import BattleRecord


# Insert or replace the battle's row with its latest record (and cache key, once known).
def save(connection: sqlite3.Connection, record: BattleRecord, cache_key: str | None) -> None:
    connection.execute(
        "INSERT INTO battles (battle_id, cache_key, status, created_at, record_json) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (battle_id) DO UPDATE SET cache_key = excluded.cache_key, "
        "status = excluded.status, record_json = excluded.record_json",
        (
            record.battle_id,
            cache_key,
            record.status,
            record.created_at.isoformat(),
            record.model_dump_json(),
        ),
    )
    connection.commit()


# The saved record for an id, or None if it was never saved.
def get(connection: sqlite3.Connection, battle_id: str) -> BattleRecord | None:
    row = connection.execute(
        "SELECT record_json FROM battles WHERE battle_id = ?", (battle_id,)
    ).fetchone()
    return None if row is None else BattleRecord.model_validate_json(row["record_json"])


INTERRUPTED = "Interrupted by a server restart."


# Mark every battle saved as still running (or pending) "failed", with each unfinished stage
# "failed" too; nothing can finish them after a restart. Returns how many were marked.
def fail_interrupted(connection: sqlite3.Connection) -> int:
    rows = connection.execute(
        "SELECT record_json, cache_key FROM battles WHERE status IN ('running', 'pending')"
    ).fetchall()
    for row in rows:
        record = BattleRecord.model_validate_json(row["record_json"])
        stages = [
            s.model_copy(update={"status": "failed", "detail": INTERRUPTED})
            if s.status in ("running", "pending")
            else s
            for s in record.stages
        ]
        failed = record.model_copy(update={"stages": stages, "status": "failed"})
        save(connection, failed, row["cache_key"])
    return len(rows)


# The newest finished ("done") battle with this cache key, or None.
def find_done_by_cache_key(connection: sqlite3.Connection, cache_key: str) -> BattleRecord | None:
    row = connection.execute(
        "SELECT record_json FROM battles WHERE cache_key = ? AND status = 'done' "
        "ORDER BY created_at DESC, rowid DESC LIMIT 1",
        (cache_key,),
    ).fetchone()
    return None if row is None else BattleRecord.model_validate_json(row["record_json"])
