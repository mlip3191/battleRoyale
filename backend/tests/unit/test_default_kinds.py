"""#168: a bare kind ("bear") becomes its default seed fighter, by a written table, and says so."""

import re
from pathlib import Path

import pytest

from app.intake.parser import COMMON_KIND_NOTE, default_kind_notes, read_matchup
from app.intake.schema import ParsedMatchup
from app.models.matchup import FighterRequest
from app.research.seed_fighters import (
    DEFAULT_KINDS,
    default_kind,
    find_seed_fighter,
    find_seed_sheet,
    load_seed_fighters,
    picked_default,
    spoken_name,
)

RESEARCH_DOC = Path(__file__).parents[3] / "docs" / "research.md"


def request(entity: str, raw: str | None = None, variant: str | None = None) -> FighterRequest:
    return FighterRequest(entity=entity, variant=variant, raw=raw or f"a {entity}")


@pytest.mark.parametrize("name", ["bear", "Bear", "bears"])
def test_bear_becomes_the_grizzly_bear(name: str) -> None:
    fighter = find_seed_fighter(name, None, f"a {name}")
    sheet = find_seed_sheet(name, None, f"a {name}")
    assert fighter is not None and fighter.id == "grizzly-bear"
    assert sheet is not None and sheet.fighter_id == "grizzly-bear"


def test_wolves_and_other_plurals_use_the_table() -> None:
    assert default_kind("wolves") == "gray-wolf"
    assert default_kind("sharks") == "great-white-shark"
    assert default_kind("cats") == "house-cat"


def test_an_exact_name_or_a_given_kind_is_never_changed() -> None:
    assert find_seed_fighter("polar bear", None, "a polar bear") is None  # off the seed list
    assert default_kind("polar bear") is None
    assert default_kind("bear", variant="polar") is None
    assert find_seed_fighter("bear", "polar", "a polar bear") is None


def test_a_name_with_no_default_falls_back_to_normal_research() -> None:
    assert default_kind("lizard") is None
    assert find_seed_fighter("lizard", None, "a lizard") is None


def test_every_default_is_a_seed_fighter() -> None:
    seed_ids = {f.id for f in load_seed_fighters()}
    assert set(DEFAULT_KINDS.values()) <= seed_ids


def test_the_code_table_matches_the_table_in_research_md() -> None:
    text = RESEARCH_DOC.read_text(encoding="utf-8")
    section = text.split("## Default variants", 1)[1].split("\n## ", 1)[0]
    rows = dict(re.findall(r"^\| (\w+) \| `([a-z0-9-]+)` \|$", section, re.MULTILINE))
    assert rows == DEFAULT_KINDS


def test_the_note_names_the_pick() -> None:
    notes = default_kind_notes([request("bear"), request("elephant"), request("lizard")])
    assert notes == [
        "Not sure which bear, so we used the grizzly bear.",
        "Not sure which elephant, so we used the African elephant.",
    ]


def test_a_plural_note_uses_the_singular_kind() -> None:
    assert default_kind_notes([request("bears")]) == [
        "Not sure which bear, so we used the grizzly bear."
    ]


# Spelled out so a new default with a proper name ("Komodo", "Bengal") can't be lowercased
# unnoticed: update _PROPER_WORDS and this list together.
def test_every_default_reads_sensibly_in_the_note() -> None:
    picks = {f.id: spoken_name(f.display_name) for f in load_seed_fighters()}
    assert {kind: picks[slug] for kind, slug in DEFAULT_KINDS.items()} == {
        "bear": "grizzly bear",
        "shark": "great white shark",
        "wolf": "gray wolf",
        "eagle": "bald eagle",
        "cat": "house cat",
        "dog": "golden retriever",
        "elephant": "African elephant",
        "crocodile": "saltwater crocodile",
        "snake": "king cobra",
        "bee": "honey bee",
        "ant": "army ant",
        "mouse": "house mouse",
        "tank": "main battle tank",
        "truck": "pickup truck",
        "cactus": "saguaro cactus",
    }


def test_no_note_when_the_raw_text_already_names_the_kind() -> None:
    assert picked_default("wolf", None, "6 gray wolves") is None
    assert default_kind_notes([request("wolf", raw="6 gray wolves")]) == []
    assert default_kind_notes([request("grizzly bear")]) == []


def test_a_still_vague_kind_with_no_default_keeps_the_general_note() -> None:
    parsed = ParsedMatchup.model_validate(
        {
            "fighters": [
                {"entity": "lizard", "raw": "a lizard"},
                {"entity": "gray wolf", "raw": "a gray wolf"},
            ],
            "needs_clarification": {
                "question": "Which lizard?",
                "options": ["a gecko", "a monitor"],
            },
        }
    )
    result = read_matchup("lizard vs gray wolf", parsed, ask=False)
    assert result.matchup is not None and COMMON_KIND_NOTE in result.matchup.assumptions
