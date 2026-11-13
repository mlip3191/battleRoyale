"""Find a fighter's stat sheet for a battle, and cache built sheets (G04 part 3).

Order: the hand-verified seed sheet, then a sheet cached for an earlier battle, then a new
sheet built from stored facts and model extraction for a seed-list fighter, which is saved so
repeat battles reuse the same sheet (and the same simulation seed). Mythical fighters and
names off the seed list get None until G09 researches new fighters on demand.
"""

import asyncio
import logging
import sqlite3
from datetime import UTC, datetime

from pydantic import ValidationError

from app.models.api import FighterMatch
from app.models.stats import StatSheet
from app.providers.base import ChatLLM, Embedder, Reranker
from app.research.extract import build_sheet_with_evidence
from app.research.seed_fighters import (
    SEED_SHEETS_DIR,
    find_seed_fighter,
    find_seed_sheet,
    load_seed_fighters,
)
from app.research.statsheet import build_stat_sheet, load_facts, profile_from_seed

logger = logging.getLogger(__name__)

# Model extraction gets this long inside research's 45 s budget; after it, facts and defaults.
EXTRACTION_BUDGET_S = 30.0
SEARCH_LIMIT = 20


# Save a sheet; saving the same version again changes nothing.
def save_sheet(connection: sqlite3.Connection, sheet: StatSheet) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO stat_sheets (fighter_id, sheet_hash, sheet_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (
            sheet.fighter_id,
            sheet.sheet_hash,
            sheet.model_dump_json(),
            datetime.now(UTC).isoformat(),
        ),
    )
    connection.commit()


# The newest cached sheet for a fighter, or None (also when a saved row no longer validates).
def cached_sheet(connection: sqlite3.Connection, fighter_id: str) -> StatSheet | None:
    row = connection.execute(
        "SELECT sheet_json FROM stat_sheets WHERE fighter_id = ? ORDER BY rowid DESC LIMIT 1",
        (fighter_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        return StatSheet.model_validate_json(row[0])
    except ValidationError:
        logger.warning("Cached sheet for %s no longer matches the contract.", fighter_id)
        return None


# The sheet for a fighter in a battle, or None when there is none to give yet.
async def resolve_stat_sheet(
    connection: sqlite3.Connection,
    providers: tuple[ChatLLM, Embedder, Reranker],
    entity: str,
    variant: str | None = None,
    raw: str | None = None,
) -> StatSheet | None:
    seed = find_seed_sheet(entity, variant, raw)
    if seed is not None:
        return seed
    fighter = find_seed_fighter(entity, variant, raw)
    if fighter is None or fighter.category == "mythical":
        return None
    cached = cached_sheet(connection, fighter.id)
    if cached is not None:
        return cached
    profile = profile_from_seed(fighter)
    try:
        sheet = await asyncio.wait_for(
            build_sheet_with_evidence(connection, providers, profile), EXTRACTION_BUDGET_S
        )
    except TimeoutError:
        logger.warning("Extraction for %s ran out of time; built from facts.", fighter.id)
        sheet = build_stat_sheet(profile, load_facts(connection, fighter.id))
    except ValueError as error:  # a stat with no level that applies (see build_stat_sheet)
        logger.warning("Could not build a sheet for %s: %s", fighter.id, error)
        return None
    save_sheet(connection, sheet)
    return sheet


# Fighters whose name or id contains the search text: seed-list fighters, then cached ones.
def search_fighters(
    connection: sqlite3.Connection, query: str, limit: int = SEARCH_LIMIT
) -> list[FighterMatch]:
    text = query.strip().lower()
    cached = {row[0] for row in connection.execute("SELECT DISTINCT fighter_id FROM stat_sheets")}
    seeded = {path.stem for path in SEED_SHEETS_DIR.glob("*.json")}
    names = {f.id: f.display_name for f in load_seed_fighters() if f.category != "mythical"}
    for fighter_id in sorted(cached - names.keys()):
        sheet = cached_sheet(connection, fighter_id)
        if sheet is not None:
            names[fighter_id] = sheet.display_name
    matches = [
        FighterMatch(fighter_id=i, display_name=n, cached=i in cached or i in seeded)
        for i, n in names.items()
        if text and (text in n.lower() or text in i)
    ]
    return matches[:limit]
