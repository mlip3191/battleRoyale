"""One async function per pipeline stage (ARCHITECTURE §4), plus each stage's time budget.

Each function calls the owning module's public function where it exists. Where the module is
not built yet, a stub returns the matching contract fixture and the result says `stub=True`, so
the orchestrator marks the stage detail "stub". Stubs remaining: audio and music (A07). Research
reads the seed sheets until G04's get_stat_sheet lands.
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field

from app.config import REPO_ROOT, get_settings
from app.media import images as media_images
from app.models.matchup import Matchup
from app.models.media import Asset
from app.models.narration import Script
from app.models.simulation import ChallengerSuggestion, FairFight, SimulationResult
from app.models.stats import StatSheet
from app.narration import writer
from app.narration.facts import build_facts
from app.narration.templates import template_scripts
from app.pipeline import challenger as next_challenger
from app.research.seed_fighters import find_seed_sheet
from app.simulation import engine, fair
from app.simulation.rng import make_seed

logger = logging.getLogger(__name__)

# Time limit per stage in seconds, from the ARCHITECTURE §4 stage budget table (research uses
# the new-fighter budget). The orchestrator reads it on every call, so tests can shrink it.
STAGE_BUDGETS_S: dict[str, float] = {
    "research": 45.0,
    "simulate": 3.0,
    "summary": 5.0,
    "challenger": 10.0,
    "script": 10.0,
    "audio": 60.0,
    "music": 60.0,
    "images": 60.0,
}
# Share of the script budget the model writer gets; the rest leaves time to swap in the
# templates and save them before the orchestrator's cut-off.
SCRIPT_WRITER_SHARE = 0.8

CONTRACT_FIXTURES = REPO_ROOT / "backend" / "tests" / "fixtures" / "contracts"
NOT_FOUND = (
    "We don't have a stat sheet for {name!r} yet. For now, pick one of our ready-made fighters."
)
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

    @property
    def stub(self) -> bool:
        return bool(self.missing_references)


# Find one fighter's stat sheet; the single seam G04's get_stat_sheet will replace.
# variant and raw are tried as described in find_seed_sheet; size references have no
# variant or raw, so they are looked up by the name alone through this same function.
async def lookup_sheet(
    entity: str, variant: str | None = None, raw: str | None = None
) -> StatSheet | None:
    return await asyncio.to_thread(find_seed_sheet, entity, variant, raw)


# Step 2: look up both fighters and any size_reference entities, all at the same time.
async def research(matchup: Matchup) -> Research:
    fighters = matchup.fighters
    references = [f.size_reference for f in fighters]
    found = await asyncio.gather(
        *(lookup_sheet(f.entity, f.variant, f.raw) for f in fighters),
        *(lookup_sheet(ref) for ref in references if ref is not None),
    )
    sheets: list[StatSheet] = []
    for fighter, sheet in zip(fighters, found[: len(fighters)], strict=True):
        if sheet is None:
            raise StageFailed(NOT_FOUND.format(name=_typed_name(fighter.entity, fighter.variant)))
        sheets.append(sheet)
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
    return Research(sheets, reference_sheets, missing)


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
    return await asyncio.to_thread(
        engine.run,
        simulation_matchup(matchup, found),
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
    pick, fallback = await next_challenger.suggest(found.sheets, result, matchup.terrain)
    return Stubbed(pick, fallback=fallback)


# Steps 4–5: intro, play-by-play, and outro scripts (narration/writer.py, A06). The outro's
# fair-fight line needs `fair_fight` (None if the summary gave nothing). A script the model could
# not write comes back as its template (fallback=True); then the stage ends "fallback".
# A slow model must not leave the battle silent: if the writer runs past its share of the
# stage budget, all three template scripts are used instead (also fallback=True).
async def scripts(
    matchup: Matchup,
    found: Research,
    result: SimulationResult,
    fair_fight: FairFight | None = None,
) -> Stubbed[list[Script]]:
    counts = [fighter.count for fighter in matchup.fighters]
    deadline = STAGE_BUDGETS_S["script"] * SCRIPT_WRITER_SHARE
    try:
        written = await asyncio.wait_for(
            writer.write_scripts(found.sheets, result, fair_fight, counts=counts), deadline
        )
    except TimeoutError:
        logger.warning("script writer ran past %.1fs; using the template scripts", deadline)
        facts = build_facts(found.sheets, result, fair_fight, counts)
        written = template_scripts(facts, result)
    return Stubbed(written, fallback=any(script.fallback for script in written))


# Step 5 (stub until A07): the announcer's voice for the scripts.
async def audio(written: list[Script]) -> Stubbed[list[Asset]]:
    return Stubbed([_asset_fixture()], stub=True)


# Step 5 (stub until A07): the soundtrack.
async def music(found: Research) -> Stubbed[list[Asset]]:
    return Stubbed([_asset_fixture()], stub=True)


# Step 6: fighter sprites and the battlefield (media/images.py, A08). Pictures that could not be
# drawn come back as placeholders (fallback=True, no URL); then the stage ends "fallback".
async def images(matchup: Matchup, found: Research) -> Stubbed[list[Asset]]:
    assets = await media_images.make_images(matchup, found.sheets)
    return Stubbed(assets, fallback=any(asset.fallback for asset in assets))


def _asset_fixture() -> Asset:
    return Asset.model_validate(_fixture("asset.json"))


# Read one contract fixture (the stand-in output of a stage that isn't built yet).
def _fixture(name: str) -> object:
    return json.loads((CONTRACT_FIXTURES / name).read_text(encoding="utf-8"))
