"""Battle routes (ARCHITECTURE §6): start a battle, read its record, and follow it live (A05)."""

import json
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.intake import UNAVAILABLE_MESSAGE, within_deadline
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.db.showcase import SHOWCASE_DIR, showcase_rows
from app.models.api import BattleCreated, ShowcaseBattle
from app.models.battle import BattleRecord
from app.models.matchup import IntakeResult, Matchup
from app.pipeline.orchestrator import start_battle
from app.pipeline.store import BattleStore, battle_store
from app.providers.base import ChatLLM
from app.providers.registry import get_intake_chat
from app.safety import SafetyUnavailable, blocked_result, check_matchup
from app.safety.wikidata import WikidataLookup, get_lookup

router = APIRouter(prefix="/api/battles", tags=["battles"])
NOT_FOUND = "We couldn't find that battle."
# Headers that stop browsers and proxies from holding back live updates.
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


# The store that holds battles; tests swap in a fresh one.
def get_store() -> BattleStore:
    return battle_store


Store = Annotated[BattleStore, Depends(get_store)]


# The chat model the safety classifier uses (intake's, short timeout); tests swap in a stand-in.
def get_safety_chat() -> ChatLLM:
    return get_intake_chat()


# The Wikidata lookup for the safety name check (mock or live); tests swap in a stand-in.
def get_wikidata_lookup() -> WikidataLookup:
    return get_lookup()


SafetyChat = Annotated[ChatLLM, Depends(get_safety_chat)]
Lookup = Annotated[WikidataLookup, Depends(get_wikidata_lookup)]
BLOCKED_STATUS = 403
BLOCKED_RESPONSES: dict[int | str, dict[str, Any]] = {
    BLOCKED_STATUS: {"model": IntakeResult, "description": "Blocked by the safety gate."},
    503: {"description": "The safety check is unavailable; no battle was started."},
}


# Start a battle for a matchup that passes the safety gate; it runs in the background. A blocked
# matchup gets intake's blocked IntakeResult (403) and reaches no research or media provider.
@router.post("", status_code=202, response_model=BattleCreated, responses=BLOCKED_RESPONSES)
async def create_battle(
    matchup: Matchup, store: Store, chat: SafetyChat, lookup: Lookup
) -> BattleCreated | JSONResponse:
    try:
        verdict = await within_deadline(
            lambda: check_matchup(matchup, chat=chat, wikidata_lookup=lookup)
        )
    except SafetyUnavailable as error:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE) from error
    if not verdict.allowed:
        blocked_body = blocked_result(verdict).model_dump(mode="json")
        return JSONResponse(status_code=BLOCKED_STATUS, content=blocked_body)
    return BattleCreated(battle_id=await start_battle(matchup, store))


# The app database with migrations applied; async so it opens on the thread that uses it.
async def get_db() -> AsyncIterator[sqlite3.Connection]:
    connection = connect()
    try:
        apply_migrations(connection)
        yield connection
    finally:
        connection.close()


Db = Annotated[sqlite3.Connection, Depends(get_db)]
ONLY_SHOWCASE = "Only the showcase list is available here: add ?showcase=true."


# Where the showcase lives; tests point it at their own folder.
def get_showcase_dir() -> Path:
    return SHOWCASE_DIR


ShowcaseDir = Annotated[Path, Depends(get_showcase_dir)]


# The saved showcase battles for the home page, in their planned order (G08).
@router.get("", response_model=list[ShowcaseBattle])
async def list_battles(
    db: Db, showcase_dir: ShowcaseDir, showcase: Annotated[bool, Query()] = False
) -> list[ShowcaseBattle]:
    if not showcase:
        raise HTTPException(status_code=404, detail=ONLY_SHOWCASE)
    return showcase_rows(db, showcase_dir)


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
