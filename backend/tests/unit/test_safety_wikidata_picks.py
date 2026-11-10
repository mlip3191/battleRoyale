"""A04 part 3a (#27): which exact Wikidata match is picked (creative works and bands demoted),
bands blocked as real people for proper names only, the weapons-of-mass-destruction class, and
the classes_version bump. Mock Wikidata and a temp cache only; no network."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from app.safety.wikidata import (
    Candidate,
    EntityClasses,
    MockWikidataLookup,
    NameCheck,
    WikidataCache,
    WikidataUnavailable,
    check_names,
    load_class_map,
    names_band,
    resolve,
)

MAGAZINE, FILM, ALBUM = "Q41298", "Q11424", "Q482994"
MUSICAL_GROUP, ROCK_BAND = "Q215380", "Q5741069"
GIRL_GROUP, BOY_BAND, METAL_BAND, DUO = "Q641066", "Q216337", "Q56816954", "Q9212979"
TAXON, FAMILY_NAME = "Q16521", "Q101352"
MALE_NAME, FEMALE_NAME, UNISEX_NAME = "Q12308941", "Q11879590", "Q3409032"
ASTEROID = "Q3863"
WMD, NUCLEAR_WEAPON = "Q49394", "Q12802"


@pytest.fixture
def cache(tmp_path: Path) -> WikidataCache:
    return WikidataCache(tmp_path / "app.db")


class ExactMatches:
    """Wikidata where every search returns these items, in order, each matching the query.

    label is every item's label (default: the query as searched); classes adds class data for
    items the search does not return (parent classes).
    """

    def __init__(
        self,
        *items: tuple[str, EntityClasses],
        label: str | None = None,
        classes: dict[str, EntityClasses] | None = None,
    ) -> None:
        self.items = list(items)
        self.label = label
        self.entities = {**dict(items), **(classes or {})}

    async def search(self, name: str) -> list[Candidate]:
        return [Candidate(qid, self.label or name, name) for qid, _ in self.items]

    async def classes(self, qids: Sequence[str]) -> dict[str, EntityClasses]:
        return {q: self.entities.get(q, EntityClasses()) for q in qids}


def test_the_class_map_demotes_creative_works_and_bands_and_lists_wmd() -> None:
    class_map = load_class_map()
    assert class_map.version >= 5
    bands = {MUSICAL_GROUP, ROCK_BAND, GIRL_GROUP, BOY_BAND, METAL_BAND, DUO}
    assert bands <= class_map.bands
    assert {MAGAZINE, FILM, ALBUM} | bands <= class_map.demoted
    assert {class_map.reasons[band] for band in bands} == {"real_person"}
    assert {MALE_NAME, FEMALE_NAME, UNISEX_NAME} <= class_map.name_items
    assert TAXON in class_map.kinds
    assert class_map.reasons[WMD] == class_map.reasons[NUCLEAR_WEAPON] == "weapon"


# --- Option A: demotion ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "picked"),
    [
        ("dragon", "Q900060"),  # the magazine "Dragon" ranks first; the creature is picked
        ("grizzly bear", "Q900121"),  # the band "Grizzly Bear" ranks first; the animal is picked
        ("beatles", "Q900130"),  # band, song, asteroid: no kind item, so the band keeps rank 1
        ("bulldozer", "Q900071"),  # a band ranks first; the machine (a kind item) is picked
        ("thor", "Q900151"),  # the male given name is skipped; the god is picked
        ("eagles", "Q900160"),  # the band, labelled exactly "Eagles", before a football team
        ("rolling stones", "Q900190"),  # the band before an asteroid
        ("wolves", "Q900171"),  # a band matching only through an alias is passed over
        ("sharks", None),  # ... even when it is the only exact match
    ],
)
async def test_the_mock_fixture_picks(query: str, picked: str | None) -> None:
    check = await resolve(query, MockWikidataLookup(), load_class_map())
    assert check.qid == picked


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        # A film, then a human: the human is picked.
        ([("F", EntityClasses((FILM,))), ("H", EntityClasses(("Q5",)))], ("H", "real_person")),
        # An item that is a film and something else is not demoted.
        ([("F", EntityClasses((FILM, TAXON))), ("H", EntityClasses(("Q5",)))], ("F", None)),
        # Only creative works: the first one is used (nothing blocked).
        ([("F", EntityClasses((FILM,))), ("A", EntityClasses((ALBUM,)))], ("F", None)),
        # A name item is skipped, a demoted one is the fallback.
        ([("N", EntityClasses((FAMILY_NAME,))), ("M", EntityClasses((MAGAZINE,)))], ("M", None)),
        # Live "the Beatles": band, then an asteroid (an individual, not a kind): band kept.
        (
            [("B", EntityClasses((MUSICAL_GROUP,))), ("A", EntityClasses((ASTEROID,)))],
            ("B", "real_person"),
        ),
        # A band yields to a kind item: a taxon, or anything with a P279.
        ([("B", EntityClasses((MUSICAL_GROUP,))), ("T", EntityClasses((TAXON,)))], ("T", None)),
        ([("B", EntityClasses((GIRL_GROUP,))), ("K", EntityClasses((), ("Q1",)))], ("K", None)),
        # With a kind item somewhere, a band yields even to an individual ranked after it.
        (
            [
                ("B", EntityClasses((ROCK_BAND,))),
                ("A", EntityClasses((ASTEROID,))),
                ("T", EntityClasses((TAXON,))),
            ],
            ("A", None),
        ),
        # A band beats a creative work ranked after it.
        ([("B", EntityClasses((DUO,))), ("F", EntityClasses((FILM,)))], ("B", "real_person")),
        # Live "Thor": a given name of any kind is skipped.
        ([("N", EntityClasses((MALE_NAME,))), ("H", EntityClasses(("Q5",)))], ("H", "real_person")),
        (
            [("N", EntityClasses((FEMALE_NAME,))), ("H", EntityClasses(("Q5",)))],
            ("H", "real_person"),
        ),
        (
            [("N", EntityClasses((UNISEX_NAME,))), ("H", EntityClasses(("Q5",)))],
            ("H", "real_person"),
        ),
    ],
)
async def test_demotion_rules(
    items: list[tuple[str, EntityClasses]], expected: tuple[str, str | None]
) -> None:
    check = await resolve("gizmo", ExactMatches(*items), load_class_map())
    assert (check.qid, check.reason) == expected


# --- Option B: bands are real people, for proper names only -----------------------------------


@pytest.mark.parametrize(
    ("names", "reason"),
    [
        (["the Beatles"], "real_person"),
        (["Beatles"], "real_person"),
        (["The Beatles"], "real_person"),
        (["a grizzly bear"], None),  # the band is demoted; the animal is picked
        (["Grizzly Bear"], None),  # capitalized, but the animal still beats the band
        (["a Dragon"], None),  # the magazine is passed over
        (["a nuclear bomb"], "weapon"),
        (["a bulldozer"], None),  # the band "Bulldozer" yields to the machine
        # A band blocks when typed as "the" + its label, or as its bare label only when that is
        # not a common word. "eagle" is a kind item, so bare "Eagles" is the birds.
        (["Eagles"], None),
        (["the Eagles"], "real_person"),
        (["The Eagles"], "real_person"),
        (["eagles"], None),
        (["the eagles"], None),
        (["EAGLES"], None),
        (["Wolves"], None),  # the band only matched an alias; a sports team is picked
        (["Sharks"], None),  # the only exact match is a band matching through an alias
        (["eagles", "the Eagles"], "real_person"),  # one typed name names the band: blocked
        (["Eagles", "the Eagles"], "real_person"),
        # "rolling stone" only matches a magazine (not a kind item): bare "Rolling Stones" blocks.
        (["Rolling Stones"], "real_person"),
        (["the Rolling Stones"], "real_person"),
        (["rolling stones"], None),
    ],
)
async def test_mock_fixture_band_and_wmd_examples(
    cache: WikidataCache, names: list[str], reason: str | None
) -> None:
    verdict = await check_names(names, lookup=MockWikidataLookup(), cache=cache)
    assert verdict.reason == reason
    assert verdict.layer == ("wikidata" if reason else None)


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("a grizzly bear", None),  # lowercase after an article: a common noun, never a band
        ("3 grizzly bears", None),
        ("Grizzly Bear", "real_person"),
        ("the Grizzly Bear", "real_person"),
        ("The Grizzly Bear", "real_person"),
        ("grizzly bear", None),  # bare but lowercase: not the band's label as typed
        ("Grizzly bear", None),
        ("a Grizzly Bear", None),  # only a leading "the" may be added to the label
    ],
)
@pytest.mark.parametrize("band", [MUSICAL_GROUP, ROCK_BAND, GIRL_GROUP, BOY_BAND, METAL_BAND, DUO])
async def test_a_band_blocks_only_names_typed_as_its_label(
    cache: WikidataCache, name: str, reason: str | None, band: str
) -> None:
    # Here the band is the only exact match, so demotion cannot save the common noun.
    lookup = ExactMatches(("B", EntityClasses((band,))), label="Grizzly Bear")
    verdict = await check_names([name], lookup=lookup, cache=cache)
    assert verdict.reason == reason


async def test_the_band_label_check_also_applies_to_cached_picks(cache: WikidataCache) -> None:
    lookup = ExactMatches(("B", EntityClasses((MUSICAL_GROUP,))), label="Eagles")
    assert (await check_names(["Eagles"], lookup=lookup, cache=cache)).reason == "real_person"
    cached = await cache.get("eagles", load_class_map().version)
    assert cached == NameCheck("B", "Eagles", "real_person", band=True)
    assert (await check_names(["eagles"], lookup=lookup, cache=cache)).allowed  # a cache hit


@pytest.mark.parametrize(
    ("typed", "label", "common", "expected"),
    [
        ("the Beatles", "The Beatles", False, True),
        ("The Beatles", "The Beatles", True, True),  # a leading "the" always names the band
        ("Beatles", "The Beatles", False, True),
        ("Beatles", "The Beatles", True, False),
        ("the Eagles", "Eagles", True, True),
        ("THE Eagles", "Eagles", True, True),  # "the" in any case
        ("Eagles", "Eagles", True, False),  # a common word without "the": the animal
        ("Eagles", "Eagles", False, True),
        ("the eagles", "Eagles", False, False),  # capitals must match the label
        ("eagles", "Eagles", False, False),
        ("a Eagles", "Eagles", False, False),
        ("the  Rolling   Stones", "The Rolling Stones", True, True),  # spaces collapsed
        ("Eagles", None, False, False),
    ],
)
def test_names_band(typed: str, label: str | None, common: bool, expected: bool) -> None:
    assert names_band(typed, label, common) is expected


class SingularLookup(ExactMatches):
    """ExactMatches for the plural query; the singular search returns `singular` instead."""

    def __init__(
        self, plural: tuple[str, EntityClasses], singular: list[tuple[str, EntityClasses]]
    ) -> None:
        super().__init__(plural, label="Gizmos", classes=dict(singular))
        self.singular = singular
        self.searches: list[str] = []

    async def search(self, name: str) -> list[Candidate]:
        self.searches.append(name)
        if name == "gizmos":
            return await super().search(name)
        return [Candidate(qid, name, name) for qid, _ in self.singular]


@pytest.mark.parametrize(
    ("singular", "common"),
    [
        ([("K", EntityClasses((TAXON,)))], True),
        ([("K", EntityClasses(("Q55983715",)))], True),  # organisms known by a common name
        ([("K", EntityClasses((), ("Q1",)))], True),  # anything with a P279
        ([("N", EntityClasses((FAMILY_NAME,))), ("K", EntityClasses((TAXON,)))], True),
        ([("M", EntityClasses((MAGAZINE,)))], False),  # Live "rolling stone": magazines only
        ([("A", EntityClasses((ASTEROID,)))], False),  # an individual, not a kind
        ([("N", EntityClasses((FAMILY_NAME,)))], False),
        ([], False),  # Live "beatle": no exact match
    ],
)
async def test_a_bands_name_is_common_when_its_singular_is_a_kind(
    cache: WikidataCache, singular: list[tuple[str, EntityClasses]], common: bool
) -> None:
    lookup = SingularLookup(("B", EntityClasses((MUSICAL_GROUP,))), singular)
    check = await resolve("gizmos", lookup, load_class_map())
    assert (check.qid, check.band, check.common) == ("B", True, common)
    assert lookup.searches == ["gizmos", "gizmo"]  # one extra search, for the singular
    bare = await check_names(["Gizmos"], lookup=lookup, cache=cache)
    assert bare.reason == (None if common else "real_person")
    assert (await check_names(["the Gizmos"], lookup=lookup, cache=cache)).reason == "real_person"


async def test_no_singular_search_for_non_bands_or_singular_queries() -> None:
    lookup = SingularLookup(("T", EntityClasses((TAXON,))), [])
    await resolve("gizmos", lookup, load_class_map())
    band = SingularLookup(("B", EntityClasses((MUSICAL_GROUP,))), [])
    await resolve("gizmo", band, load_class_map())
    assert (lookup.searches, band.searches) == (["gizmos"], ["gizmo"])


async def test_a_failed_singular_search_fails_open(cache: WikidataCache) -> None:
    class Down(SingularLookup):
        async def search(self, name: str) -> list[Candidate]:
            if name == "gizmo":
                raise WikidataUnavailable("down")
            return await super().search(name)

    lookup = Down(("B", EntityClasses((MUSICAL_GROUP,))), [])
    assert (await check_names(["the Gizmos"], lookup=lookup, cache=cache)).allowed
    assert await cache.get("gizmos", load_class_map().version) is None  # failures not cached


async def test_the_common_word_flag_is_cached(cache: WikidataCache) -> None:
    lookup = MockWikidataLookup()
    assert (await check_names(["the Eagles"], lookup=lookup, cache=cache)).reason == "real_person"
    cached = await cache.get("eagles", load_class_map().version)
    assert cached == NameCheck("Q900160", "Eagles", "real_person", band=True, common=True)
    assert (await check_names(["Eagles"], lookup=lookup, cache=cache)).allowed  # a cache hit


async def test_a_band_counts_only_on_the_items_own_p31(cache: WikidataCache) -> None:
    # The item is an instance of a subclass of musical group (not a listed one): never blocked.
    lookup = ExactMatches(
        ("B", EntityClasses(("SUB",))), classes={"SUB": EntityClasses((), (MUSICAL_GROUP,))}
    )
    assert (await check_names(["Gizmo"], lookup=lookup, cache=cache)).allowed


async def test_organizations_are_not_blocked(cache: WikidataCache) -> None:
    # business (Q4830453) and organization (Q43229) are not in the class map: brands stay allowed.
    for org in ["Q4830453", "Q43229"]:
        lookup = ExactMatches(("O", EntityClasses((org,))))
        assert (await check_names(["Gizmo Corp"], lookup=lookup, cache=cache)).allowed


async def test_a_non_demoted_match_beats_the_band(cache: WikidataCache) -> None:
    lookup = ExactMatches(("B", EntityClasses((ROCK_BAND,))), ("T", EntityClasses((TAXON,))))
    assert (await check_names(["Gizmo"], lookup=lookup, cache=cache)).allowed


# --- Weapons of mass destruction --------------------------------------------------------------


@pytest.mark.parametrize("parent", [WMD, NUCLEAR_WEAPON])
async def test_weapons_of_mass_destruction_are_weapons(cache: WikidataCache, parent: str) -> None:
    lookup = ExactMatches(("W", EntityClasses((), (parent,))))
    verdict = await check_names(["a gizmo"], lookup=lookup, cache=cache)
    assert (verdict.reason, verdict.layer) == ("weapon", "wikidata")


# --- The version bump --------------------------------------------------------------------------


async def test_the_version_bump_ignores_rows_cached_before_it(cache: WikidataCache) -> None:
    # Version 2 had no band class, so it cached the Beatles as "no objection".
    await cache.put("beatles", NameCheck("Q900130", "The Beatles", None), 2)
    assert await cache.get("beatles", 2) is not None
    verdict = await check_names(["the Beatles"], lookup=MockWikidataLookup(), cache=cache)
    assert (verdict.reason, verdict.layer) == ("real_person", "wikidata")
    version = load_class_map().version
    assert await cache.get("beatles", version) == NameCheck(
        "Q900130", "The Beatles", "real_person", band=True
    )
