"""Every contract fixture validates against its model, and every model has a fixture."""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.models import (
    CONTRACT_MODELS,
    Asset,
    BattleCreated,
    BattleRecord,
    ChallengerSuggestion,
    FairFight,
    FighterMatch,
    FighterRequest,
    FightEvent,
    IntakeResult,
    LoreProfile,
    Matchup,
    Script,
    ScriptLine,
    ShowcaseBattle,
    SimulationResult,
    Source,
    StageStatus,
    StatSheet,
    StatValue,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"

# Fixture file -> the model it must validate against.
FIXTURE_MODELS: dict[str, type[BaseModel]] = {
    "fighter-request.json": FighterRequest,
    "matchup.json": Matchup,
    "intake-result.json": IntakeResult,
    "source.json": Source,
    "stat-value.json": StatValue,
    "lore-profile.json": LoreProfile,
    "stat-sheet.json": StatSheet,
    "stat-sheet-gray-wolf.json": StatSheet,
    "stat-sheet-toaster.json": StatSheet,
    "stat-sheet-dragon.json": StatSheet,
    "fight-event.json": FightEvent,
    "simulation-result.json": SimulationResult,
    "fair-fight.json": FairFight,
    "challenger-suggestion.json": ChallengerSuggestion,
    "script-line.json": ScriptLine,
    "script.json": Script,
    "asset.json": Asset,
    "stage-status.json": StageStatus,
    "battle-record-running.json": BattleRecord,
    "battle-record-done.json": BattleRecord,
    "battle-created.json": BattleCreated,
    "showcase-battle.json": ShowcaseBattle,
    "fighter-match.json": FighterMatch,
}


# Load one fixture as plain JSON data.
def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(FIXTURE_MODELS))
def test_fixture_validates(name: str) -> None:
    FIXTURE_MODELS[name].model_validate(load(name))


def test_every_fixture_file_is_checked() -> None:
    assert {p.name for p in FIXTURES.glob("*.json")} == set(FIXTURE_MODELS)


def test_every_model_has_a_fixture() -> None:
    assert set(CONTRACT_MODELS) == set(FIXTURE_MODELS.values())


def test_battle_records_cover_running_and_done() -> None:
    assert load("battle-record-running.json")["status"] == "running"
    assert load("battle-record-done.json")["status"] == "done"


def test_special_stat_sheets() -> None:
    toaster = StatSheet.model_validate(load("stat-sheet-toaster.json"))
    assert (toaster.category, toaster.body) == ("object", "inert")
    dragon = StatSheet.model_validate(load("stat-sheet-dragon.json"))
    assert dragon.category == "mythical" and dragon.lore is not None
    assert all(stat.method == "assumption" for stat in dragon.stats.values())


def test_extracted_values_quote_wikipedia() -> None:
    for name in ("stat-sheet.json", "stat-sheet-gray-wolf.json"):
        for stat in StatSheet.model_validate(load(name)).stats.values():
            if stat.method == "extracted":
                assert stat.source is not None
                assert stat.source.url.host == "en.wikipedia.org"
                assert stat.source.quote
