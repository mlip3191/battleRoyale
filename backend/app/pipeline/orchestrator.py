"""The battle orchestrator (A05): runs the stages in ARCHITECTURE §4 order and records progress.

Flow: research (both fighters and any size_reference entities, in parallel) -> simulate ->
then in parallel: summary + fair fight, challenger, images, and the broadcast (scripts once the
summary ends, then audio and music in parallel). Scripts wait for the summary because the fair
fight is an input to write_scripts (the outro's fair-fight line); they get None if the summary
fell back. Images and challenger start right after simulate (ARCHITECTURE §4), not after the
scripts. Each announcer file goes on the record as soon as it is made, the intro's first, while
the battle is still running (#592). The verdict is saved before any of those start, so it never
waits for media. Every stage has a time limit (`stages.STAGE_BUDGETS_S`). Research or
simulate failing fails the battle; any later stage failing ends "fallback" and the battle
goes on. The battle is "done" if and only if simulate succeeded, and it never stays "running".
Repeat battles: after research, a finished battle with the same cache key (`stages.cache_key`)
lends its verdict, plus its fair fight and challenger when it has them; each copied stage ends
"done" with detail "cached", and one it lacks runs fresh. Stub output is not saved to the
record. Research finds sheets through G04's `resolve_stat_sheet` (variant plus entity first).
A size_reference with no sheet ends research "fallback" with a plain note; that side fights
at its normal size and the battle goes on. A fighter with no sheet and no legend fights on an
all-estimate sheet from code defaults (#345): research ends "fallback" with a note naming it,
and the battle goes on. A blocked legend, an unavailable legend lookup, or a seed fighter whose
build failed still fails research.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from app.models.battle import BattleRecord
from app.models.matchup import FighterRequest, Matchup
from app.models.media import Asset
from app.models.simulation import ChallengerSuggestion, FairFight, SimulationResult
from app.pipeline import stages
from app.pipeline.stages import Research, StageFailed, Stubbed
from app.pipeline.store import BattleStore
from app.research.mythical import find_creature
from app.research.seed_fighters import find_seed_fighter
from app.research.sheet_store import LEGEND_BUDGET_S

logger = logging.getLogger(__name__)

STUB = "stub"
# Added to the research line when a fighter may be a new legend (#324), from its time limit.
LEGEND_NOTE = f" (a legend can take up to {int(LEGEND_BUDGET_S)} s)"
CACHED = "cached"  # detail for a stage copied from an earlier, identical battle
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
    "summary": "The fair-fight search didn't finish this time.",
    "challenger": "No next challenger this time.",
    "script": "No commentary script this time.",
    "audio": "Captions only this time, no announcer voice.",
    "music": "No music this time.",
    "images": "Placeholder shapes instead of pictures this time.",
}
# What the results page's fair-fight box says when the search was cut off or failed (#509). It
# must not claim that no fair fight exists: that is only said by a search that finished.
FAIR_FIGHT_UNFINISHED = "We couldn't work out a fair fight in time for this one."
# Notes for a stage whose fallback path still produced something worth saving.
FALLBACK_WITH_VALUE = {
    "challenger": "Next challenger picked by quick tests of seed fighters this time.",
    "script": "Some of the commentary used the template script this time.",
    "audio": "Some parts have captions only this time, no announcer voice.",
    "images": "Placeholder shapes for some of the pictures this time.",
}
# For a stage with a saved stand-in value but no note of its own above.
FALLBACK_WITH_VALUE_GENERIC = "A quick stand-in was used for this step this time."
# Research note when a size_reference has no sheet yet; {names} are the quoted references.
MISSING_REFERENCE = "No size reference for {names} yet, so that side fights at its normal size."
MISSING_REFERENCES = "No size reference for {names} yet, so both sides fight at their normal size."
# Research note when a fighter has no sheet and fights on code estimates (#345).
ESTIMATED_FIGHTER = "We have no stat sheet for {names}, so its stats are estimates."
ESTIMATED_FIGHTERS = "We have no stat sheet for {names}, so their stats are estimates."
# Research note when a fighter's research outlived the battle's wait (#622). The Results page
# shows a rematch button when the note contains RESEARCH_REMATCH, so keep that wording in step
# with REMATCH_PROMISE in frontend/src/components/Verdict.tsx.
RESEARCH_REMATCH = "A rematch will use sourced stats."
RESEARCHING_FIGHTER = (
    "Research on {names} is still running, so its stats here are estimates. " + RESEARCH_REMATCH
)
RESEARCHING_FIGHTERS = (
    "Research on {names} is still running, so their stats here are estimates. " + RESEARCH_REMATCH
)

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
        # Intake really ran before this battle was created (POST /api/intake and the safety
        # gate), so the stage is recorded as done here.
        await store.set_stage(battle_id, "intake", "running")
        await store.set_stage(battle_id, "intake", "done")

        stage = "research"
        await store.set_stage(battle_id, stage, "running", _looking_up(matchup))
        found = await _required(stage, lambda: stages.research(matchup), RESEARCH_FAILED)
        await store.update(battle_id, stat_sheets=found.sheets)
        if found.estimated or found.researching or found.missing_references:
            await store.set_stage(battle_id, stage, "fallback", _research_note(found))
        else:
            await store.set_stage(battle_id, stage, "done")

        # Same matchup, same sheets, same engine: reuse a finished battle's verdict.
        key = stages.cache_key(matchup, found)
        await store.set_cache_key(battle_id, key)
        cached = await store.find_cached(key)

        stage = "simulate"
        await store.set_stage(battle_id, stage, "running")
        if cached is not None and cached.result is not None:
            result = cached.result
        else:
            cached = None
            result = await _required(
                stage, lambda: stages.simulate(matchup, found), SIMULATE_FAILED
            )
        # The verdict goes on the record before any later stage starts.
        await store.update(battle_id, result=result)
        await store.set_stage(battle_id, stage, "done", CACHED if cached else None)
        simulated = True

        await _after_simulate(battle_id, store, matchup, found, result, cached)
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
# With a cached battle, a saved fair fight or challenger is copied instead of worked out
# again; one the cached battle lacks (None) is worked out fresh. A copied value can come
# from a stage that ended "fallback"; it is still marked "cached", which is fine for a
# repeat battle. A saved "couldn't work it out in time" box is the exception: it is not a result,
# so that search runs again.
async def _after_simulate(
    battle_id: str,
    store: BattleStore,
    matchup: Matchup,
    found: Research,
    result: SimulationResult,
    cached: BattleRecord | None = None,
) -> None:
    saved_fair = cached.fair_fight if cached is not None else None
    if saved_fair is not None and saved_fair.message.startswith(FAIR_FIGHT_UNFINISHED):
        saved_fair = None  # a cut-off search is retried, not copied (#509)
    saved_next = cached.challenger if cached is not None else None

    async def fair_fight() -> Stubbed[FairFight | None]:
        if saved_fair is not None:
            return Stubbed(saved_fair)
        return Stubbed(await stages.summary(matchup, found, result))

    async def challenger() -> Stubbed[ChallengerSuggestion | None]:
        if saved_next is not None:
            return Stubbed(saved_next)
        return await stages.challenger(matchup, found, result)

    fair_done = CACHED if saved_fair is not None else None
    next_done = CACHED if saved_next is not None else None
    async with asyncio.TaskGroup() as group:
        summary = group.create_task(
            _optional(battle_id, store, "summary", fair_fight, "fair_fight", fair_done)
        )
        group.create_task(
            _optional(battle_id, store, "challenger", challenger, "challenger", next_done)
        )
        group.create_task(_broadcast(battle_id, store, matchup, found, result, summary))
        group.create_task(
            _optional(battle_id, store, "images", lambda: stages.images(matchup, found), "assets")
        )


# Scripts once the summary ends (the outro needs the fair fight); then the announcer's voice
# and the music in parallel. The summary is awaited before the script stage starts its own
# budget, so a slow fair fight never eats the script's time.
async def _broadcast(
    battle_id: str,
    store: BattleStore,
    matchup: Matchup,
    found: Research,
    result: SimulationResult,
    summary: Awaitable[Stubbed[FairFight | None] | None],
) -> None:
    summarized = await summary
    fair = summarized.value if summarized is not None and not summarized.stub else None
    written = await _optional(
        battle_id,
        store,
        "script",
        lambda: stages.scripts(matchup, found, result, fair),
        "scripts",
    )
    lines = written.value if written is not None else []
    shown: set[str] = set()  # ids of the voice files already on the record

    # Each voice file goes on the record as soon as it is made, the intro's first, so the show
    # can start while the rest is recorded (#592).
    async def publish(asset: Asset) -> None:
        await store.add_assets(battle_id, [asset])
        shown.add(asset.asset_id)

    # The audio stage; when it ends, only the files not already on the record are added.
    async def voice() -> Stubbed[list[Asset] | None]:
        out = await stages.audio(lines, on_ready=publish)
        if out.value is None:
            return out
        return replace(out, value=[a for a in out.value if a.asset_id not in shown])

    async with asyncio.TaskGroup() as group:
        group.create_task(_optional(battle_id, store, "audio", voice, "assets"))
        group.create_task(
            _optional(
                battle_id, store, "music", lambda: stages.music(matchup, found, result), "assets"
            )
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
# stage's trouble never cancels its siblings. A stage that reports its own fallback also ends
# "fallback", keeping any value it still found. `done_detail` is the note for a real "done".
async def _optional[T](
    battle_id: str,
    store: BattleStore,
    stage: str,
    work: Callable[[], Awaitable[Stubbed[T]]],
    field: str,
    done_detail: str | None = None,
) -> Stubbed[T] | None:
    await store.set_stage(battle_id, stage, "running")
    try:
        out = await asyncio.wait_for(work(), stages.STAGE_BUDGETS_S[stage])
        if not out.stub and out.value is not None:
            await _save(battle_id, store, field, out.value)
        if out.fallback:
            note = (
                FALLBACK_DETAILS[stage]
                if out.value is None
                else FALLBACK_WITH_VALUE.get(stage, FALLBACK_WITH_VALUE_GENERIC)
            )
            await store.set_stage(battle_id, stage, "fallback", note)
        else:
            await store.set_stage(battle_id, stage, "done", STUB if out.stub else done_detail)
        return out
    except Exception:
        logger.warning("battle %s: stage %s fell back", battle_id, stage, exc_info=True)
        if stage == "summary":
            await _save_unfinished_fair_fight(battle_id, store)
        await store.set_stage(battle_id, stage, "fallback", FALLBACK_DETAILS[stage])
        return None


# A fair-fight search that was cut off still gets a box on the results page, saying so (#509).
async def _save_unfinished_fair_fight(battle_id: str, store: BattleStore) -> None:
    unfinished = FairFight(
        varied_side=0, count=None, win_prob_at_count=None, message=FAIR_FIGHT_UNFINISHED
    )
    try:
        await _save(battle_id, store, "fair_fight", unfinished)
    except Exception:
        logger.warning(
            "battle %s: could not save the unfinished fair fight", battle_id, exc_info=True
        )


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


# The research "fallback" note: fighters still being researched, then estimated fighters, then
# missing size references.
def _research_note(found: Research) -> str:
    notes = []
    if found.researching:
        notes.append(_names_note(found.researching, RESEARCHING_FIGHTER, RESEARCHING_FIGHTERS))
    if found.estimated:
        notes.append(_estimated_note(found.estimated))
    if found.missing_references:
        notes.append(_missing_reference_note(found.missing_references))
    return " ".join(notes)


# The research note naming each fighter that fights on estimates, e.g. 'wolverine'.
def _estimated_note(names: list[str]) -> str:
    return _names_note(names, ESTIMATED_FIGHTER, ESTIMATED_FIGHTERS)


# A note naming each fighter once ('moose' and 'warthog'), with the one- or two-name wording.
def _names_note(names: list[str], one: str, two: str) -> str:
    unique = list(dict.fromkeys(names))  # at most two sides; the same name twice is one sheet
    template = one if len(unique) == 1 else two
    return template.format(names=" and ".join(repr(name) for name in unique))


# The research note naming each size_reference with no sheet, e.g. 'a school bus'.
def _missing_reference_note(names: list[str]) -> str:
    joined = " or ".join(repr(name) for name in dict.fromkeys(names))  # at most two sides
    template = MISSING_REFERENCE if len(names) == 1 else MISSING_REFERENCES
    return template.format(names=joined)


# A short note shown while research runs.
def _looking_up(matchup: Matchup) -> str:
    names = "Looking up " + " and ".join(f.entity for f in matchup.fighters)
    return names + LEGEND_NOTE if any(_may_be_a_new_legend(f) for f in matchup.fighters) else names


# A fighter that's neither a seed fighter nor a creature in mythical.yaml may be a legend that
# has to be fetched and modeled, which can take most of research's time (#324).
def _may_be_a_new_legend(fighter: FighterRequest) -> bool:
    if find_creature(fighter.entity) is not None:
        return False
    return find_seed_fighter(fighter.entity, fighter.variant, fighter.raw) is None
