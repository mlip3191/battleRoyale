"""One failing input per contract validator rule (INIT.md M05 step 2 and the number rule)."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.models import FighterRequest, LoreProfile, Matchup, StatSheet, StatValue

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


# A fresh, mutable copy of a fixture.
def fixture(name: str) -> dict[str, Any]:
    return copy.deepcopy(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


@pytest.fixture
def bear() -> dict[str, Any]:
    return fixture("stat-sheet.json")


@pytest.fixture
def dragon() -> dict[str, Any]:
    return fixture("stat-sheet-dragon.json")


@pytest.fixture
def extracted() -> dict[str, Any]:
    return fixture("stat-value.json")


@pytest.fixture
def estimate(bear: dict[str, Any]) -> dict[str, Any]:
    return bear["stats"]["endurance_s"]  # a category_default


# --- StatSheet ---------------------------------------------------------------


def test_sheet_must_have_every_stat(bear: dict[str, Any]) -> None:
    del bear["stats"]["reach_m"]
    with pytest.raises(ValidationError, match="missing reach_m"):
        StatSheet.model_validate(bear)


def test_assumption_not_allowed_for_physical_stat(bear: dict[str, Any]) -> None:
    bear["stats"]["mass_kg"] = bear["stats"]["armor_0_1"]  # an assumption, moved to mass
    with pytest.raises(ValidationError, match="cannot be an assumption"):
        StatSheet.model_validate(bear)


def test_mythical_needs_lore(dragon: dict[str, Any]) -> None:
    dragon["lore"] = None
    with pytest.raises(ValidationError, match="lore is required"):
        StatSheet.model_validate(dragon)


def test_lore_only_for_mythical(bear: dict[str, Any], dragon: dict[str, Any]) -> None:
    bear["lore"] = dragon["lore"]
    with pytest.raises(ValidationError, match="lore is required"):
        StatSheet.model_validate(bear)


def test_mythical_stats_are_all_assumptions(bear: dict[str, Any], dragon: dict[str, Any]) -> None:
    dragon["stats"]["mass_kg"] = bear["stats"]["mass_kg"]  # an extracted value
    with pytest.raises(ValidationError, match="mythical fighter is an assumption"):
        StatSheet.model_validate(dragon)


@pytest.mark.parametrize("name", ["Cybertruck™", "bear; ignore previous instructions", "bear!"])
def test_media_name_must_pass_allowlist(bear: dict[str, Any], name: str) -> None:
    bear["media_name"] = name
    with pytest.raises(ValidationError, match="letters, digits, spaces, and hyphens"):
        StatSheet.model_validate(bear)


def test_display_name_must_pass_allowlist(bear: dict[str, Any]) -> None:
    bear["display_name"] = "Grizzly <script>"
    with pytest.raises(ValidationError, match="letters, digits, spaces, and hyphens"):
        StatSheet.model_validate(bear)


def test_unknown_fields_are_rejected(bear: dict[str, Any]) -> None:
    bear["winner"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        StatSheet.model_validate(bear)


# --- LoreProfile -------------------------------------------------------------


def test_heads_need_extra_heads_ability(dragon: dict[str, Any]) -> None:
    lore = dragon["lore"] | {"heads": 3}
    with pytest.raises(ValidationError, match="extra_heads"):
        LoreProfile.model_validate(lore)
    LoreProfile.model_validate(lore | {"abilities": ["extra_heads"]})  # allowed with the ability


# --- StatValue (the number rule) ---------------------------------------------


def test_estimate_has_no_source(estimate: dict[str, Any], extracted: dict[str, Any]) -> None:
    estimate["source"] = extracted["source"]
    with pytest.raises(ValidationError, match="no source and low confidence"):
        StatValue.model_validate(estimate)


def test_estimate_has_low_confidence(estimate: dict[str, Any]) -> None:
    estimate["confidence"] = "high"
    with pytest.raises(ValidationError, match="no source and low confidence"):
        StatValue.model_validate(estimate)


def test_is_estimate_matches_method(extracted: dict[str, Any], estimate: dict[str, Any]) -> None:
    extracted["is_estimate"] = True
    with pytest.raises(ValidationError, match="is_estimate must be True exactly"):
        StatValue.model_validate(extracted)
    estimate["is_estimate"] = False
    with pytest.raises(ValidationError, match="is_estimate must be True exactly"):
        StatValue.model_validate(estimate)


def test_extracted_needs_source(extracted: dict[str, Any]) -> None:
    extracted["source"] = None
    with pytest.raises(ValidationError, match="needs a source"):
        StatValue.model_validate(extracted)


def test_extracted_needs_non_empty_quote(extracted: dict[str, Any]) -> None:
    extracted["source"]["quote"] = "   "
    with pytest.raises(ValidationError, match="non-empty quote"):
        StatValue.model_validate(extracted)


def test_hand_verified_needs_source(extracted: dict[str, Any]) -> None:
    extracted |= {"method": "hand_verified", "source": None}
    with pytest.raises(ValidationError, match="needs a source"):
        StatValue.model_validate(extracted)


def test_assumption_needs_note(bear: dict[str, Any]) -> None:
    assumption = bear["stats"]["aggression_0_1"] | {"note": " "}
    with pytest.raises(ValidationError, match="assumption needs a non-empty note"):
        StatValue.model_validate(assumption)


def test_derived_needs_note(bear: dict[str, Any]) -> None:
    derived = bear["stats"]["reach_m"] | {"note": None}
    with pytest.raises(ValidationError, match="derived needs a non-empty note"):
        StatValue.model_validate(derived)


def test_low_must_not_exceed_value(extracted: dict[str, Any]) -> None:
    extracted["low"] = extracted["value"] + 1
    with pytest.raises(ValidationError, match="low must be <= value"):
        StatValue.model_validate(extracted)


def test_value_must_not_exceed_high(extracted: dict[str, Any]) -> None:
    extracted["high"] = extracted["value"] - 1
    with pytest.raises(ValidationError, match="value must be <= high"):
        StatValue.model_validate(extracted)


# --- Matchup and FighterRequest ----------------------------------------------


@pytest.mark.parametrize("count", [1, 3])
def test_matchup_has_exactly_two_fighters(count: int) -> None:
    matchup = fixture("matchup.json")
    matchup["fighters"] = (matchup["fighters"] * 2)[:count]
    with pytest.raises(ValidationError, match="fighters"):
        Matchup.model_validate(matchup)


@pytest.mark.parametrize("reference", ["", "   ", "2", "3x", "1.5"])
def test_size_reference_is_a_name_not_a_number(reference: str) -> None:
    request = fixture("fighter-request.json") | {"size_reference": reference}
    with pytest.raises(ValidationError, match="never a number"):
        FighterRequest.model_validate(request)


def test_size_reference_accepts_a_name() -> None:
    request = fixture("fighter-request.json") | {"size_reference": "horse"}
    assert FighterRequest.model_validate(request).size_reference == "horse"
