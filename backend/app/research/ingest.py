"""Download, parse, chunk, embed, and store the reference text for the seed fighters, and,
on demand, the parts of the article a stat sheet needs for a fighter off the seed list."""

import asyncio
import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.providers.base import DocParser, Embedder
from app.providers.live.doc_parser import split_pieces, strip_markup
from app.providers.live.http import ProviderError
from app.research.facts import store_facts, wikidata_facts
from app.research.kb_store import DocumentRecord, ensure_vector_table, store_document
from app.research.seed_fighters import SeedFighter
from app.research.sources import (
    SourceDocument,
    SourceError,
    fetch_article,
    fetch_wikidata,
    save_raw,
)
from app.research.traits import TraitTables, load_trait_tables, taxon_name

logger = logging.getLogger(__name__)

# Fighters handled at once; the parser is slow, but Wikipedia asks clients not to hammer it.
CONCURRENT_FIGHTERS = 3
# On-demand ingest of one fighter off the seed list must finish within this (G03, #34).
ON_DEMAND_BUDGET_S = 30.0
# Half the parser's usual piece: a piece takes about 25 s at full size, too close to the limit.
ON_DEMAND_PIECE_CHARS = 4_500
SECTION_START = re.compile(r'<section data-mw-section-id="-?\d+"[^>]*>')
HEADING = re.compile(r"<h([2-6])\b[^>]*>(.*?)</h\1>", re.DOTALL)
# Top-level sections that carry size and description, kept with their subsections (PM, #34).
NEEDED_HEADINGS = re.compile(
    r"descri|anatom|characteristic|physical|size|appearance|morpholog|specification|design",
    re.IGNORECASE,
)


@dataclass
class IngestSummary:
    """What a run did, for the table the script prints."""

    fighters: int = 0
    documents: int = 0
    parsed: int = 0
    chunks: int = 0
    facts: int = 0
    failures: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    """Fighters with no PanTHERIA or AnimalTraits row for their scientific name."""
    trait_origin: str = ""
    """Where the trait rows were loaded from (the Hugging Face team dataset, or the originals)."""


# True when this exact revision is already stored, so it needn't be parsed again.
def _already_stored(connection: sqlite3.Connection, doc_id: str, document: SourceDocument) -> bool:
    row = connection.execute("SELECT url FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
    return document.pinned and row is not None and row[0] == document.url


# Parse a fighter's article and store its passages, unless that revision is already stored.
async def _ingest_article(
    connection: sqlite3.Connection,
    parser: DocParser,
    embedder: Embedder,
    fighter: SeedFighter,
    document: SourceDocument,
) -> None:
    doc_id = f"{fighter.id}/wikipedia"
    if _already_stored(connection, doc_id, document):
        return
    text = await parser.parse(document.body, document.media_type)
    record = DocumentRecord(
        doc_id=doc_id,
        fighter_id=fighter.id,
        source="wikipedia",
        title=document.title,
        url=document.url,
        license=document.license,
        retrieved_at=document.retrieved_at.isoformat(),
        text=text,
    )
    await store_document(connection, record, embedder)


# Store the structured facts from a fighter's Wikidata entity.
def _ingest_wikidata(
    connection: sqlite3.Connection, fighter: SeedFighter, document: SourceDocument
) -> None:
    facts = wikidata_facts(json.loads(document.body))
    retrieved_at = document.retrieved_at.isoformat()
    store_facts(connection, fighter.id, "wikidata", facts, document.license, retrieved_at)


# Store each trait dataset's rows for the fighter's scientific name, and note a fighter with none.
def _ingest_traits(
    connection: sqlite3.Connection,
    fighter: SeedFighter,
    entity: dict[str, Any],
    traits: TraitTables,
    summary: IngestSummary,
) -> None:
    name = taxon_name(entity)
    retrieved_at = datetime.now(UTC).isoformat()
    matched = False
    for source, table in traits.by_source.items():
        facts = table.get(name, []) if name else []
        matched = matched or bool(facts)
        store_facts(connection, fighter.id, source, facts, traits.licenses[source], retrieved_at)
    if traits.by_source and not matched:
        summary.unmatched.append(f"{fighter.id} ({name or 'no scientific name'})")


# Ingest one fighter; a failure is logged and recorded, and never stops the run.
async def ingest_fighter(
    connection: sqlite3.Connection,
    client: httpx.AsyncClient,
    parser: DocParser,
    embedder: Embedder,
    fighter: SeedFighter,
    kb_dir: Path,
    summary: IngestSummary,
    traits: TraitTables | None = None,
) -> None:
    try:
        article = await fetch_article(client, fighter.article)
        if article is None:
            raise SourceError(f"no article titled {fighter.article!r}")
        summary.documents += 1
        save_raw(kb_dir, fighter.id, "wikipedia", article)
        await _ingest_article(connection, parser, embedder, fighter, article)
        entity = await fetch_wikidata(client, fighter.article)
        if entity is None:
            logger.info("No Wikidata item for %s; any facts from earlier runs stay.", fighter.id)
            return
        save_raw(kb_dir, fighter.id, "wikidata", entity)
        _ingest_wikidata(connection, fighter, entity)
        if traits is not None:
            _ingest_traits(connection, fighter, json.loads(entity.body), traits, summary)
    except (SourceError, ProviderError, httpx.HTTPError, ValueError, sqlite3.Error) as error:
        logger.warning("Could not ingest %s: %s", fighter.id, error)
        summary.failures.append(f"{fighter.id}: {error}")


# Count what is stored, so the summary describes the knowledge base and not just this run.
# The table name goes into the SQL text, so callers pass only this module's fixed names.
def _count(connection: sqlite3.Connection, table: str) -> int:
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# Ingest every fighter a few at a time, and report the totals.
async def ingest_all(
    connection: sqlite3.Connection,
    client: httpx.AsyncClient,
    parser: DocParser,
    embedder: Embedder,
    fighters: list[SeedFighter],
    kb_dir: Path,
) -> IngestSummary:
    await ensure_vector_table(connection, embedder)
    summary = IngestSummary(fighters=len(fighters))
    token = get_settings().hf_token
    traits, trait_failures = await load_trait_tables(
        client, kb_dir, hf_token=token.get_secret_value() if token else None
    )
    summary.failures.extend(trait_failures)
    summary.trait_origin = traits.origin
    limit = asyncio.Semaphore(CONCURRENT_FIGHTERS)

    async def one(fighter: SeedFighter) -> None:
        async with limit:
            await ingest_fighter(
                connection, client, parser, embedder, fighter, kb_dir, summary, traits
            )

    await asyncio.gather(*(one(fighter) for fighter in fighters))
    summary.parsed = _count(connection, "documents")
    summary.chunks = _count(connection, "chunks")
    summary.facts = _count(connection, "facts")
    return summary


# The article's lead plus its size and description sections, each with its subsections, as
# HTML pieces. An article without section markup is kept whole.
def needed_sections(html: str) -> list[str]:
    starts = [match.start() for match in SECTION_START.finditer(html)]
    if not starts:
        return [html]
    pieces = [html[a:b] for a, b in zip(starts, [*starts[1:], len(html)], strict=True)]
    groups: list[list[str]] = []
    keep = True  # the lead comes first and is always kept
    for piece in pieces:
        heading = HEADING.search(piece)
        level = int(heading.group(1)) if heading and heading.start() < 300 else None
        if heading and level == 2:  # heading is set whenever level is
            keep = bool(NEEDED_HEADINGS.search(heading.group(2)))
            if keep:
                groups.append([])
        elif level is None and not groups:
            groups.append([])  # the lead
        if keep and groups:
            groups[-1].append(piece)
    return ["".join(group) for group in groups]


# Fetch one article and store only its needed sections, parsed in parallel.
async def _ingest_needed(
    connection: sqlite3.Connection,
    client: httpx.AsyncClient,
    parser: DocParser,
    embedder: Embedder,
    fighter_id: str,
    title: str,
) -> bool:
    article = await fetch_article(client, title)
    if article is None:
        logger.info("No article titled %r for %s.", title, fighter_id)
        return False
    sections = needed_sections(article.body.decode("utf-8", errors="replace"))
    # Cut each section into parser-sized pieces here, so every piece is parsed at once.
    pieces = [
        piece
        for section in sections
        for piece in split_pieces(strip_markup(section), limit=ON_DEMAND_PIECE_CHARS)
    ]
    # A TaskGroup cancels the other pieces as soon as one fails, so no parser calls run on.
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(parser.parse(piece.encode("utf-8"), article.media_type))
                for piece in pieces
            ]
    except ExceptionGroup as failed:
        raise failed.exceptions[0] from failed
    texts = [task.result() for task in tasks]
    if not any(text.strip() for text in texts):
        logger.warning("Parser returned no text for %s; stored nothing.", fighter_id)
        return False  # nothing stored, so a later lookup tries again
    record = DocumentRecord(
        doc_id=f"{fighter_id}/wikipedia",
        fighter_id=fighter_id,
        source="wikipedia",
        title=article.title,
        url=article.url,
        license=article.license,
        retrieved_at=article.retrieved_at.isoformat(),
        text="\n".join(texts),
    )
    await ensure_vector_table(connection, embedder)
    await store_document(connection, record, embedder)
    return True


# Ingest a fighter off the seed list within ON_DEMAND_BUDGET_S. True when its passages are
# stored; a timeout or failure is logged and gives False, never an error.
async def ingest_on_demand(
    connection: sqlite3.Connection,
    client: httpx.AsyncClient,
    parser: DocParser,
    embedder: Embedder,
    fighter_id: str,
    title: str,
) -> bool:
    try:
        return await asyncio.wait_for(
            _ingest_needed(connection, client, parser, embedder, fighter_id, title),
            ON_DEMAND_BUDGET_S,
        )
    except TimeoutError:
        logger.warning("On-demand ingest of %s ran past %.0f s.", fighter_id, ON_DEMAND_BUDGET_S)
    except (SourceError, ProviderError, httpx.HTTPError, ValueError, sqlite3.Error) as error:
        logger.warning("Could not ingest %s on demand: %s", fighter_id, error)
    return False
