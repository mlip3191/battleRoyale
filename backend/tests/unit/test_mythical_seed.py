"""data/seed/mythical.yaml: the 12 mythical creature types G09 builds sheets from (#39)."""

import re
from pathlib import Path

import yaml

from app.config import REPO_ROOT
from app.models.stats import Ability, LoreProfile
from app.research.seed_fighters import load_seed_fighters

MYTHICAL_PATH = REPO_ROOT / "data" / "seed" / "mythical.yaml"
ID_PATTERN = re.compile(r"^[a-z]+(-[a-z]+)*$")
DISPLAY_PATTERN = re.compile(r"^[A-Za-z0-9 -]+$")


# Read the creature list.
def load_creatures(path: Path = MYTHICAL_PATH) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["creatures"]


# Seed fighters' display names in lowercase, so "saltwater crocodile" matches "Saltwater crocodile".
def seed_names() -> set[str]:
    return {fighter.display_name.lower() for fighter in load_seed_fighters()}


def test_there_are_exactly_twelve_creatures_with_unique_ids() -> None:
    ids = [creature["id"] for creature in load_creatures()]
    assert len(ids) == 12
    assert len(set(ids)) == 12


def test_ids_and_names_are_plain_slugs_and_words() -> None:
    for creature in load_creatures():
        assert ID_PATTERN.match(creature["id"]), creature["id"]
        assert DISPLAY_PATTERN.match(creature["display_name"]), creature["display_name"]
        assert DISPLAY_PATTERN.match(creature["media_name"]), creature["media_name"]


def test_every_lore_block_validates() -> None:
    for creature in load_creatures():
        LoreProfile.model_validate(creature["lore"])


def test_analogs_are_seed_fighters() -> None:
    names = seed_names()
    for creature in load_creatures():
        lore = LoreProfile.model_validate(creature["lore"])
        assert lore.body_analog.lower() in names, (creature["id"], lore.body_analog)
        if lore.size_analog is not None:
            assert lore.size_analog.lower() in names, (creature["id"], lore.size_analog)


def test_every_quote_comes_from_a_pinned_wikipedia_revision() -> None:
    for creature in load_creatures():
        source = LoreProfile.model_validate(creature["lore"]).source
        assert str(source.url).startswith("https://en.wikipedia.org/w/index.php?title=")
        assert "&oldid=" in str(source.url), creature["id"]
        assert source.quote.strip(), creature["id"]
        assert source.license == "CC BY-SA 4.0"


def test_the_dragon_matches_the_showcase_plan() -> None:
    dragon = next(c for c in load_creatures() if c["id"] == "dragon")
    lore = LoreProfile.model_validate(dragon["lore"])
    assert lore.body_analog == "saltwater crocodile"
    assert lore.size_analog == "African elephant"
    assert set(lore.abilities) == {Ability.FLIGHT, Ability.BREATH_WEAPON}
