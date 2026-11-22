"""Find a fighter's stat sheet for a battle, and cache built sheets (G04 part 3).

Order: the hand-verified seed sheet, then a sheet cached for an earlier battle, then a new
sheet built from stored facts and model extraction for a seed-list fighter, which is saved so
repeat battles reuse the same sheet (and the same simulation seed). A creature in
data/seed/mythical.yaml is built from its analogs (G09). A legend that isn't in the file is
modeled from its Wikipedia article by resolve_legend (G09, live mode only); anything else
gets None.
"""

import asyncio
import logging
import sqlite3
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.models.api import FighterMatch
from app.models.stats import StatSheet
from app.providers.base import ChatLLM, Embedder, Reranker
from app.research.extract import build_sheet_with_evidence
from app.research.lore import (
    NONSENSE,
    UNAVAILABLE,
    LoreOutcome,
    code_kind,
    lore_for,
)
from app.research.mythical import build_mythical_sheet, find_creature
from app.research.seed_fighters import (
    SEED_SHEETS_DIR,
    fighter_slug,
    find_seed_fighter,
    find_seed_sheet,
    load_seed_fighters,
)
from app.research.statsheet import (
    FighterProfile,
    build_stat_sheet,
    load_facts,
    profile_from_seed,
)

logger = logging.getLogger(__name__)

# Model extraction gets this long inside research's 45 s budget; after it, facts and defaults.
EXTRACTION_BUDGET_S = 30.0
# Fetching a legend's article and asking the model get this long, also inside research's budget.
LEGEND_BUDGET_S = 30.0
ARTICLE_TIMEOUT_S = 10.0
# One lock per legend name, so two lookups of the same new legend model it once.
_LEGEND_LOCKS: dict[str, asyncio.Lock] = {}
# A refused name (found: false, or a quote or analog that failed code's check) isn't looked up
# again for this long, so a retry answers at once instead of costing another 10 to 26 s
# model call (#324). Outages are never remembered.
REFUSAL_MEMORY_S = 600.0
_REFUSED: dict[str, float] = {}  # legend slug -> when it was refused (time.monotonic)
# A plausible real fighter that is not a legend (#403) is remembered the same way, for as long,
# but in its own table, so the lookup (about 6 s) is not repeated for the same unknown name
# (#445). Real refusals stay in _REFUSED only. Outages are never remembered.
NOT_A_LEGEND_MEMORY_S = 600.0
_NOT_A_LEGEND: dict[str, float] = {}  # legend slug -> when it was found not to be a legend
_NOT_A_LEGEND_KIND: dict[str, str] = {}  # legend slug -> the fixed reason it gave (#453)
_NOT_A_LEGEND_SHAPE: dict[str, tuple[str | None, str | None]] = {}  # -> (category, size) (#517)
# At most this many new legends are fetched and modeled at once, so many unknown names can't
# flood Wikipedia and the chat model (#324). Waiting for a slot counts toward LEGEND_BUDGET_S.
MAX_LEGEND_LOOKUPS = 2
_SLOTS: tuple[asyncio.AbstractEventLoop, asyncio.Semaphore] | None = None
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
    creature = find_creature(entity)
    if creature is not None:  # cheap and deterministic, so built each time rather than cached
        return build_mythical_sheet(creature)
    fighter = find_seed_fighter(entity, variant, raw)
    if fighter is None or fighter.category == "mythical":
        return None
    cached = cached_sheet(connection, fighter.id)
    if cached is not None and cached.category != "mythical":  # never a legend for a seed fighter
        return cached
    profile = profile_from_seed(fighter)
    try:
        sheet = await asyncio.wait_for(
            build_sheet_with_evidence(connection, providers, profile), EXTRACTION_BUDGET_S
        )
    except TimeoutError:
        # Not cached: a later battle retries extraction instead of reusing this weaker sheet.
        logger.warning("Extraction for %s ran out of time; built from facts.", fighter.id)
        return _sheet_without_extraction(connection, profile)
    except ValueError as error:  # a stat with no level that applies (see build_stat_sheet)
        logger.warning("Could not build a sheet for %s: %s", fighter.id, error)
        return None
    save_sheet(connection, sheet)
    return sheet


# A sheet from stored facts and defaults only, or None when one can't be built.
def _sheet_without_extraction(
    connection: sqlite3.Connection, profile: FighterProfile
) -> StatSheet | None:
    try:
        return build_stat_sheet(profile, load_facts(connection, profile.fighter_id))
    except ValueError as error:
        logger.warning("Could not build a sheet for %s: %s", profile.fighter_id, error)
        return None


# Seed-list fighters whose name or id contains the search text. Cached sheets off the seed list
# (legends, and animals researched on demand, #518) had no safety check of their own, so they
# are never listed.
def search_fighters(
    connection: sqlite3.Connection, query: str, limit: int = SEARCH_LIMIT
) -> list[FighterMatch]:
    text = query.strip().lower()
    cached = {row[0] for row in connection.execute("SELECT DISTINCT fighter_id FROM stat_sheets")}
    seeded = {path.stem for path in SEED_SHEETS_DIR.glob("*.json")}
    names = {f.id: f.display_name for f in load_seed_fighters() if f.category != "mythical"}
    matches = [
        FighterMatch(fighter_id=i, display_name=n, cached=i in cached or i in seeded)
        for i, n in names.items()
        if text and (text in n.lower() or text in i)
    ]
    return matches[:limit]


# A client for Wikipedia in live mode; None in mock mode, so tests and CI never go online.
def legend_client() -> httpx.AsyncClient | None:
    if get_settings().provider_mode == "mock":
        return None
    return httpx.AsyncClient(timeout=ARTICLE_TIMEOUT_S)


# A legend not in mythical.yaml (G09): its cached sheet, or one modeled from its article now
# and saved. Otherwise the LoreOutcome says why (blocked, or a service is down), or None when
# there is nothing to model: mock mode (no article can be fetched) or "not a legend" (#403), a
# plausible real fighter that fights on an estimate sheet.
async def resolve_legend(
    connection: sqlite3.Connection, chat: ChatLLM, name: str
) -> StatSheet | LoreOutcome | None:
    async with _LEGEND_LOCKS.setdefault(fighter_slug(name), asyncio.Lock()):
        return await _resolve_legend(connection, chat, name)


# resolve_legend's work, run while holding that name's lock.
async def _resolve_legend(
    connection: sqlite3.Connection, chat: ChatLLM, name: str
) -> StatSheet | LoreOutcome | None:
    slug = fighter_slug(name)
    cached = cached_sheet(connection, slug)
    if cached is not None and cached.category == "mythical":
        return cached
    if recently_refused(slug):
        return NONSENSE
    if recently_not_a_legend(slug):
        return None  # asked a moment ago: still a plausible real fighter, so an estimate sheet
    kind = code_kind(name)  # "a god" (#444) or "navy seal" (D-69): known kinds, in mock mode too
    if kind is not None:
        remember_not_a_legend(slug, kind)
        return None
    client = legend_client()
    if client is None:
        return None
    try:
        async with client:
            outcome = await asyncio.wait_for(
                _in_a_slot(lambda: lore_for(name, client, chat)), LEGEND_BUDGET_S
            )
    except TimeoutError:
        logger.warning("Modeling the legend %r ran out of time.", name)
        return UNAVAILABLE
    if outcome.not_a_legend:  # a plausible real fighter (#403): an estimate sheet, and remembered
        remember_not_a_legend(slug, outcome.kind, outcome.category, outcome.size_class)
        return None
    if outcome.creature is None:
        if outcome.blocked:
            remember_refusal(slug)
        return outcome
    try:
        sheet = build_mythical_sheet(outcome.creature)
    except ValueError as error:  # an analog whose sheet can't be built
        logger.warning("Could not build a sheet for the legend %r: %s", name, error)
        return UNAVAILABLE
    save_sheet(connection, sheet)
    return sheet


# True when the model refused this legend within the last REFUSAL_MEMORY_S.
def recently_refused(slug: str) -> bool:
    refused_at = _REFUSED.get(slug)
    if refused_at is None:
        return False
    if time.monotonic() - refused_at < REFUSAL_MEMORY_S:
        return True
    del _REFUSED[slug]
    return False


# Remember a refusal, dropping any that have expired so the memory never grows without bound.
def remember_refusal(slug: str) -> None:
    now = time.monotonic()
    for old in [name for name, at in _REFUSED.items() if now - at >= REFUSAL_MEMORY_S]:
        del _REFUSED[old]
    _REFUSED[slug] = now


# True when this name was found not to be a legend within the last NOT_A_LEGEND_MEMORY_S.
def recently_not_a_legend(slug: str) -> bool:
    found_at = _NOT_A_LEGEND.get(slug)
    if found_at is None:
        return False
    if time.monotonic() - found_at < NOT_A_LEGEND_MEMORY_S:
        return True
    del _NOT_A_LEGEND[slug]
    _NOT_A_LEGEND_KIND.pop(slug, None)
    _NOT_A_LEGEND_SHAPE.pop(slug, None)
    return False


# Remember a "not a legend" answer, dropping expired ones so the memory never grows without bound.
def remember_not_a_legend(
    slug: str, kind: str | None = None, category: str | None = None, size_class: str | None = None
) -> None:
    now = time.monotonic()
    for old in [name for name, at in _NOT_A_LEGEND.items() if now - at >= NOT_A_LEGEND_MEMORY_S]:
        del _NOT_A_LEGEND[old]
        _NOT_A_LEGEND_KIND.pop(old, None)
        _NOT_A_LEGEND_SHAPE.pop(old, None)
    _NOT_A_LEGEND[slug] = now
    if kind:
        _NOT_A_LEGEND_KIND[slug] = kind
    else:
        _NOT_A_LEGEND_KIND.pop(slug, None)
    _NOT_A_LEGEND_SHAPE[slug] = (category, size_class)


# The fixed reason remembered for a name that is not a legend ("real_animal"), or None.
def not_a_legend_kind(slug: str) -> str | None:
    return _NOT_A_LEGEND_KIND.get(slug) if recently_not_a_legend(slug) else None


# The animal kind and size class remembered with it (#517): (category, size class), each or None.
def not_a_legend_shape(slug: str) -> tuple[str | None, str | None]:
    if not recently_not_a_legend(slug):
        return (None, None)
    return _NOT_A_LEGEND_SHAPE.get(slug, (None, None))


# Forget every remembered answer (tests start clean; a restart does the same in the app).
def forget_refusals() -> None:
    _REFUSED.clear()
    _NOT_A_LEGEND.clear()
    _NOT_A_LEGEND_KIND.clear()
    _NOT_A_LEGEND_SHAPE.clear()


# This event loop's lookup limit (a semaphore belongs to one loop, and tests start new ones).
def _lookup_slots() -> asyncio.Semaphore:
    global _SLOTS
    loop = asyncio.get_running_loop()
    if _SLOTS is None or _SLOTS[0] is not loop:
        _SLOTS = (loop, asyncio.Semaphore(MAX_LEGEND_LOOKUPS))
    return _SLOTS[1]


# Run one legend lookup once a slot is free. It takes a function, not a coroutine, so a lookup
# that times out while still waiting never leaves an unstarted coroutine behind.
async def _in_a_slot(start: Callable[[], Awaitable[LoreOutcome]]) -> LoreOutcome:
    async with _lookup_slots():
        return await start()


# The legends cached by earlier battles (not the 12 in mythical.yaml): (id, name, versions).
def cached_legends(connection: sqlite3.Connection) -> list[tuple[str, str, int]]:
    # The name comes from each legend's newest saved version (the highest rowid).
    rows = connection.execute(
        "SELECT s.fighter_id, json_extract(s.sheet_json, '$.display_name'), c.versions "
        "FROM stat_sheets AS s JOIN ("
        "  SELECT fighter_id, MAX(rowid) AS newest, COUNT(*) AS versions FROM stat_sheets"
        "  WHERE json_extract(sheet_json, '$.category') = 'mythical' GROUP BY fighter_id"
        ") AS c ON s.rowid = c.newest ORDER BY s.fighter_id"
    ).fetchall()
    return [(fighter_id, name, count) for fighter_id, name, count in rows]


# Remove a cached legend so the next battle models it again; returns how many rows went.
# Never touches a seed fighter or a creature in mythical.yaml, which aren't cached legends.
def forget_legend(connection: sqlite3.Connection, name: str) -> int:
    if find_creature(name) is not None or find_seed_fighter(name) is not None:
        raise ValueError(f"{name!r} is a seed fighter or in mythical.yaml, not a cached legend")
    removed = connection.execute(
        "DELETE FROM stat_sheets WHERE fighter_id = ? "
        "AND json_extract(sheet_json, '$.category') = 'mythical'",
        (fighter_slug(name),),
    ).rowcount
    connection.commit()
    return removed
