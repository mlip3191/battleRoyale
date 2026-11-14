"""Fighter routes (ARCHITECTURE §6, G04): search fighters, and read a fighter's stat sheet.

Both only read what exists (seed sheets and sheets cached by earlier battles); neither starts
research, so they answer fast. Research happens in a battle's research stage.
"""

import sqlite3
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.api import FighterMatch
from app.models.stats import StatSheet
from app.research.seed_fighters import find_seed_sheet
from app.research.sheet_store import cached_sheet, search_fighters

router = APIRouter(prefix="/api/fighters", tags=["fighters"])
NOT_FOUND = "We don't have a stat sheet for that fighter yet."


# The app database with migrations applied; async so it opens on the thread that uses it.
async def get_db() -> AsyncIterator[sqlite3.Connection]:
    connection = connect()
    try:
        apply_migrations(connection)
        yield connection
    finally:
        connection.close()


Db = Annotated[sqlite3.Connection, Depends(get_db)]


# Fighters whose name contains the search text, with whether a sheet is ready.
@router.get("", response_model=list[FighterMatch])
async def find_fighters(
    db: Db, q: Annotated[str, Query(min_length=1, max_length=100)]
) -> list[FighterMatch]:
    return search_fighters(db, q)


# A fighter's stat sheet: the hand-verified seed sheet, else the newest cached one.
@router.get("/{fighter_id}", response_model=StatSheet)
async def read_fighter(fighter_id: str, db: Db) -> StatSheet:
    sheet = find_seed_sheet(fighter_id) or cached_sheet(db, fighter_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return sheet
