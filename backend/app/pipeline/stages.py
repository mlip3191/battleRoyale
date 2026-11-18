"""One async function per pipeline stage (ARCHITECTURE §4), plus each stage's time budget.

Each function calls the owning module's public function. A stage that reports `stub=True`
gets the stage detail "stub" and its output is not saved. No stage in this file is a stub any
more. Research uses G04's sheet lookup: seed sheet, cached sheet, or a newly built one; a
size_reference with no sheet is listed in `Research.missing_references`. A fighter with no sheet
and no legend fights on an all-estimate sheet from code defaults (#345) and is listed in
`Research.estimated`. Either way research then ends "fallback" with a plain note.
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from typing import cast

from app.config import get_settings
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.media import audio as media_audio
from app.media import images as media_images
from app.models.matchup import FighterRequest, Matchup
from app.models.media import Asset
from app.models.narration import Script
from app.models.simulation import ChallengerSuggestion, FairFight, SimulationResult
from app.models.stats import StatSheet
from app.narration import writer
from app.narration.facts import build_facts
from app.narration.templates import template_scripts
from app.pipeline import challenger as next_challenger
from app.providers.registry import get_provider
from app.research.estimate_sheet import estimate_sheet
from app.research.seed_fighters import find_seed_fighter
from app.research.sheet_store import resolve_legend, resolve_stat_sheet
from app.simulation import engine, fair
from app.simulation.rng import make_seed

logger = logging.getLogger(__name__)

# Time limit per stage in seconds, from the ARCHITECTURE §4 stage budget table (research uses
# the new-fighter budget). The orchestrator reads it on every call, so tests can shrink it.
STAGE_BUDGETS_S: dict[str, float] = {
    "research": 45.0,
    # 15 s, not 3 s (D-63, #359): 1,000 runs plus the deciding-factor analysis took up to 6.9 s
    # for showcase battle 1 on a Windows laptop, and the limit keeps about 2x headroom.
    "simulate": 15.0,
    "summary": 5.0,
    "challenger": 10.0,
    # 15 s, not 10 s (D-66, #363): a play-by-play rejected on its first try needs room for its
    # one retry, so each script gets about 10.5 s instead of 7 s.
    "script": 15.0,
    "audio": 60.0,
    "music": 60.0,
    "images": 60.0,
}
# Share of the script budget the model writer gets; the rest leaves time to swap in the
# templates and save them before the orchestrator's cut-off.
SCRIPT_WRITER_SHARE = 0.8
# Share each script gets on its own: a script past it is its template, and the ones that
# finished keep the model's lines (#363). Below the writer's share, so it ends first.
SCRIPT_CALL_SHARE = 0.7
# Share of the audio and music budgets the providers get; the rest leaves time to save.
MEDIA_PROVIDER_SHARE = 0.8
# The scripts that each get a narration file, in broadcast order.
NARRATED_SCRIPTS = ("intro", "play_by_play", "outro")

NOT_FOUND = (
    "We don't have a stat sheet for {name!r} yet. For now, pick one of our ready-made fighters."
)
LEGEND_BLOCKED = (
    "We don't have a stat sheet for {name!r}, and we couldn't find a legend by that name to "
    'model. Pick one of our ready-made fighters, or a mythical creature like "a griffin".'
)
LEGEND_UNAVAILABLE = "We couldn't look up {name!r} right now. Please try again in a minute."
# Age and sex words used as labels by mock intake; they are not shown in the miss message.
_LABEL_WORDS = frozenset({"adult", "male", "female", "juvenile", "baby", "young"})


def _typed_name(entity: str, variant: str | None) -> str:
    """The fighter as the user would recognise it: descriptive variant plus entity."""
    kind = (variant or "").strip()
    if kind and any(part not in _LABEL_WORDS for part in kind.lower().split()):
        if kind.lower().split()[-len(entity.split()) :] == entity.lower().split():
            return kind
        return f"{kind} {entity}"
    return entity


class StageFailed(Exception):
    """A stage could not finish; the message is plain English for the user."""


@dataclass(frozen=True)
class Stubbed[T]:
    """What a stage produced, and whether it came from a stand-in (stage detail "stub")."""

    value: T
    stub: bool = False
    fallback: bool = False
    """The stage used its fallback path: it ends "fallback"; a value that isn't None is saved."""


@dataclass(frozen=True)
class Research:
    """The sheets for both sides, plus each side's size_reference sheet (None if unset)."""

    sheets: list[StatSheet]
    reference_sheets: list[StatSheet | None]
    missing_references: list[str] = field(default_factory=list)
    """size_reference names with no sheet yet; those sides fight at their normal size."""
    estimated: list[str] = field(default_factory=list)
    """Fighters (as typed) with no sheet at all; they fight on all-estimate sheets (#345)."""


# Find one fighter's stat sheet (G04): seed sheet, cached sheet, or one built and cached now.
# variant and raw are tried as described in find_seed_sheet; size references have no
# variant or raw, so they are looked up by the name alone through this same function.
async def lookup_sheet(
    entity: str, variant: str | None = None, raw: str | None = None
) -> StatSheet | None:
    connection = connect()
    try:
        apply_migrations(connection)
        providers = (get_provider("chat"), get_provider("embedder"), get_provider("reranker"))
        return await resolve_stat_sheet(connection, providers, entity, variant, raw)
    finally:
        connection.close()


# A fighter's sheet: lookup_sheet first, then, for a name off the seed list only, a legend
# modeled from its article (G09). None when there is neither. Raises StageFailed with the reason
# when a seed fighter's build failed, a legend is blocked, or the legend lookup is down.
async def find_fighter(fighter: FighterRequest) -> StatSheet | None:
    sheet = await lookup_sheet(fighter.entity, fighter.variant, fighter.raw)
    if sheet is not None:
        return sheet
    name = _typed_name(fighter.entity, fighter.variant)
    if find_seed_fighter(fighter.entity, fighter.variant, fighter.raw) is not None:
        raise StageFailed(NOT_FOUND.format(name=name))  # a seed fighter's build failed
    connection = connect()
    try:
        apply_migrations(connection)
        legend = await resolve_legend(connection, get_provider("chat"), fighter.entity)
    finally:
        connection.close()
    if legend is None or isinstance(legend, StatSheet):
        return legend
    raise StageFailed((LEGEND_BLOCKED if legend.blocked else LEGEND_UNAVAILABLE).format(name=name))


# find_fighter's sheet, or an all-estimate sheet from code defaults when there is none (#345).
# The second value is True for the estimate. A block or failure from find_fighter still raises,
# so the estimate never gets past a safety block. The estimate is not cached in the sheet store.
async def lookup_fighter_or_estimate(fighter: FighterRequest) -> tuple[StatSheet, bool]:
    sheet = await find_fighter(fighter)
    if sheet is not None:
        return sheet, False
    return estimate_sheet(_typed_name(fighter.entity, fighter.variant)), True


# A fighter's sheet for a battle: found, or the all-estimate fallback (see the function above).
async def lookup_fighter(fighter: FighterRequest) -> StatSheet:
    sheet, _ = await lookup_fighter_or_estimate(fighter)
    return sheet


# Step 2: look up both fighters and any size_reference entities, all at the same time.
async def research(matchup: Matchup) -> Research:
    fighters = matchup.fighters
    references = [f.size_reference for f in fighters]
    found = await asyncio.gather(
        *(lookup_fighter_or_estimate(f) for f in fighters),
        *(lookup_sheet(ref) for ref in references if ref is not None),
    )
    looked_up = cast(list[tuple[StatSheet, bool]], list(found[: len(fighters)]))
    sheets = [sheet for sheet, _ in looked_up]
    estimated = [
        _typed_name(f.entity, f.variant)
        for f, (_, is_estimate) in zip(fighters, looked_up, strict=True)
        if is_estimate
    ]
    found_refs = iter(found[len(fighters) :])
    reference_sheets: list[StatSheet | None] = []
    missing: list[str] = []
    for ref in references:
        if ref is None:
            reference_sheets.append(None)
            continue
        sheet = next(found_refs)
        reference_sheets.append(sheet)
        if sheet is None:
            missing.append(ref)
    return Research(sheets, reference_sheets, missing, estimated)


# The matchup the engine sees: a size swap whose reference has no sheet fights at normal size.
def simulation_matchup(matchup: Matchup, found: Research) -> Matchup:
    if not found.missing_references:
        return matchup
    fighters = [
        f.model_copy(update={"size_reference": None}) if ref is None else f
        for f, ref in zip(matchup.fighters, found.reference_sheets, strict=True)
    ]
    return matchup.model_copy(update={"fighters": fighters})


# The repeat-battle cache key: the simulation seed (normalized matchup, both sheet hashes,
# ENGINE_VERSION; ARCHITECTURE §8) plus what else changes the verdict: the size-reference
# sheets, a hash of each whole sheet (sheet_hash covers only stats; the engine also reads
# body, weapons, habitat, and lore), and the number of runs.
def cache_key(matchup: Matchup, found: Research) -> str:
    seed = make_seed(
        simulation_matchup(matchup, found), found.sheets[0].sheet_hash, found.sheets[1].sheet_hash
    )
    references = ",".join(s.sheet_hash if s else "-" for s in found.reference_sheets)
    whole = ",".join(
        hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()
        for s in (*found.sheets, *(r for r in found.reference_sheets if r))
    )
    text = f"seed={seed}|refs={references}|sheets={whole}|runs={get_settings().sim_runs}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Step 3: the real engine, off the event loop so other battles and streams keep moving.
# Functions run via to_thread must stay pure and never write to the store: a thread that
# ran past its budget keeps running in the background after the stage has moved on.
async def simulate(matchup: Matchup, found: Research) -> SimulationResult:
    engine_matchup = simulation_matchup(matchup, found)
    if engine.too_big_for_venom(engine_matchup, found.sheets, found.reference_sheets):
        # A venomous crowd below the swarm ceiling runs one by one for 20 to 30 s (#330, D-61).
        # Answer "too big to simulate quickly" now (the orchestrator maps a TimeoutError to that
        # message) instead of burning a thread after the stage has already given up.
        raise TimeoutError("venomous fight too big to run one by one")
    return await asyncio.to_thread(
        engine.run,
        engine_matchup,
        found.sheets,
        reference_sheets=found.reference_sheets,
    )


# Step 7: the fair-fight search (code only). The summary numbers are not stored on the
# BattleRecord; readers derive them from the saved result with simulation.summary.
# Same rule as simulate: the threaded search must stay pure (no store writes).
async def summary(matchup: Matchup, found: Research, result: SimulationResult) -> FairFight:
    return await asyncio.to_thread(
        fair.fair_fight,
        simulation_matchup(matchup, found),
        found.sheets,
        result,
        found.reference_sheets,
    )


# Step 8: the next challenger from seed and cached fighters only (pipeline/challenger.py).
async def challenger(
    matchup: Matchup, found: Research, result: SimulationResult
) -> Stubbed[ChallengerSuggestion | None]:
    # The engine's own matchup, so the winner duels as the battle was fought (count and size).
    pick, fallback = await next_challenger.suggest(
        found.sheets,
        result,
        matchup.terrain,
        matchup=simulation_matchup(matchup, found),
        reference_sheets=found.reference_sheets,
    )
    return Stubbed(pick, fallback=fallback)


# Steps 4–5: intro, play-by-play, and outro scripts (narration/writer.py, A06). The outro's
# fair-fight line needs `fair_fight` (None if the summary gave nothing). A script the model could
# not write comes back as its template (fallback=True); then the stage ends "fallback".
# A slow model must not leave the battle silent: a script past its own share of the stage budget
# is its template (#363), and if the writer as a whole runs past its share, all three template
# scripts are used instead (also fallback=True).
async def scripts(
    matchup: Matchup,
    found: Research,
    result: SimulationResult,
    fair_fight: FairFight | None = None,
) -> Stubbed[list[Script]]:
    counts = [fighter.count for fighter in matchup.fighters]
    deadline = STAGE_BUDGETS_S["script"] * SCRIPT_WRITER_SHARE
    per_script = STAGE_BUDGETS_S["script"] * SCRIPT_CALL_SHARE
    try:
        written = await asyncio.wait_for(
            writer.write_scripts(
                found.sheets, result, fair_fight, counts=counts, deadline_s=per_script
            ),
            deadline,
        )
    except TimeoutError:
        logger.warning("script writer ran past %.1fs; using the template scripts", deadline)
        facts = build_facts(found.sheets, result, fair_fight, counts)
        written = template_scripts(facts, result)
    return Stubbed(written, fallback=any(script.fallback for script in written))


# Step 5: the announcer's voice, one file per script (media/audio.py, A07). The provider gets
# a share of the stage budget, so a slow one is cut off here and the stage still ends in time.
# Fewer than three files is a fallback: with none the battle is captions only (value None);
# with some, the saved files are kept and the missing parts are silent.
async def audio(written: list[Script]) -> Stubbed[list[Asset] | None]:
    if not written:
        return Stubbed(None, fallback=True)
    deadline = STAGE_BUDGETS_S["audio"] * MEDIA_PROVIDER_SHARE
    assets = await media_audio.make_audio(written, timeout_s=deadline)
    if not assets:
        return Stubbed(None, fallback=True)
    missing = len(assets) < len(NARRATED_SCRIPTS) or len(assets) < len(written)
    return Stubbed(assets, fallback=missing or any(asset.fallback for asset in assets))


# Step 5: the soundtrack (media/audio.py, A07), with the same share of its budget. No track
# means the stage ends "fallback" with nothing saved.
async def music(
    matchup: Matchup, found: Research, result: SimulationResult
) -> Stubbed[list[Asset] | None]:
    deadline = STAGE_BUDGETS_S["music"] * MEDIA_PROVIDER_SHARE
    track = await media_audio.make_music(matchup, result, found.sheets, timeout_s=deadline)
    if track is None:
        return Stubbed(None, fallback=True)
    return Stubbed([track], fallback=track.fallback)


# Step 6: fighter sprites and the battlefield (media/images.py, A08). Pictures that could not be
# drawn come back as placeholders (fallback=True, no URL); then the stage ends "fallback".
async def images(matchup: Matchup, found: Research) -> Stubbed[list[Asset]]:
    assets = await media_images.make_images(matchup, found.sheets)
    return Stubbed(assets, fallback=any(asset.fallback for asset in assets))
