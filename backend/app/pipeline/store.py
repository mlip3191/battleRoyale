"""In-memory battle records and their stage-change history, safe to share between tasks.

Every read hands back a copy, and every change happens under the battle's own lock, so two
battles running at once can never see or change each other's record.
TODO(A05): save records to the `battles` table (ARCHITECTURE §8) instead of memory.
Note: finished battles are never evicted from memory, so this store grows until restart.
"""

import asyncio
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, get_args

from app.models.battle import BattleRecord, StageStatus
from app.models.matchup import Matchup
from app.models.media import Asset

# Every stage, in ARCHITECTURE §4 order (taken from the contract so they never drift apart).
STAGES: tuple[str, ...] = get_args(StageStatus.model_fields["stage"].annotation)


class BattleStore:
    """Battle records keyed by battle_id, plus each battle's stage changes in order."""

    def __init__(self) -> None:
        self._records: dict[str, BattleRecord] = {}
        self._changes: dict[str, list[StageStatus]] = {}
        self._signals: dict[str, asyncio.Condition] = {}

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
        return record.model_copy(deep=True)

    # A copy of the battle's current record, or None for an unknown id.
    async def get(self, battle_id: str) -> BattleRecord | None:
        record = self._records.get(battle_id)
        return None if record is None else record.model_copy(deep=True)

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
            signal.notify_all()

    # Fill in record fields (stat_sheets, result, status, ...) and wake anyone following.
    async def update(self, battle_id: str, **fields: Any) -> None:
        signal = self._signals[battle_id]
        async with signal:
            record = self._records[battle_id]
            data = record.model_dump() | fields
            self._records[battle_id] = BattleRecord.model_validate(data)
            signal.notify_all()

    # Add media assets to the record; several stages add theirs at the same time.
    async def add_assets(self, battle_id: str, assets: list[Asset]) -> None:
        signal = self._signals[battle_id]
        async with signal:
            record = self._records[battle_id]
            added = [asset.model_copy() for asset in assets]
            self._records[battle_id] = record.model_copy(update={"assets": record.assets + added})
            signal.notify_all()

    # Yield each stage change as it happens (earlier ones first); stop once the battle ends.
    async def follow(self, battle_id: str) -> AsyncIterator[StageStatus]:
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


# The store the app uses; tests swap in a fresh one through the router's dependency.
battle_store = BattleStore()
