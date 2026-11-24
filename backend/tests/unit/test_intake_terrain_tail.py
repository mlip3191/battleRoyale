"""#456: a trailing "in a forest" is read from the typed text when the model drops the place.

The model sometimes returns terrain null for "a grizzly bear vs 6 gray wolves in a forest", so the
battle was fought in the arena. Code now reads a trailing place phrase itself; when the model does
give a place, the model's wins.
"""

import pytest

from app.intake.parser import read_matchup
from app.intake.rules import terrain_in_text
from app.intake.schema import ParsedMatchup
from app.models.terrain import Terrain


def parsed(text: str, terrain: str | None) -> ParsedMatchup:
    left, right = (part.strip() for part in text.split(" vs "))
    sides = [{"entity": "bear", "raw": left}, {"entity": "wolf", "raw": right}]
    return ParsedMatchup.model_validate({"fighters": sides, "terrain": terrain})


def terrain_of(text: str, terrain: str | None) -> Terrain:
    result = read_matchup(text, parsed(text, terrain))
    assert result.status == "ok" and result.matchup is not None
    return result.matchup.terrain


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a grizzly bear vs 6 gray wolves in a forest", Terrain.FOREST),
        ("a shark vs a crocodile in the water", Terrain.WATER),
        ("a lion vs a gorilla on the beach", Terrain.SHORELINE),
        ("a bear vs a wolf at the mountain", Terrain.MOUNTAIN),
        ("a bear vs a wolf in the open field", Terrain.OPEN_FIELD),
        ("a bear vs a wolf in a city", Terrain.URBAN),
        ("a bald eagle vs a dragon in the sky", Terrain.SKY),  # D-70
    ],
)
def test_a_trailing_place_is_read_when_the_model_drops_it(text, expected) -> None:
    assert terrain_of(text, None) == expected
    assert terrain_of(text, "") == expected  # an empty answer counts as dropped too


# An audit found these missed: longer phrases, more than one trailing mark, a hyphenated place.
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a bear vs a wolf in the middle of the forest", Terrain.FOREST),
        ("a bear vs a wolf in the middle of a forest", Terrain.FOREST),
        ("a bear vs a wolf on top of a mountain", Terrain.MOUNTAIN),
        ("a bear vs a wolf on the side of a hill", Terrain.MOUNTAIN),
        ("a bear vs a wolf in a dark spooky forest", Terrain.FOREST),
        ("a bear vs a wolf in a forest!!", Terrain.FOREST),
        ("a bear vs a wolf in a forest...", Terrain.FOREST),
        ("a bear vs a wolf in a forest :)", Terrain.FOREST),
        ("a bear vs a wolf (in a forest)", Terrain.FOREST),
        ("a bear vs a wolf in a rain-forest", Terrain.FOREST),
    ],
)
def test_longer_and_punctuated_places_are_read(text, expected) -> None:
    assert terrain_of(text, None) == expected


def test_a_model_answer_of_arena_does_not_hide_a_typed_battlefield() -> None:
    # The model said "arena" but the user typed a forest: as in #416's answer step, the typed place
    # wins.
    assert terrain_of("a bear vs a wolf in a forest", "arena") == Terrain.FOREST
    # An explicit arena in the text stays an arena, and a real model answer is never overridden.
    assert terrain_of("a bear vs a wolf in the arena", "arena") == Terrain.ARENA
    assert terrain_of("a bear vs a wolf in the arena", None) == Terrain.ARENA
    assert terrain_of("a bear vs a wolf in a forest", "the snow") == Terrain.OPEN_FIELD


def test_the_models_own_terrain_wins_when_it_gives_one() -> None:
    assert terrain_of("a bear vs a wolf in a forest", "the snow") == Terrain.OPEN_FIELD


@pytest.mark.parametrize(
    "text",
    [
        "a grizzly bear vs 6 gray wolves",
        "a sea turtle vs a wolf",  # a place word inside a name is not the battlefield
        "a bear vs a wolf in a minute",
        "a bear vs a wolf in a fight to the death",
        "a bear vs a wolf on a whim",
    ],
)
def test_no_place_means_the_arena(text) -> None:
    assert terrain_in_text(text) is None
    assert terrain_of(text, None) == Terrain.ARENA


def test_an_approximate_place_still_adds_its_assumption() -> None:
    result = read_matchup("a bear vs a wolf on ice", parsed("a bear vs a wolf on ice", None))
    assert result.matchup is not None and result.matchup.terrain == Terrain.OPEN_FIELD
    assert any("ice" in note for note in result.matchup.assumptions)
