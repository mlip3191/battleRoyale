"""In-memory battle records and their stage-change history, safe to share between tasks.

Every read hands back a copy, and every change happens under the battle's own lock, so two
battles running at once can never see or change each other's record.
Memory feeds the live event streams. A persistent store also saves every change to the
`battles` table (ARCHITECTURE §8), so a battle can still be read after a restart and a repeat
battle can reuse a finished one. A database error is logged and never stops a battle.
Note: finished battles are never evicted from memory, so this store grows until restart.
"""

import asyncio
import logging
import secrets
import sqlite3
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

from app.db import battles as saved
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.battle import BattleRecord, StageStatus
from app.models.matchup import Matchup
from app.models.media import Asset

logger = logging.getLogger(__name__)

# Every stage, in ARCHITECTURE §4 order (taken from the contract so they never drift apart).
STAGES: tuple[str, ...] = get_args(StageStatus.model_fields["stage"].annotation)
# How long a database step waits for another writer's lock before giving up.
BUSY_TIMEOUT_MS = 200


class BattleStore:
    """Battle records keyed by battle_id, plus each battle's stage changes in order.

    persist=True saves to the app database (or `db_path`); the default keeps memory only.
    """

    def __init__(self, *, persist: bool = False, db_path: Path | None = None) -> None:
        self._records: dict[str, BattleRecord] = {}
        self._changes: dict[str, list[StageStatus]] = {}
        self._signals: dict[str, asyncio.Condition] = {}
        self._cache_keys: dict[str, str] = {}
        self._persist = persist or db_path is not None
        self._db_path = db_path
        self._db: sqlite3.Connection | None = None
        self._recovered = False  # interrupted battles marked failed (done once per store)

    # The open database (migrated on first use); used only on the event loop's thread.
    # The first time it opens, battles a restart left "running" are marked failed.
    def _connection(self) -> sqlite3.Connection:
        if self._db is None:
            connection = connect(self._db_path)
            try:
                # Calls run on the event loop, so wait for a lock only briefly; a save that
                # misses heals itself, because the next save writes the whole record again.
                connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
                apply_migrations(connection)
                if not self._recovered:
                    saved.fail_interrupted(connection)
                    self._recovered = True
            except Exception:
                connection.close()
                raise
            self._db = connection
        return self._db

    # Run one database step; on any error log only its class name, drop the connection, and
    # hand back None, so the battle carries on from memory.
    def _try_db[T](self, action: str, step: Callable[[sqlite3.Connection], T]) -> T | None:
        if not self._persist:
            return None
        try:
            return step(self._connection())
        except Exception as error:
            logger.warning("battle store: could not %s (%s)", action, type(error).__name__)
            self._close()
            return None

    # Close the database connection, if open; it reopens on the next step.
    def _close(self) -> None:
        connection, self._db = self._db, None
        if connection is not None:
            try:
                connection.close()
            except Exception:  # already broken; nothing more to do
                pass

    # Save the battle's current record as its durable copy (called after every change).
    def _save(self, battle_id: str) -> None:
        record, key = self._records[battle_id], self._cache_keys.get(battle_id)
        self._try_db("save a battle", lambda db: saved.save(db, record, key))

    # Remember the battle's cache key (known once research is done) and save it with the record.
    async def set_cache_key(self, battle_id: str, cache_key: str) -> None:
        async with self._signals[battle_id]:
            self._cache_keys[battle_id] = cache_key
            self._save(battle_id)

    # The newest finished battle saved under this cache key, or None (also when memory-only).
    async def find_cached(self, cache_key: str) -> BattleRecord | None:
        return self._try_db(
            "read the cache", lambda db: saved.find_done_by_cache_key(db, cache_key)
        )

    # Save a new battle with every stage pending and hand back a copy of it.
    async def create(self, matchup: Matchup) -> BattleRecord:
        battle_id = f"b-{secrets.token_hex(4)}"
        while battle_id in self._records:
            battle_id = f"b-{secrets.token_hex(4)}"
        record = BattleRecord(
            battle_id=battle_id,
            created_at=datetime.now(UTC),
            matchup=matchup.model_copy(deep=True),
            stages=[StageStatus.model_validate({"stage": s, "status": "pending"}) for s in STAGES],
            status="running",
        )
        self._records[battle_id] = record
        self._changes[battle_id] = []
        self._signals[battle_id] = asyncio.Condition()
        self._save(battle_id)
        return record.model_copy(deep=True)

    # A copy of the battle's current record; the saved copy if it isn't in memory (e.g. after
    # a restart); None for an unknown id.
    async def get(self, battle_id: str) -> BattleRecord | None:
        record = self._records.get(battle_id)
        if record is None:
            return self._try_db("read a battle", lambda db: saved.get(db, battle_id))
        return record.model_copy(deep=True)

    # A copy of every stage change so far, oldest first.
    async def changes(self, battle_id: str) -> list[StageStatus]:
        return [change.model_copy() for change in self._changes.get(battle_id, [])]

    # Record one stage change and wake anyone following the battle.
    async def set_stage(
        self, battle_id: str, stage: str, status: str, detail: str | None = None
    ) -> None:
        change = StageStatus.model_validate({"stage": stage, "status": status, "detail": detail})
        signal = self._signals[battle_id]
        async with signal:
            record = self._records[battle_id]
            stages = [change if s.stage == stage else s for s in record.stages]
            self._records[battle_id] = record.model_copy(update={"stages": stages})
            self._changes[battle_id].append(change)
            self._save(battle_id)
            signal.notify_all()

    # Fill in record fields (stat_sheets, result, status, ...) and wake anyone following.
    async def update(self, battle_id: str, **fields: Any) -> None:
        signal = self._signals[battle_id]
        async with signal:
            record = self._records[battle_id]
            data = record.model_dump() | fields
            self._records[battle_id] = BattleRecord.model_validate(data)
            self._save(battle_id)
            signal.notify_all()

    # Add media assets to the record; several stages add theirs at the same time.
    async def add_assets(self, battle_id: str, assets: list[Asset]) -> None:
        signal = self._signals[battle_id]
        async with signal:
            record = self._records[battle_id]
            added = [asset.model_copy() for asset in assets]
            self._records[battle_id] = record.model_copy(update={"assets": record.assets + added})
            self._save(battle_id)
            signal.notify_all()

    # Yield each stage change as it happens (earlier ones first); stop once the battle ends.
    # A battle known only from the database replays its saved stages once.
    async def follow(self, battle_id: str) -> AsyncIterator[StageStatus]:
        if battle_id not in self._signals:
            record = await self.get(battle_id)
            for change in record.stages if record else []:
                yield change
            return
        signal = self._signals[battle_id]
        seen = 0
        while True:
            async with signal:
                await signal.wait_for(lambda count=seen: self._has_news(battle_id, count))
                new = self._changes[battle_id][seen:]
                seen += len(new)
                ended = self._records[battle_id].status != "running"
            for change in new:
                yield change.model_copy()
            if ended:
                return

    # True when there are changes past the first `seen`, or the battle has ended.
    def _has_news(self, battle_id: str, seen: int) -> bool:
        return len(self._changes[battle_id]) > seen or self._records[battle_id].status != "running"


# The store the app uses (saved to data/app.db); tests swap in a fresh one through the
# router's dependency.
battle_store = BattleStore(persist=True)
