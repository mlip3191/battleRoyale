"""Research for a real animal off the seed list (#518), at battle time, in live mode only.

An unlisted animal starts as an all-estimate sheet (estimate_sheet.py, shaped by #517). This
module fetches its Wikipedia article, stores it (ingest_on_demand), and runs the same extraction
as the seed fighters (build_sheet_with_evidence), so every number it keeps carries a quote that
code checked. Before that it stores the animal's Wikidata measurements as facts, read by code
as for the seed fighters, and reads the article's taxobox "Class:" row with code, so an ostrich
is a bird even when the lookup's label said otherwise. Each extracted stat replaces the
estimate's value; every other stat stays the labeled estimate (with its #517 size class). A
sheet with at least one sourced stat is cached, so later battles reuse it.

The battle waits at most ON_DEMAND_RESEARCH_S, and never past the research stage's deadline
(the legend lookup before it can use most of the stage). If the build takes longer, the battle
fights on the estimate and the build carries on in the background, so the next battle gets the
researched sheet. A name that gave no sourced stat is not tried again for
NOTHING_FOUND_MEMORY_S, and an article without an animal taxobox gives nothing, so a name that
lands on an unrelated page never lends it its numbers. Researched sheets had no safety check of
their own, so like legends they are never listed in fighter search or offered as the next
challenger (sheet_store.search_fighters, challenger.cached_sheets).
"""

import asyncio
import json
import logging
import re
import sqlite3
import time
from html import unescape

import httpx

from app.config import get_settings
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.stats import StatSheet
from app.providers.registry import get_provider
from app.research.estimate_sheet import ANIMAL_KINDS, estimate_sheet
from app.research.extract import build_sheet_with_evidence
from app.research.facts import store_facts, wikidata_facts
from app.research.ingest import ingest_on_demand
from app.research.sheet_hash import compute_sheet_hash
from app.research.sheet_store import cached_sheet, legend_client, save_sheet
from app.research.sources import SourceError, fetch_article, fetch_wikidata
from app.research.statsheet import FighterProfile

logger = logging.getLogger(__name__)

ON_DEMAND_RESEARCH_S = 20.0  # how long a battle waits; the build itself may run on after
BUILD_LIMIT_S = 90.0  # the whole background build, so a stalled call can't hang forever
NOTHING_FOUND_MEMORY_S = 600.0
RESEARCHED_KINDS = frozenset({"real_animal"})  # objects stay inert; people have no useful article
_BUILDS: dict[str, asyncio.Task[StatSheet | None]] = {}  # fighter id -> its build in flight
_NOTHING_FOUND: dict[str, float] = {}  # fighter id -> when its build found nothing
# The taxobox "Class:" row of an animal's article -> our animal kind (#517's ANIMAL_KINDS).
TAXON_CLASSES = {
    "mammalia": "mammal",
    "aves": "bird",
    "reptilia": "reptile",
    "amphibia": "amphibian",
    "actinopterygii": "fish",
    "chondrichthyes": "fish",
    "sarcopterygii": "fish",
    "insecta": "insect",
    "arachnida": "arachnid",
    "cephalopoda": "mollusk",
    "gastropoda": "mollusk",
    "bivalvia": "mollusk",
}
TAXOBOX_CLASS = re.compile(
    r">\s*Class:\s*</t[dh]>\s*<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL
)


# The researched sheet for an unlisted fighter if there is one in time, else its estimate.
# `title` is the article to read (the fighter as typed, without a variant); `deadline` is the
# time.monotonic() by which the battle must have its sheet, so the wait never overruns the stage.
async def researched_or_estimate(
    estimate: StatSheet,
    kind: str | None,
    size_class: str | None = None,
    *,
    title: str | None = None,
    deadline: float | None = None,
) -> StatSheet:
    if kind not in RESEARCHED_KINDS or _recently_found_nothing(estimate.fighter_id):
        return estimate
    if get_settings().provider_mode == "mock":  # no article can be fetched
        return estimate
    connection = connect()
    try:
        apply_migrations(connection)
        cached = cached_sheet(connection, estimate.fighter_id)
    finally:
        connection.close()
    if cached is not None and cached.category != "mythical":
        return cached
    build = _BUILDS.get(estimate.fighter_id)
    if build is None:
        article = title or estimate.display_name
        build = asyncio.create_task(_build(estimate, kind, size_class, article))
        _BUILDS[estimate.fighter_id] = build
        build.add_done_callback(lambda _: _BUILDS.pop(estimate.fighter_id, None))
    wait = ON_DEMAND_RESEARCH_S
    if deadline is not None:
        wait = min(wait, deadline - time.monotonic())
    try:
        if wait <= 0:  # no time left this battle; the build still runs for the next one
            raise TimeoutError
        sheet = await asyncio.wait_for(asyncio.shield(build), wait)
    except TimeoutError:
        logger.info("Research for %s is still running; fighting on estimates.", estimate.fighter_id)
        return estimate
    return sheet or estimate


# Fetch, store and extract the fighter's article; the merged sheet, cached, or None. A sheet
# with no sourced stat (only a better animal kind) is used for this battle but counts as nothing
# found, so later battles don't redo the whole build.
async def _build(
    estimate: StatSheet, kind: str | None, size_class: str | None, title: str
) -> StatSheet | None:
    try:
        sheet = await asyncio.wait_for(_research(estimate, kind, size_class, title), BUILD_LIMIT_S)
    except Exception as error:  # noqa: BLE001 - research is a bonus: any failure means estimates
        logger.warning("On-demand research for %s failed: %s", estimate.fighter_id, error)
        sheet = None
    if sheet is None or all(value.is_estimate for value in sheet.stats.values()):
        _remember_nothing_found(estimate.fighter_id)
    return sheet


# The work of _build, on its own database connection: the taxobox's animal kind, Wikidata facts,
# the article's passages, then extraction. An article with no animal taxobox gives nothing (it
# may not be about this animal). Only a sheet with a sourced stat is saved.
async def _research(
    estimate: StatSheet, kind: str | None, size_class: str | None, title: str
) -> StatSheet | None:
    client = legend_client()
    if client is None:
        return None
    connection = connect()
    try:
        apply_migrations(connection)
        async with client:
            animal_kind = await _taxobox_kind(client, title)
            if animal_kind is None:
                return None
            await _store_wikidata_facts(connection, client, estimate.fighter_id, title)
            await ingest_on_demand(
                connection,
                client,
                get_provider("doc_parser"),
                get_provider("embedder"),
                estimate.fighter_id,
                title,
            )
        base = estimate
        if animal_kind != estimate.category:
            base = estimate_sheet(
                estimate.display_name, kind, category=animal_kind, size_class=size_class
            )
        providers = (get_provider("chat"), get_provider("embedder"), get_provider("reranker"))
        built = await build_sheet_with_evidence(connection, providers, profile_of(base))
        sheet = merged(base, built)
        if sheet is None:
            return base if base is not estimate else None  # a better kind, nothing sourced
        save_sheet(connection, sheet)
        return sheet
    finally:
        connection.close()


# Store the animal's Wikidata measurements (mass, length, height, speed) as facts, read by code.
async def _store_wikidata_facts(
    connection: sqlite3.Connection, client: httpx.AsyncClient, fighter_id: str, title: str
) -> None:
    try:
        document = await fetch_wikidata(client, title)
    except (SourceError, httpx.HTTPError) as error:
        logger.warning("No Wikidata facts for %s: %s", fighter_id, error)
        return
    if document is None:
        return
    facts = wikidata_facts(json.loads(document.body))
    retrieved_at = document.retrieved_at.isoformat()
    store_facts(connection, fighter_id, "wikidata", facts, document.license, retrieved_at)


# The animal kind from the article's taxobox "Class:" row, or None when there is none we know.
async def _taxobox_kind(client: httpx.AsyncClient, title: str) -> str | None:
    try:
        article = await fetch_article(client, title)
    except (SourceError, httpx.HTTPError):
        return None
    if article is None:
        return None
    return kind_from_taxobox(article.body.decode("utf-8", errors="replace"))


# The taxobox's class (Aves, Reptilia, ...) as one of our animal kinds, or None.
def kind_from_taxobox(html: str) -> str | None:
    match = TAXOBOX_CLASS.search(html)
    if match is None:
        return None
    taxon = unescape(re.sub(r"<[^>]+>", " ", match.group(1))).split()
    kind = TAXON_CLASSES.get(taxon[0].lower()) if taxon else None
    return kind if kind in ANIMAL_KINDS else None


# The estimate's identity (kind, body, habitat, weapons) as a profile for extraction.
def profile_of(estimate: StatSheet) -> FighterProfile:
    return FighterProfile(
        fighter_id=estimate.fighter_id,
        display_name=estimate.display_name,
        media_name=estimate.media_name,
        category=estimate.category,
        body=estimate.body.value,
        habitat=estimate.habitat.value,
        weapons=tuple(estimate.weapons),
    )


# The estimate with every extracted (quoted, checked) stat put in, or None when none was found.
def merged(estimate: StatSheet, built: StatSheet) -> StatSheet | None:
    found = {stat: value for stat, value in built.stats.items() if value.method == "extracted"}
    if not found:
        return None
    stats = {**estimate.stats, **found}
    return StatSheet.model_validate(
        {**estimate.model_dump(), "stats": stats, "sheet_hash": compute_sheet_hash(stats)}
    )


# True when this fighter's research found nothing within the last NOTHING_FOUND_MEMORY_S.
def _recently_found_nothing(fighter_id: str) -> bool:
    at = _NOTHING_FOUND.get(fighter_id)
    return at is not None and time.monotonic() - at < NOTHING_FOUND_MEMORY_S


# Remember an empty result, dropping expired ones so the memory never grows without bound.
def _remember_nothing_found(fighter_id: str) -> None:
    now = time.monotonic()
    for old in [i for i, at in _NOTHING_FOUND.items() if now - at >= NOTHING_FOUND_MEMORY_S]:
        del _NOTHING_FOUND[old]
    _NOTHING_FOUND[fighter_id] = now


# Cancel builds in flight and forget empty results (tests start clean).
async def forget_research() -> None:
    builds = list(_BUILDS.values())
    for build in builds:
        build.cancel()
    await asyncio.gather(*builds, return_exceptions=True)
    _BUILDS.clear()
    _NOTHING_FOUND.clear()
