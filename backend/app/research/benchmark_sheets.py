"""Stat sheets for the benchmark's `--sheets research` run (F07): built by the research pipeline.

The seed run (`--sheets seed`) scores the simulator on hand-verified sheets. This run scores the
whole chain: for every fighter the benchmark names, the pipeline builds the sheet itself (stored
facts, then model extraction with verified quotes, then the builder's later levels), and the
hand-verified seed sheet is deliberately NOT used, so the two runs can be compared. A fighter the
pipeline cannot build a sheet for is left out, so its matchups show as skipped, never as failures.
"""

import logging
import sqlite3
from collections.abc import Sequence

from app.models.stats import StatSheet
from app.providers.base import ChatLLM, Embedder, Reranker
from app.research.extract import build_sheet_with_evidence
from app.research.seed_fighters import find_seed_fighter
from app.research.statsheet import profile_from_seed
from app.simulation.benchmark import Entry, IndexedSheets, SheetSource

logger = logging.getLogger(__name__)


async def research_sheets(
    entries: Sequence[Entry],
    connection: sqlite3.Connection,
    providers: tuple[ChatLLM, Embedder, Reranker],
) -> SheetSource:
    """Build a sheet with the research pipeline for each distinct fighter in the entries."""
    built: dict[str, StatSheet] = {}
    missed: set[str] = set()
    for entry in entries:
        for request in entry.matchup.fighters:
            fighter = find_seed_fighter(request.entity, request.variant, request.raw)
            if fighter is None or fighter.category == "mythical":
                continue  # no ground truth for legends, and only seed-list fighters have profiles
            if fighter.id in built or fighter.id in missed:
                continue
            try:
                built[fighter.id] = await build_sheet_with_evidence(
                    connection, providers, profile_from_seed(fighter)
                )
            except ValueError as error:  # a stat with no level that applies
                logger.warning("Could not build a sheet for %s: %s", fighter.id, error)
                missed.add(fighter.id)
    return IndexedSheets(list(built.values()))
