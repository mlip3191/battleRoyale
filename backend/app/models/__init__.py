"""Shared contracts used by every lane (ARCHITECTURE §5). Changes need a contract-change issue."""

from typing import Any

from pydantic import BaseModel

from app.models.api import BattleCreated, FighterMatch, ShowcaseBattle
from app.models.battle import BattleRecord, StageStatus
from app.models.matchup import FighterRequest, IntakeResult, Matchup
from app.models.media import Asset
from app.models.narration import Script, ScriptLine
from app.models.simulation import (
    ChallengerSuggestion,
    EventType,
    FairFight,
    FightEvent,
    SimulationResult,
)
from app.models.stats import (
    Ability,
    Body,
    Confidence,
    Habitat,
    LoreProfile,
    Source,
    StatName,
    StatSheet,
    StatValue,
)
from app.models.terrain import Terrain

# Every contract model, in ARCHITECTURE §5 order; schema export and TS generation use this list.
CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    FighterRequest,
    Matchup,
    IntakeResult,
    Source,
    StatValue,
    LoreProfile,
    StatSheet,
    FightEvent,
    SimulationResult,
    FairFight,
    ChallengerSuggestion,
    ScriptLine,
    Script,
    Asset,
    StageStatus,
    BattleRecord,
    BattleCreated,
    ShowcaseBattle,
    FighterMatch,
)


# JSON Schemas for every contract (and the enums they use), keyed by name, for OpenAPI components.
def contract_schemas() -> dict[str, Any]:
    schemas: dict[str, Any] = {}
    for model in CONTRACT_MODELS:
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        schemas.update(schema.pop("$defs", {}))
        schemas[model.__name__] = schema
    return dict(sorted(schemas.items()))


__all__ = [
    "CONTRACT_MODELS",
    "Ability",
    "Asset",
    "BattleCreated",
    "BattleRecord",
    "Body",
    "ChallengerSuggestion",
    "Confidence",
    "EventType",
    "FairFight",
    "FightEvent",
    "FighterMatch",
    "FighterRequest",
    "Habitat",
    "IntakeResult",
    "LoreProfile",
    "Matchup",
    "Script",
    "ScriptLine",
    "ShowcaseBattle",
    "SimulationResult",
    "Source",
    "StageStatus",
    "StatName",
    "StatSheet",
    "StatValue",
    "Terrain",
    "contract_schemas",
]
