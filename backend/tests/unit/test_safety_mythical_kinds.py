"""#340: a generic kind of mythical creature is not a named character (D-38, D-60). Mock Wikidata
(real IDs and class chains, cut short) and a temp cache only; no network.

Live, "centaur" and "harpies" are kinds (they have a P279) whose classes reach "character"
through "mythological Greek character" -> "mythical character" (and the harpies through
"fictional creature"), so the Wikidata layer blocked them as named characters. Cerberus and
Medusa take the same path but are individuals (no P279), so they must still block. "character"
now counts only for individuals; kinds from a franchise (Pikachu) still block through
"fictional species".
"""

from collections.abc import Sequence
from pathlib import Path

import pytest

from app.safety.wikidata import (
    Candidate,
    EntityClasses,
    MockWikidataLookup,
    WikidataCache,
    check_names,
    load_class_map,
    resolve,
)

CHARACTER, FICTIONAL_SPECIES, GEOGRAPHIC_LOCATION = "Q95074", "Q21192438", "Q2221906"
CENTAUR, HARPIES, CERBERUS, MEDUSA, PIKACHU = "Q83203", "Q181360", "Q83496", "Q160730", "Q9351"


@pytest.fixture
def cache(tmp_path: Path) -> WikidataCache:
    return WikidataCache(tmp_path / "app.db")


class OnlyItem(MockWikidataLookup):
    """The mock fixture's classes, with every search returning one item as its only match."""

    def __init__(self, qid: str) -> None:
        super().__init__()
        self.qid = qid

    async def search(self, name: str) -> list[Candidate]:
        return [Candidate(self.qid, name, name)]


def test_character_counts_only_for_individuals() -> None:
    class_map = load_class_map()
    assert class_map.version == 11
    assert class_map.individuals_only == {CHARACTER, GEOGRAPHIC_LOCATION}
    assert class_map.reasons[CHARACTER] == "copyrighted_character"
    assert class_map.reasons[FICTIONAL_SPECIES] == "copyrighted_character"
    assert FICTIONAL_SPECIES not in class_map.individuals_only


@pytest.mark.parametrize(
    ("query", "qid"), [("centaur", CENTAUR), ("harpy", HARPIES), ("harpies", HARPIES)]
)
async def test_the_mock_search_picks_the_mythical_kind(query: str, qid: str) -> None:
    # The live search order: the creature is the top exact match, and a kind. resolve raises if
    # any class on the walk is missing, so None here is a real answer, not a lookup gap.
    check = await resolve(query, MockWikidataLookup(), load_class_map())
    assert (check.qid, check.reason, check.kind_qid) == (qid, None, None)
    assert load_class_map().is_kind(
        (await MockWikidataLookup().classes([qid]))[qid]
    )  # it has a P279


@pytest.mark.parametrize(
    "names",
    [
        ["a centaur", "a horse"],  # case my-05
        ["a harpy", "a goose"],  # case my-06
        ["harpies"],
        ["2 centaurs"],
        ["the centaur"],
        ["harpies", "2 centaurs"],  # case my-08
    ],
)
async def test_a_kind_of_mythical_creature_is_allowed(
    cache: WikidataCache, names: list[str]
) -> None:
    verdict = await check_names(names, lookup=MockWikidataLookup(), cache=cache)
    assert verdict.allowed, verdict


@pytest.mark.parametrize(
    ("qid", "name"),
    [
        (CERBERUS, "Cerberus"),  # an individual (no P279): the same path to "character"
        (MEDUSA, "Medusa"),
        (MEDUSA, "a Medusa"),
    ],
)
async def test_named_mythological_individuals_still_block(
    cache: WikidataCache, qid: str, name: str
) -> None:
    verdict = await check_names([name], lookup=OnlyItem(qid), cache=cache)
    assert (verdict.reason, verdict.layer) == ("copyrighted_character", "wikidata")


async def test_a_franchise_kind_still_blocks_through_fictional_species(
    cache: WikidataCache,
) -> None:
    # Live Pikachu has a P279 (so it is a kind) and reaches "character" one level up; with
    # "character" for individuals only, "fictional species" (two levels up) still blocks it.
    check = await resolve("pikachu", OnlyItem(PIKACHU), load_class_map())
    assert (check.qid, check.reason) == (PIKACHU, "copyrighted_character")
    for name in ("Pikachu", "a pikachu"):
        verdict = await check_names([name], lookup=OnlyItem(PIKACHU), cache=cache)
        assert verdict.reason == "copyrighted_character", name


@pytest.mark.parametrize("name", ["Mickey Mouse", "Lightning McQueen", "Wolverine"])
async def test_named_fictional_characters_still_block(cache: WikidataCache, name: str) -> None:
    verdict = await check_names([name], lookup=MockWikidataLookup(), cache=cache)
    assert (verdict.reason, verdict.layer) == ("copyrighted_character", "wikidata")


@pytest.mark.parametrize(
    ("own", "reason"),
    [
        # An individual reaching "character": blocked (Cerberus, Medusa).
        (EntityClasses(("MYTH",)), "copyrighted_character"),
        # A kind reaching "character": allowed (centaur, harpies).
        (EntityClasses((), ("MYTH",)), None),
        # A kind reaching "fictional species": blocked (Pikachu, Dalek).
        (EntityClasses((), ("SPECIES",)), "copyrighted_character"),
    ],
)
async def test_character_and_fictional_species_rules(
    own: EntityClasses, reason: str | None
) -> None:
    parents = {
        "MYTH": EntityClasses((), (CHARACTER,)),
        "SPECIES": EntityClasses((), (FICTIONAL_SPECIES,)),
    }

    class Ranked:
        async def search(self, name: str) -> list[Candidate]:
            return [Candidate("P", name, name)]

        async def classes(self, qids: Sequence[str]) -> dict[str, EntityClasses]:
            return {q: {"P": own, **parents}.get(q, EntityClasses()) for q in qids}

    assert (await resolve("gizmo", Ranked(), load_class_map())).reason == reason
