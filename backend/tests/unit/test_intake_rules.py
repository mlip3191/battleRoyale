"""Intake code rules: counts, names, size references, and terrain (A02, part 1)."""

import pytest
from pydantic import ValidationError

from app.config import get_settings
from app.intake.rules import (
    CountReading,
    clamp_count,
    find_size_reference,
    map_terrain,
    normalize_entity,
    read_count,
    singular_word,
    strip_size_phrase,
)
from app.intake.schema import ParsedMatchup
from app.models.terrain import Terrain

# --- Counts -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "count"),
    [
        ("a dozen house cats", 12),
        ("a pair of goats", 2),
        ("a couple of geese", 2),
        ("two dozen eggs", 24),
        ("100 duck-sized horses", 100),
        ("1 horse-sized duck", 1),
        ("3 wolves", 3),
        ("500 army ants", 500),
        ("a million ants", 1_000_000),
        ("1,000,000 ants", 1_000_000),
        ("3 million ants", 3_000_000),
        ("one hundred and twenty wolves", 120),
        ("twenty-five bees", 25),
        ("a hundred thousand ants", 100_000),
        ("2.0 bears", 2),
        ("a toaster", 1),
        ("an ant", 1),
        ("the goose", 1),
        ("one moose", 1),
        ("A Dozen House Cats", 12),
    ],
)
def test_counts_come_from_digits_and_number_words(raw: str, count: int) -> None:
    assert read_count(raw) == CountReading(count)


@pytest.mark.parametrize("raw", ["ant", "whale", "bear", "wolves", "dragon"])
def test_no_quantity_words_means_no_count(raw: str) -> None:
    assert read_count(raw) == CountReading(None)


@pytest.mark.parametrize(
    "raw", ["half a horse", "a quarter of a bear", "one third of a moose", "1/2 horse", "1.5 bears"]
)
def test_fractions_are_flagged_not_counted(raw: str) -> None:
    assert read_count(raw) == CountReading(None, "fraction")


@pytest.mark.parametrize("raw", ["0 wolves", "zero wolves", "no wolves", "none"])
def test_zero_is_flagged(raw: str) -> None:
    assert read_count(raw).problem == "zero"


def test_a_quarter_horse_is_a_breed_not_a_fraction() -> None:
    assert read_count("a quarter horse") == CountReading(1)


def test_number_words_after_the_name_are_ignored() -> None:
    assert read_count("a horse with three legs") == CountReading(1)


def test_counts_above_the_limit_are_clamped_with_an_assumption() -> None:
    limit = get_settings().sim_max_count
    count, note = clamp_count(1_000_000, "ant", limit)
    assert count == limit == 10_000
    assert note is not None and "10,000" in note and "1,000,000" in note and "ant" in note


def test_counts_within_the_limit_are_unchanged() -> None:
    assert clamp_count(10_000, "ant", 10_000) == (10_000, None)
    assert clamp_count(3, "wolf", 10_000) == (3, None)


# --- Names --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("word", "singular"),
    [
        ("wolves", "wolf"),
        ("geese", "goose"),
        ("mice", "mouse"),
        ("horses", "horse"),
        ("ants", "ant"),
        ("foxes", "fox"),
        ("finches", "finch"),
        ("flies", "fly"),
        ("bees", "bee"),
        ("rhinos", "rhino"),
        ("kiwis", "kiwi"),
        ("emus", "emu"),
        ("doves", "dove"),
        ("albatrosses", "albatross"),
        ("octopuses", "octopus"),
        ("bulldozers", "bulldozer"),
    ],
)
def test_plurals_become_singular(word: str, singular: str) -> None:
    assert singular_word(word) == singular


@pytest.mark.parametrize(
    "word",
    [
        "moose",
        "deer",
        "fish",
        "bison",
        "walrus",
        "octopus",
        "cactus",
        "stegosaurus",
        "albatross",
        "rhinoceros",
        "mantis",
        "ibis",
        "wolf",
        "goose",
        "toaster",
        "ox",
    ],
)
def test_singular_words_are_left_alone(word: str) -> None:
    assert singular_word(word) == word


@pytest.mark.parametrize(
    ("name", "entity"),
    [
        ("Wolves", "wolf"),
        ("Army Ants", "army ant"),
        ("house cats", "house cat"),
        ("  Golden   Retriever ", "golden retriever"),
        ("the Grizzly Bear", "grizzly bear"),
        ("main battle tank", "main battle tank"),
        ("Cybertruck", "cybertruck"),
        ("3 wolves", "wolf"),
        ("a dozen house cats", "house cat"),
        ("duck-sized horses", "horse"),
        ("Horse-Sized Duck", "duck"),
        ("medium-sized dog", "dog"),
        ("saguaro cactus", "saguaro cactus"),
        ("praying mantises", "praying mantis"),
    ],
)
def test_names_are_lowercase_singular_without_quantity_or_size(name: str, entity: str) -> None:
    assert normalize_entity(name) == entity


def test_a_name_made_only_of_quantity_words_normalizes_to_empty() -> None:
    assert normalize_entity("a dozen") == ""


# --- Size references ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "reference"),
    [
        ("100 duck-sized horses", "duck"),
        ("1 horse-sized duck", "horse"),
        ("a horse sized duck", "horse"),
        ("an elephant-sized ant", "elephant"),
        ("a school-bus-sized spider", "school bus"),
        ("a duck the size of a horse", "horse"),
        ("ants-sized whale", "ant"),
    ],
)
def test_size_phrases_name_the_reference_entity(raw: str, reference: str) -> None:
    assert find_size_reference(raw) == reference


@pytest.mark.parametrize(
    "raw", ["a goat", "medium-sized dog", "a king-sized bed", "a large horse", "3 wolves"]
)
def test_no_size_reference_without_an_entity_size_phrase(raw: str) -> None:
    assert find_size_reference(raw) is None


def test_duck_and_horse_swap_roles_on_each_side() -> None:
    left, right = "100 duck-sized horses", "1 horse-sized duck"
    assert (normalize_entity(left), find_size_reference(left)) == ("horse", "duck")
    assert (normalize_entity(right), find_size_reference(right)) == ("duck", "horse")


def test_size_phrase_is_removed_from_a_name() -> None:
    assert strip_size_phrase("Duck-Sized Horse") == "horse"
    assert strip_size_phrase("duck the size of a horse") == "duck"


# --- Terrain ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("phrase", "terrain"),
    [
        ("in the forest", Terrain.FOREST),
        ("the woods", Terrain.FOREST),
        ("jungle", Terrain.FOREST),
        ("on the beach", Terrain.SHORELINE),
        ("in the ocean", Terrain.WATER),
        ("city streets", Terrain.URBAN),
        ("the mountains", Terrain.MOUNTAIN),
        ("open_field", Terrain.OPEN_FIELD),
        ("an open field", Terrain.OPEN_FIELD),
        ("the savanna", Terrain.OPEN_FIELD),
        ("in a snowy forest", Terrain.FOREST),
        ("Arena", Terrain.ARENA),
    ],
)
def test_terrain_words_map_to_the_enum(phrase: str, terrain: Terrain) -> None:
    assert map_terrain(phrase) == (terrain, None)


@pytest.mark.parametrize("phrase", [None, "", "  ", "in the"])
def test_no_terrain_means_arena_without_an_assumption(phrase: str | None) -> None:
    assert map_terrain(phrase) == (Terrain.ARENA, None)


def test_approximate_terrain_is_mapped_with_an_assumption() -> None:
    terrain, note = map_terrain("in the snow")
    assert terrain == Terrain.OPEN_FIELD
    assert note is not None and "snow" in note


def test_unknown_terrain_falls_back_to_arena_with_an_assumption() -> None:
    terrain, note = map_terrain("inside a volcano")
    assert terrain == Terrain.ARENA
    assert note is not None and "volcano" in note and "arena" in note


# --- Model reply schema -------------------------------------------------------------------


def test_model_reply_with_wrong_types_still_validates_so_code_can_override_it() -> None:
    reply = ParsedMatchup.model_validate(
        {
            "fighters": [
                {"entity": "Wolves", "count": "lots", "raw": "3 wolves", "size_reference": 2.5},
                {"entity": "moose", "count": 7, "raw": "a moose"},
            ],
            "terrain": "volcano",
            "extra_field": "ignored",
        }
    )
    wolf = reply.fighters[0]
    assert wolf.size_reference == 2.5 and wolf.count == "lots"
    assert normalize_entity(wolf.entity) == "wolf"
    assert read_count(wolf.raw).count == 3
    assert find_size_reference(wolf.raw) is None
    assert read_count(reply.fighters[1].raw).count == 1
    assert map_terrain(reply.terrain)[0] == Terrain.ARENA


def test_model_reply_without_a_raw_phrase_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ParsedMatchup.model_validate({"fighters": [{"entity": "wolf"}]})
