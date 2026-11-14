"""#186, DECISIONS D-51: a bare name typed all in lowercase ("moose", "shredder") is judged by its
kind item when the top pick is a person (the kind item's label must be the typed word) or a
character (an alias match is enough). Capitals keep the proper-name reading. Mock Wikidata, stand-in
lookups and a temp cache only; no network."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from app.models.matchup import FighterRequest
from app.safety.gate import model_written_names, wikidata_names
from app.safety.wikidata import (
    Candidate,
    EntityClasses,
    MockWikidataLookup,
    NameCheck,
    WikidataCache,
    WikidataUnavailable,
    bare_lowercase,
    check_names,
    kind_beats_name,
    load_class_map,
)

HUMAN, TAXON, FILM, FIREARM, CHARACTER = "Q5", "Q16521", "Q11424", "Q12796", "Q95074"


@pytest.fixture
def cache(tmp_path: Path) -> WikidataCache:
    return WikidataCache(tmp_path / "app.db")


class Matches:
    """Wikidata where every search returns these (qid, label, matched text, classes) items."""

    def __init__(self, *items: tuple[str, str, str, EntityClasses]) -> None:
        self.items = items
        self.entities = {qid: own for qid, _, _, own in items}

    async def search(self, name: str) -> list[Candidate]:
        return [Candidate(qid, label, match) for qid, label, match, _ in self.items]

    async def classes(self, qids: Sequence[str]) -> dict[str, EntityClasses]:
        return {q: self.entities.get(q, EntityClasses()) for q in qids}


class Down:
    """Wikidata that is always down: any verdict must come from the cache."""

    async def search(self, name: str) -> list[Candidate]:
        raise WikidataUnavailable("down")

    async def classes(self, qids: Sequence[str]) -> dict[str, EntityClasses]:
        raise WikidataUnavailable("down")


def test_the_class_map_version_was_bumped_for_d51() -> None:
    # D-51 and D-59 each bumped to 7 on their own branches; the merge bumped again to 8.
    assert load_class_map().version >= 8


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("moose", True),
        ("  shredder ", True),
        ("paper shredder", True),
        ("Moose", False),
        ("MOOSE", False),
        ("a moose", False),
        ("3 moose", False),
        ("the moose", False),
    ],
)
def test_bare_lowercase(name: str, expected: bool) -> None:
    assert bare_lowercase(name) is expected


@pytest.mark.parametrize(
    ("names", "reason"),
    [
        (["moose"], None),  # a person, then the animal labelled "moose": the kind wins
        (["shredder"], None),  # a character, then kinds matching only the alias "shredder"
        (["hulk"], None),  # accepted on purpose: a ship labelled "hulk"; the classifier decides
        (["napoleon"], "real_person"),  # the pastry only has "napoleon" as an alias
        (["Moose"], "real_person"),  # capitals: a proper name
        (["Shredder"], "copyrighted_character"),
        (["Hulk"], "copyrighted_character"),
        (["Napoleon"], "real_person"),
        (["moose", "Moose"], "real_person"),  # typed both ways in one request: capitals win
        (["shredder", "Shredder"], "copyrighted_character"),
        (["a moose", "moose"], None),
        (["thor"], "deity"),  # a deity is not a D-51 trigger, even with a kind item (a genus)
        (["a napoleon"], None),  # a common noun: the pastry, as before
    ],
)
async def test_the_mock_fixture_under_d51(
    cache: WikidataCache, names: list[str], reason: str | None
) -> None:
    verdict = await check_names(names, lookup=MockWikidataLookup(), cache=cache)
    assert verdict.reason == reason
    assert verdict.layer == ("wikidata" if reason else None)


@pytest.mark.parametrize(
    ("kind_label", "kind_match", "reason"),
    [
        ("doohickey", "gizmo", "real_person"),  # the kind item matched only through an alias
        ("Gizmo", "Gizmo", None),  # its label is the typed word, ignoring case
    ],
)
async def test_a_person_needs_a_kind_item_with_the_typed_label(
    cache: WikidataCache, kind_label: str, kind_match: str, reason: str | None
) -> None:
    lookup = Matches(
        ("H", "Gizmo", "Gizmo", EntityClasses((HUMAN,))),
        ("K", kind_label, kind_match, EntityClasses((TAXON,))),
    )
    assert (await check_names(["gizmo"], lookup=lookup, cache=cache)).reason == reason


async def test_a_character_yields_to_a_kind_item_matched_by_alias(cache: WikidataCache) -> None:
    lookup = Matches(
        ("C", "Gizmo", "Gizmo", EntityClasses((CHARACTER,))),
        ("K", "doohickey", "gizmo", EntityClasses((TAXON,))),
    )
    assert (await check_names(["gizmo"], lookup=lookup, cache=cache)).allowed
    assert (await check_names(["Gizmo"], lookup=lookup, cache=cache)).reason == (
        "copyrighted_character"
    )


async def test_a_blocked_kind_item_still_blocks_when_it_wins(cache: WikidataCache) -> None:
    lookup = Matches(
        ("H", "Gizmo", "Gizmo", EntityClasses((HUMAN,))),
        ("W", "gizmo", "gizmo", EntityClasses((), (FIREARM,))),
    )
    verdict = await check_names(["gizmo"], lookup=lookup, cache=cache)
    assert (verdict.reason, verdict.layer) == ("weapon", "wikidata")


async def test_a_creative_work_yields_to_a_kind_item(cache: WikidataCache) -> None:
    # Only creative works in the first results: the film is the fallback pick (no reason).
    lookup = Matches(
        ("F", "Gizmo", "Gizmo", EntityClasses((FILM,))),
        ("W", "doohickey", "gizmo", EntityClasses((), (FIREARM,))),
    )
    assert (await check_names(["gizmo"], lookup=lookup, cache=cache)).reason == "weapon"


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        (NameCheck("H", "Moose", "real_person", kind_qid="K", kind_label="Moose"), True),
        (
            NameCheck("H", "Napoleon", "real_person", kind_qid="K", kind_label="mille-feuille"),
            False,
        ),
        (
            NameCheck("C", "Shredder", "copyrighted_character", kind_qid="K", kind_label="grater"),
            True,
        ),
        (NameCheck("F", "Moose", None, kind_qid="K", kind_label="elk"), True),  # a creative work
        (NameCheck("D", "Moose", "deity", kind_qid="K", kind_label="moose"), False),
        (NameCheck("P", "Moose", "out_of_scope", kind_qid="K", kind_label="moose"), False),
        (
            NameCheck("B", "Moose", "real_person", group=True, kind_qid="K", kind_label="moose"),
            False,
        ),
        (NameCheck("H", "Moose", "real_person"), False),  # no kind item
    ],
)
def test_kind_beats_name(check: NameCheck, expected: bool) -> None:
    assert kind_beats_name("moose", check) is expected


@pytest.mark.parametrize(
    ("names", "reason"),
    [
        (["moose"], None),
        (["Moose"], "real_person"),
        (["shredder"], None),
        (["Shredder"], "copyrighted_character"),
        (["napoleon"], "real_person"),
    ],
)
async def test_a_cached_check_gives_the_same_verdict(
    cache: WikidataCache, names: list[str], reason: str | None
) -> None:
    first = await check_names(names, lookup=MockWikidataLookup(), cache=cache)
    again = await check_names(names, lookup=Down(), cache=cache)  # only the cache can answer
    assert first == again
    assert again.reason == reason
    # The other casing from the same cached row: label vs alias is decided at check time.
    flipped = [n.lower() if n[:1].isupper() else n.capitalize() for n in names]
    assert (await check_names(flipped, lookup=Down(), cache=cache)).reason == (
        await check_names(flipped, lookup=MockWikidataLookup(), cache=cache)
    ).reason


async def test_a_model_written_entity_keeps_the_proper_name_reading(cache: WikidataCache) -> None:
    # "shredder" from words the user never typed: the model chose its lowercase, so no D-51.
    fighters = [FighterRequest(raw="the turtle villain", entity="shredder")]
    assert model_written_names(fighters) == ["shredder"]
    verdict = await check_names(
        wikidata_names(fighters),
        lookup=MockWikidataLookup(),
        cache=cache,
        model_written=model_written_names(fighters),
    )
    assert verdict.reason == "copyrighted_character"
    # The same entity typed by the user is theirs: "shredder" from "shredder".
    assert model_written_names([FighterRequest(raw="shredder", entity="shredder")]) == []
