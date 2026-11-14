"""Step 8, the next challenger (A05 part 3; D-36, D-41): the decision model shortlists, code tests.

Candidates are seed fighters with sheets plus already-cached fighters, never new research, so
the stage fits its 10 s budget (ARCHITECTURE §4). Structured Decisions answers one choice
question; its 5 likeliest options go to simulation.test_challengers and the closest to 50/50 is
kept. If the model fails, or none of its picks pass the tests, the first seed candidates by id
are tested instead (a fallback).
Everything here that runs in a thread is pure: it reads files and simulates, never writes.
"""

import asyncio
import logging
import math
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.db.connection import connect
from app.models.simulation import ChallengerSuggestion, SimulationResult
from app.models.stats import StatSheet
from app.models.terrain import Terrain
from app.providers.base import DecisionAnswer, DecisionQuestion, StructuredLLM
from app.providers.registry import get_provider
from app.research.seed_fighters import SEED_SHEETS_DIR, load_seed_fighters
from app.simulation import fair

logger = logging.getLogger(__name__)

PROMPT_NAME = "challenger"
PROMPT_PATH = Path(__file__).parents[2] / "prompts" / f"{PROMPT_NAME}.md"
QUESTION = "challenger"
MAX_SEED = 30  # the whole seed list (D-39)
MAX_CACHED = 20  # the most recently cached fighters
SHORTLIST = 5  # how many options get simulated
# The model's share of the 10 s stage budget (a live call took ~4 s); the duels get the rest.
DECIDE_BUDGET_S = 6.0
DATA_LIMIT = 80  # longest name or description sent to the model


@dataclass(frozen=True)
class Candidates:
    """Who may be offered as the next challenger, each list sorted by fighter id."""

    seed: list[StatSheet]
    cached: list[StatSheet]

    @property
    def all(self) -> list[StatSheet]:
        return by_id(self.seed + self.cached)


def by_id(sheets: list[StatSheet]) -> list[StatSheet]:
    return sorted(sheets, key=lambda sheet: sheet.fighter_id)


# The prompt, read fresh so edits apply without a restart.
def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


# Seed fighters that have a hand-verified sheet, in seed-list order, at most MAX_SEED.
def seed_sheets() -> list[StatSheet]:
    paths = [SEED_SHEETS_DIR / f"{fighter.id}.json" for fighter in load_seed_fighters()]
    sheets = [
        StatSheet.model_validate_json(p.read_text(encoding="utf-8")) for p in paths if p.is_file()
    ]
    return sheets[:MAX_SEED]


# Fighters researched for earlier battles, newest first, from the `stat_sheets` table that G04
# (issue #35) will create. Assumed shape: one sheet per row as JSON in `sheet_json`, newest
# row last inserted (`ORDER BY rowid DESC`). If G04 uses different columns or provides a
# research/ function for this read, this query will need to match; a mismatch or any other
# read error is caught below and treated as no cached fighters (seed fighters still work).
def cached_sheets(limit: int = MAX_CACHED, db_path: Path | None = None) -> list[StatSheet]:
    path = db_path or get_settings().data_dir / "app.db"
    if not path.is_file():  # never create the database just to read it
        return []
    try:
        connection = connect(path)
        try:
            if not connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'stat_sheets'"
            ).fetchone():
                return []
            rows = connection.execute(
                "SELECT sheet_json FROM stat_sheets ORDER BY rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        finally:
            connection.close()
    except Exception as error:
        logger.warning("challenger: could not read cached sheets (%s)", type(error).__name__)
        return []
    return [sheet for row in rows if (sheet := _parse_sheet(row["sheet_json"])) is not None]


# One saved sheet, or None if it no longer matches the contract.
def _parse_sheet(text: str) -> StatSheet | None:
    try:
        return StatSheet.model_validate_json(text)
    except ValueError:
        return None


# Seed and cached fighters, minus this matchup's fighters; a fighter in both counts as seed.
def load_candidates(exclude: set[str]) -> Candidates:
    seed = [s for s in seed_sheets() if s.fighter_id not in exclude]
    seen = exclude | {s.fighter_id for s in seed}
    cached: dict[str, StatSheet] = {}
    for sheet in cached_sheets()[:MAX_CACHED]:
        if sheet.fighter_id not in seen:
            cached.setdefault(sheet.fighter_id, sheet)
    return Candidates(seed=by_id(seed), cached=by_id(list(cached.values())))


# The side that won; in a draw or no contest, the likelier side, ties broken by fighter id.
def winner_side(result: SimulationResult, sheets: list[StatSheet]) -> int:
    if result.outcome in ("win_0", "win_1"):
        return int(result.outcome[-1])
    return min((0, 1), key=lambda side: (-result.win_prob[side], sheets[side].fighter_id))


# One line of plain data: newlines and control characters become spaces, runs of space collapse.
def _clip(text: str) -> str:
    printable = "".join(" " if not ch.isprintable() else ch for ch in text)
    return " ".join(printable.split())[:DATA_LIMIT]


# The matchup as decision state; names are data (the prompt says so) and kept short.
def build_state(winner: StatSheet, defeated: StatSheet, terrain: Terrain) -> dict[str, str]:
    return {
        "winner": _clip(winner.display_name),
        "defeated": _clip(defeated.display_name),
        "terrain": terrain.value,
    }


# One choice question whose options are the candidates' fighter ids.
def build_questions(candidates: list[StatSheet]) -> dict[str, DecisionQuestion]:
    criteria = {
        s.fighter_id: _clip(f"{s.display_name}: {s.category}, {s.body}") for s in candidates
    }
    return {QUESTION: {"type": "choice", "instructions": load_prompt(), "criteria": criteria}}


# The SHORTLIST likeliest known candidates; unknown ids and non-finite odds are ignored,
# ties go by fighter id.
def shortlist(answer: DecisionAnswer, candidates: list[StatSheet]) -> list[StatSheet]:
    by_id = {s.fighter_id: s for s in candidates}
    odds = {
        key: float(p)
        for key, p in answer["probabilities"].items()
        if key in by_id and math.isfinite(float(p))
    }
    ranked = sorted(odds, key=lambda key: (-odds[key], key))
    return [by_id[key] for key in ranked[:SHORTLIST]]


# Ask the decision model, within its sub-budget, for the shortlist.
async def ask_model(
    llm: StructuredLLM | None, state: dict[str, str], candidates: list[StatSheet]
) -> list[StatSheet]:
    llm = llm or get_provider("structured")
    call = llm.decide(state, build_questions(candidates), prompt_name=PROMPT_NAME)
    answers = await asyncio.wait_for(call, DECIDE_BUDGET_S)
    return shortlist(answers[QUESTION], candidates)


# The next challenger and whether it came from the fallback path (None: nobody to suggest).
async def suggest(
    sheets: list[StatSheet],
    result: SimulationResult,
    terrain: Terrain,
    llm: StructuredLLM | None = None,
) -> tuple[ChallengerSuggestion | None, bool]:
    side = winner_side(result, sheets)
    winner, defeated = sheets[side], sheets[1 - side]
    candidates = await asyncio.to_thread(load_candidates, {s.fighter_id for s in sheets})
    if not candidates.all:
        return None, True
    picks: list[StatSheet] = []
    try:
        picks = await ask_model(llm, build_state(winner, defeated, terrain), candidates.all)
    except Exception as error:  # any model trouble means the seed fallback, never a crash
        # Only the class name: provider errors can carry request details.
        logger.warning("challenger: decision model failed (%s)", type(error).__name__)
    fallback = not picks
    if fallback:
        picks = candidates.seed[:SHORTLIST]
    tested = await asyncio.to_thread(fair.test_challengers, winner, picks, terrain)
    if not tested and not fallback:  # every model pick failed the tests: try the seed once
        fallback = True
        tried = {s.fighter_id for s in picks}
        picks = [s for s in candidates.seed[:SHORTLIST] if s.fighter_id not in tried]
        if picks:
            tested = await asyncio.to_thread(fair.test_challengers, winner, picks, terrain)
    return (tested[0], fallback) if tested else (None, True)
