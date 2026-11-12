"""Battle routes (ARCHITECTURE §6): start a battle, read its record, and follow it live (A05)."""

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.models.api import BattleCreated
from app.models.battle import BattleRecord
from app.models.matchup import Matchup
from app.pipeline.orchestrator import start_battle
from app.pipeline.store import BattleStore, battle_store

router = APIRouter(prefix="/api/battles", tags=["battles"])
NOT_FOUND = "We couldn't find that battle."
# Headers that stop browsers and proxies from holding back live updates.
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


# The store that holds battles; tests swap in a fresh one.
def get_store() -> BattleStore:
    return battle_store


Store = Annotated[BattleStore, Depends(get_store)]


# Start a battle for a confirmed matchup; it runs in the background.
# TODO(A05): this route trusts that the matchup was confirmed by intake. Once real research
# lands, re-run the safety gate here; today it is safe only because fighters resolve from seed
# sheets alone.
@router.post("", status_code=202, response_model=BattleCreated)
async def create_battle(matchup: Matchup, store: Store) -> BattleCreated:
    return BattleCreated(battle_id=await start_battle(matchup, store))


# The battle as it stands now (partial while it is still running).
@router.get("/{battle_id}", response_model=BattleRecord)
async def read_battle(battle_id: str, store: Store) -> BattleRecord:
    record = await store.get(battle_id)
    if record is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return record


# Live progress: a "stage" event per stage change, then one "end" event when the battle stops.
@router.get("/{battle_id}/events")
async def battle_events(battle_id: str, store: Store) -> StreamingResponse:
    if await store.get(battle_id) is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return StreamingResponse(
        _event_stream(battle_id, store), media_type="text/event-stream", headers=SSE_HEADERS
    )


# Format the battle's stage changes as Server-Sent Events.
async def _event_stream(battle_id: str, store: BattleStore) -> AsyncIterator[str]:
    async for change in store.follow(battle_id):
        yield f"event: stage\ndata: {change.model_dump_json()}\n\n"
    record = await store.get(battle_id)
    status = record.status if record else "failed"
    yield f"event: end\ndata: {json.dumps({'status': status})}\n\n"
