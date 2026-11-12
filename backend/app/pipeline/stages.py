"""One async function per pipeline stage (ARCHITECTURE §4), plus each stage's time budget.

Each function calls the owning module's public function where it exists. Where the module is
not built yet, a stub returns the matching contract fixture and the result says `stub=True`, so
the orchestrator marks the stage detail "stub". Stubs remaining: challenger (A05 part 3),
scripts (A06), audio and music (A07), images (A08). Research reads the seed sheets until G04's
get_stat_sheet lands.
"""

import asyncio
import json
from dataclasses import dataclass, field

from app.config import REPO_ROOT
from app.models.matchup import Matchup
from app.models.media import Asset
from app.models.narration import Script
from app.models.simulation import ChallengerSuggestion, FairFight, SimulationResult
from app.models.stats import StatSheet
from app.research.seed_fighters import find_seed_sheet
from app.simulation import engine, fair

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

CONTRACT_FIXTURES = REPO_ROOT / "backend" / "tests" / "fixtures" / "contracts"
NOT_FOUND = (
    "We don't have a stat sheet for {name!r} yet. For now, pick one of our ready-made fighters."
)


class StageFailed(Exception):
    """A stage could not finish; the message is plain English for the user."""


@dataclass(frozen=True)
class Stubbed[T]:
    """What a stage produced, and whether it came from a stand-in (stage detail "stub")."""

    value: T
    stub: bool = False


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
async def lookup_sheet(entity: str) -> StatSheet | None:
    return await asyncio.to_thread(find_seed_sheet, entity)


# Step 2: look up both fighters and any size_reference entities, all at the same time.
async def research(matchup: Matchup) -> Research:
    fighters = [f.entity for f in matchup.fighters]
    references = [f.size_reference for f in matchup.fighters]
    names = fighters + [ref for ref in references if ref is not None]
    found = await asyncio.gather(*(lookup_sheet(name) for name in names))
    by_name = dict(zip(names, found, strict=True))
    sheets = []
    for name in fighters:
        sheet = by_name[name]
        if sheet is None:
            raise StageFailed(NOT_FOUND.format(name=name))
        sheets.append(sheet)
    reference_sheets = [None if ref is None else by_name[ref] for ref in references]
    missing = [
        ref for ref, sheet in zip(references, reference_sheets, strict=True) if ref and not sheet
    ]
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


# Step 8 (stub until A05 part 3): the next challenger.
async def challenger(found: Research, result: SimulationResult) -> Stubbed[ChallengerSuggestion]:
    fixture = _fixture("challenger-suggestion.json")
    return Stubbed(ChallengerSuggestion.model_validate(fixture), stub=True)


# Steps 4–5 (stub until A06): intro, play-by-play, and outro scripts.
async def scripts(
    found: Research, result: SimulationResult, fair_fight: FairFight | None = None
) -> Stubbed[list[Script]]:
    return Stubbed([Script.model_validate(_fixture("script.json"))], stub=True)


# Step 5 (stub until A07): the announcer's voice for the scripts.
async def audio(written: list[Script]) -> Stubbed[list[Asset]]:
    return Stubbed([_asset_fixture()], stub=True)


# Step 5 (stub until A07): the soundtrack.
async def music(found: Research) -> Stubbed[list[Asset]]:
    return Stubbed([_asset_fixture()], stub=True)


# Step 6 (stub until A08): fighter sprites and the battlefield.
async def images(matchup: Matchup, found: Research) -> Stubbed[list[Asset]]:
    return Stubbed([_asset_fixture()], stub=True)


def _asset_fixture() -> Asset:
    return Asset.model_validate(_fixture("asset.json"))


# Read one contract fixture (the stand-in output of a stage that isn't built yet).
def _fixture(name: str) -> object:
    return json.loads((CONTRACT_FIXTURES / name).read_text(encoding="utf-8"))
