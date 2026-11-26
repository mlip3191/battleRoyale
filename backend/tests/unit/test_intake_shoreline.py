"""#619: a water animal against a land animal with no place typed meets on the shoreline.

ARCHITECTURE section 14 ("Habitat mismatch") promises the shoreline and a note. The intake used to
leave such a matchup in the arena with nothing noted, so the land animal won with the shark
stranded. Code decides this from the seed list's habitats; no model is involved.
"""

from app.intake.parser import SHORELINE_NOTE, read_matchup
from app.intake.schema import ParsedFighter, ParsedMatchup
from app.models.terrain import Terrain


def _read(text: str, a: str, b: str, terrain: str | None = None):
    parsed = ParsedMatchup(
        fighters=[
            ParsedFighter(entity=a, raw=f"a {a}"),
            ParsedFighter(entity=b, raw=f"a {b}"),
        ],
        terrain=terrain,
    )
    return read_matchup(text, parsed)


def test_a_shark_against_a_lion_with_no_place_meets_on_the_shoreline() -> None:
    result = _read("a great white shark vs a lion", "great white shark", "lion")
    assert result.status == "ok" and result.matchup is not None
    assert result.matchup.terrain == Terrain.SHORELINE
    assert SHORELINE_NOTE in result.matchup.assumptions
    assert "on the shoreline" in (result.message or "")  # the card line says where


def test_the_order_of_the_sides_does_not_matter() -> None:
    result = _read("a lion vs a great white shark", "lion", "great white shark")
    assert result.matchup is not None and result.matchup.terrain == Terrain.SHORELINE


def test_a_typed_place_always_wins() -> None:
    for text, terrain, expected in [
        ("a great white shark vs a lion in the water", "in the water", Terrain.WATER),
        ("a great white shark vs a lion in a forest", "a forest", Terrain.FOREST),
        ("a great white shark vs a lion in the arena", "the arena", Terrain.ARENA),
    ]:
        result = _read(text, "great white shark", "lion", terrain)
        assert result.matchup is not None
        assert result.matchup.terrain == expected, text
        assert SHORELINE_NOTE not in result.matchup.assumptions


def test_two_land_animals_or_two_water_animals_keep_the_default() -> None:
    land = _read("a lion vs a gray wolf", "lion", "gray wolf")
    assert land.matchup is not None and land.matchup.terrain == Terrain.ARENA
    assert SHORELINE_NOTE not in land.matchup.assumptions
    water = _read(
        "a great white shark vs a saltwater crocodile", "great white shark", "saltwater crocodile"
    )
    assert water.matchup is not None
    assert water.matchup.terrain == Terrain.ARENA  # a crocodile is amphibious, not land-only


def test_a_fighter_with_no_seed_habitat_keeps_the_default() -> None:
    result = _read("a great white shark vs a moose", "great white shark", "moose")
    assert result.matchup is not None and result.matchup.terrain == Terrain.ARENA
