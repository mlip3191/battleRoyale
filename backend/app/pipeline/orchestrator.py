"""The battle orchestrator (A05): runs the stages in ARCHITECTURE §4 order and records progress.

Flow: research (both fighters and any size_reference entities, in parallel) -> simulate ->
then in parallel: summary + fair fight, challenger, images, and the broadcast (scripts, then
audio and music in parallel). Images start right after simulate (ARCHITECTURE §4), not
after the scripts. The verdict is saved before any of those start, so it never
waits for media. Every stage has a time limit (`stages.STAGE_BUDGETS_S`). Research or
simulate failing fails the battle; any later stage failing ends "fallback" and the battle
goes on. The battle is "done" if and only if simulate succeeded, and it never stays "running".

TODO, remaining A05 pieces (issue #36):
- part 3: the real challenger stage (StructuredLLM over seed and cached fighters only, then
  simulation.test_challengers), replacing the stub in stages.py.
- part 4: save the BattleRecord to the `battles` table after every change (store.py is memory
  only), and reuse the stored result for the same matchup and sheet hashes (cache).
- when the owning modules land, swap the stubs in stages.py for real calls: research
  (G04 get_stat_sheet, with the all-estimate fallback sheet and banner), scripts (A06),
  audio and music (A07), images (A08). Stub output is not saved to the record today.
- seed-sheet lookup ignores `variant`; match variants once variant sheets exist.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.models.matchup import Matchup
from app.models.simulation import FairFight, SimulationResult
from app.pipeline import stages
from app.pipeline.stages import Research, StageFailed, Stubbed
from app.pipeline.store import BattleStore

logger = logging.getLogger(__name__)

STUB = "stub"
SIMULATE_FAILED = "The simulation hit a snag, so there's no verdict this time. Please try again."
RESEARCH_FAILED = "We couldn't look up these fighters this time. Please try again."
RESEARCH_TOO_SLOW = "Looking up the fighters took too long. Please try again."
# No "try again": the same fight would run past its budget again.
SIMULATE_TOO_SLOW = "That fight is too big to simulate quickly. Try smaller numbers."
# What to tell the user when a required stage runs past its budget.
TOO_SLOW = {"research": RESEARCH_TOO_SLOW, "simulate": SIMULATE_TOO_SLOW}
UNEXPECTED = "Something went wrong behind the scenes. Please try again."
CANCELLED = "This battle was stopped before it finished. Please try again."
# Plain notes for stages that ended with a stand-in; the battle carries on without them.
FALLBACK_DETAILS = {
    "summary": "no fair fight within limits",
    "challenger": "No next challenger this time.",
    "script": "No commentary script this time.",
    "audio": "Captions only this time, no announcer voice.",
    "music": "No music this time.",
    "images": "Placeholder shapes instead of pictures this time.",
}

# Running battles; holding a reference keeps a task from being garbage-collected mid-fight.
_tasks: set[asyncio.Task[None]] = set()


# Save a new battle, start running it in the background, and return its id at once.
async def start_battle(matchup: Matchup, store: BattleStore) -> str:
    record = await store.create(matchup)
    task = asyncio.create_task(run_battle(record.battle_id, store))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return record.battle_id


# Run every stage; the battle ends "done" if simulate finished, else "failed".
async def run_battle(battle_id: str, store: BattleStore) -> None:
    record = await store.get(battle_id)
    if record is None:
        # Nothing was saved under this id, so there is no battle to finish.
        logger.error("battle %s not found; nothing to run", battle_id)
        return
    matchup = record.matchup
    stage, simulated, reason = "intake", False, UNEXPECTED
    try:
        # Intake already happened (POST /api/intake) before this battle was created.
        await store.set_stage(battle_id, "intake", "running", STUB)
        await store.set_stage(battle_id, "intake", "done", STUB)

        stage = "research"
        await store.set_stage(battle_id, stage, "running", _looking_up(matchup))
        found = await _required(stage, lambda: stages.research(matchup), RESEARCH_FAILED)
        await store.update(battle_id, stat_sheets=found.sheets)
        await store.set_stage(battle_id, stage, "done", STUB if found.stub else None)

        stage = "simulate"
        await store.set_stage(battle_id, stage, "running")
        result = await _required(stage, lambda: stages.simulate(matchup, found), SIMULATE_FAILED)
        # The verdict goes on the record before any later stage starts.
        await store.update(battle_id, result=result)
        await store.set_stage(battle_id, stage, "done")
        simulated = True

        await _after_simulate(battle_id, store, matchup, found, result)
    except StageFailed as error:
        reason = str(error)
    except asyncio.CancelledError:
        reason = CANCELLED
        raise
    except Exception:
        logger.exception("battle %s crashed (last sequential stage: %s)", battle_id, stage)
    finally:
        # A battle must never stay "running": always write its final status.
        await _finish(battle_id, store, stage, simulated, reason)


# Everything that needs the verdict, all at once; each of these may only end "fallback".
async def _after_simulate(
    battle_id: str, store: BattleStore, matchup: Matchup, found: Research, result: SimulationResult
) -> None:
    async def fair_fight() -> Stubbed[FairFight]:
        return Stubbed(await stages.summary(matchup, found, result))

    async with asyncio.TaskGroup() as group:
        group.create_task(_optional(battle_id, store, "summary", fair_fight, "fair_fight"))
        group.create_task(
            _optional(
                battle_id,
                store,
                "challenger",
                lambda: stages.challenger(found, result),
                "challenger",
            )
        )
        group.create_task(_broadcast(battle_id, store, found, result))
        group.create_task(
            _optional(battle_id, store, "images", lambda: stages.images(matchup, found), "assets")
        )


# Scripts first; once they exist, the announcer's voice and the music in parallel.
async def _broadcast(
    battle_id: str, store: BattleStore, found: Research, result: SimulationResult
) -> None:
    written = await _optional(
        battle_id, store, "script", lambda: stages.scripts(found, result), "scripts"
    )
    lines = written.value if written is not None else []
    async with asyncio.TaskGroup() as group:
        group.create_task(
            _optional(battle_id, store, "audio", lambda: stages.audio(lines), "assets")
        )
        group.create_task(
            _optional(battle_id, store, "music", lambda: stages.music(found), "assets")
        )


# Run a stage the battle can't do without, within its budget; any failure is a StageFailed.
async def _required[T](stage: str, work: Callable[[], Awaitable[T]], failed: str) -> T:
    try:
        return await asyncio.wait_for(work(), stages.STAGE_BUDGETS_S[stage])
    except StageFailed:
        raise
    except TimeoutError as error:
        logger.warning("stage %s ran past its budget", stage)
        raise StageFailed(TOO_SLOW.get(stage, failed)) from error
    except Exception as error:
        logger.exception("stage %s failed", stage)
        raise StageFailed(failed) from error


# Run a stage the battle can do without, within its budget. Real output is saved under
# `field`; stub output is not (the fixtures describe a different battle). On error, timeout,
# or a failed save the stage ends "fallback" with a plain note and None comes back, so one
# stage's trouble never cancels its siblings.
async def _optional[T](
    battle_id: str,
    store: BattleStore,
    stage: str,
    work: Callable[[], Awaitable[Stubbed[T]]],
    field: str,
) -> Stubbed[T] | None:
    await store.set_stage(battle_id, stage, "running")
    try:
        out = await asyncio.wait_for(work(), stages.STAGE_BUDGETS_S[stage])
        if not out.stub:
            await _save(battle_id, store, field, out.value)
        await store.set_stage(battle_id, stage, "done", STUB if out.stub else None)
        return out
    except Exception:
        logger.warning("battle %s: stage %s fell back", battle_id, stage, exc_info=True)
        await store.set_stage(battle_id, stage, "fallback", FALLBACK_DETAILS[stage])
        return None


# Put a stage's real output on the record; assets from several stages are added together.
async def _save(battle_id: str, store: BattleStore, field: str, value: Any) -> None:
    if field == "assets":
        await store.add_assets(battle_id, value)
    else:
        await store.update(battle_id, **{field: value})


# Write the final status. Before a verdict, mark the stage that stopped the battle "failed";
# after one, any stage left unfinished by a crash or cancel ends "fallback".
async def _finish(
    battle_id: str, store: BattleStore, stage: str, simulated: bool, reason: str
) -> None:
    try:
        if not simulated:
            await store.set_stage(battle_id, stage, "failed", reason)
        else:
            await _settle_unfinished(battle_id, store, reason)
    except Exception:
        logger.exception("battle %s: could not mark its stages before finishing", battle_id)
    # Ending the battle also wakes every stream so it sends its "end" event.
    await store.update(battle_id, status="done" if simulated else "failed")


# Mark every stage still pending or running as "fallback".
async def _settle_unfinished(battle_id: str, store: BattleStore, reason: str) -> None:
    record = await store.get(battle_id)
    for change in record.stages if record else []:
        if change.status in ("pending", "running"):
            await store.set_stage(battle_id, change.stage, "fallback", reason)


# A short note shown while research runs.
def _looking_up(matchup: Matchup) -> str:
    return "Looking up " + " and ".join(f.entity for f in matchup.fighters)
