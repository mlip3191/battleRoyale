"""Thin stub of the battle orchestrator (A05, MS-1): seed sheets in, real simulation, verdict out.

Runs the stages in ARCHITECTURE §4 order as a background task and records every change.
Only `research` (seed sheets only) and `simulate` (the real engine) do real work; every other
stage is marked done with detail "stub".

TODO, remaining A05 pieces (issue #36):
- research: real research for fighters not in the seed sheets, plus size_reference entities,
  both fighters in parallel; fall back to an all-estimate sheet with a banner.
- per-stage time budgets from ARCHITECTURE §4, with "fallback"/"failed" on error or timeout.
- run summary, challenger and script in parallel after simulate, then audio, music and images
  in parallel (A06, A07, A08, StructuredLLM challenger from seed/cached fighters only).
- summary + fair fight (code only) filling `fair_fight`.
- save the BattleRecord to the `battles` table after every change (store.py is memory only).
- cache: reuse the stored result for the same matchup and sheet hashes.
- seed-sheet lookup ignores `variant`; match variants once variant sheets exist.
"""

import asyncio
import logging

from app.models.matchup import Matchup
from app.models.simulation import SimulationResult
from app.models.stats import StatSheet
from app.pipeline.store import STAGES, BattleStore
from app.research.seed_fighters import find_seed_sheet
from app.simulation import engine

logger = logging.getLogger(__name__)

STUB = "stub"
REAL_STAGES = ("research", "simulate")
SIMULATE_FAILED = "The simulation hit a snag, so there's no verdict this time. Please try again."
UNEXPECTED = "Something went wrong behind the scenes. Please try again."
CANCELLED = "This battle was stopped before it finished. Please try again."
SIZE_REFERENCE_UNSUPPORTED = (
    "Size swaps like {raw!r} aren't supported yet. Try the fighters at their normal size."
)
NOT_IN_SEED = (
    "We don't have a stat sheet for {name!r} yet. For now, pick one of our ready-made fighters."
)

# Running battles; holding a reference keeps a task from being garbage-collected mid-fight.
_tasks: set[asyncio.Task[None]] = set()


class StageFailed(Exception):
    """A stage could not finish; the message is plain English for the user."""


# Save a new battle, start running it in the background, and return its id at once.
async def start_battle(matchup: Matchup, store: BattleStore) -> str:
    record = await store.create(matchup)
    task = asyncio.create_task(run_battle(record.battle_id, store))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return record.battle_id


# Run every stage in order; the battle ends "done" if simulate finished, else "failed".
async def run_battle(battle_id: str, store: BattleStore) -> None:
    record = await store.get(battle_id)
    if record is None:
        # Nothing was saved under this id, so there is no battle to finish.
        logger.error("battle %s not found; nothing to run", battle_id)
        return
    matchup = record.matchup
    sheets: list[StatSheet] = []
    stage = STAGES[0]
    status, reason = "failed", UNEXPECTED
    try:
        for stage in STAGES:
            await store.set_stage(battle_id, stage, "running", _running_detail(stage, matchup))
            if stage == "research":
                sheets = _resolve_fighters(matchup)
                await store.update(battle_id, stat_sheets=sheets)
            elif stage == "simulate":
                result = await _simulate(matchup, sheets)
                await store.update(battle_id, result=result)
            await store.set_stage(battle_id, stage, "done", None if stage in REAL_STAGES else STUB)
        status = "done"
    except StageFailed as error:
        reason = str(error)
    except asyncio.CancelledError:
        reason = CANCELLED
        raise
    except Exception:
        logger.exception("battle %s crashed in stage %s", battle_id, stage)
    finally:
        # A battle must never stay "running": always write its final status.
        await _finish(battle_id, store, stage, status, reason)


# Mark the stage that stopped the battle (best effort), then write the final status.
async def _finish(battle_id: str, store: BattleStore, stage: str, status: str, reason: str) -> None:
    if status == "failed":
        try:
            await store.set_stage(battle_id, stage, "failed", reason)
        except Exception:
            logger.exception("battle %s: could not mark stage %s failed", battle_id, stage)
    # Ending the battle also wakes every stream so it sends its "end" event.
    await store.update(battle_id, status=status)


# A short note shown while a stage runs.
def _running_detail(stage: str, matchup: Matchup) -> str | None:
    if stage == "research":
        names = " and ".join(f.entity for f in matchup.fighters)
        return f"Looking up {names}"
    return None if stage in REAL_STAGES else STUB


# One seed sheet per side; a fighter without one (or a size swap) stops the battle.
def _resolve_fighters(matchup: Matchup) -> list[StatSheet]:
    sheets = []
    for fighter in matchup.fighters:
        if fighter.size_reference is not None:
            raise StageFailed(SIZE_REFERENCE_UNSUPPORTED.format(raw=fighter.raw))
        sheet = find_seed_sheet(fighter.entity)
        if sheet is None:
            raise StageFailed(NOT_IN_SEED.format(name=fighter.entity))
        sheets.append(sheet)
    return sheets


# Run the real engine off the event loop so other battles and streams keep moving.
async def _simulate(matchup: Matchup, sheets: list[StatSheet]) -> SimulationResult:
    try:
        return await asyncio.to_thread(engine.run, matchup, sheets)
    except Exception as error:
        logger.exception("simulation failed")
        raise StageFailed(SIMULATE_FAILED) from error
