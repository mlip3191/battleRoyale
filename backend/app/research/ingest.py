"""Download, parse, chunk, embed, and store the reference text for the seed fighters."""

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.providers.base import DocParser, Embedder
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
