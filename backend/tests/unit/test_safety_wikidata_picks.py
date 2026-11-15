"""A04 part 3a (#27): which exact Wikidata match is picked (creative works and bands demoted),
bands blocked as real people for proper names only (ALL CAPS included, and bands that lost the
pick to a kind item), the weapons-of-mass-destruction class, the classes_version bump and
migration 004; part 3b (D-59): sports teams follow the band rule. Mock Wikidata and a temp cache
only; no network."""

import shutil
import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.db.migrate import MIGRATIONS_DIR, apply_migrations
from app.safety.wikidata import (
    Candidate,
    EntityClasses,
    MockWikidataLookup,
    NameCheck,
    WikidataCache,
    WikidataUnavailable,
    check_names,
    load_class_map,
    names_group,
    resolve,
)

MAGAZINE, FILM, ALBUM = "Q41298", "Q11424", "Q482994"
MUSICAL_GROUP, ROCK_BAND = "Q215380", "Q5741069"
GIRL_GROUP, BOY_BAND, METAL_BAND, DUO = "Q641066", "Q216337", "Q56816954", "Q9212979"
TAXON, FAMILY_NAME, COMMON_NAME = "Q16521", "Q101352", "Q55983715"
MALE_NAME, FEMALE_NAME, UNISEX_NAME = "Q12308941", "Q11879590", "Q3409032"
ASTEROID = "Q3863"
WMD, NUCLEAR_WEAPON = "Q49394", "Q12802"
SPORTS_TEAM, BASKETBALL_TEAM, FOOTBALL_CLUB = "Q12973014", "Q13393265", "Q476028"
BUSINESS, CAR_BRAND = "Q4830453", "Q10429667"


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
    assert class_map.version >= 6
    bands = {MUSICAL_GROUP, ROCK_BAND, GIRL_GROUP, BOY_BAND, METAL_BAND, DUO}
    assert bands <= class_map.groups
    assert {MAGAZINE, FILM, ALBUM} | bands <= class_map.demoted
    assert {class_map.reasons[band] for band in bands} == {"real_person"}
    assert {MALE_NAME, FEMALE_NAME, UNISEX_NAME} <= class_map.name_items
    assert {TAXON, COMMON_NAME} <= class_map.kinds
    assert class_map.common_kinds == {COMMON_NAME}  # a bare taxon is not a common word
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
        # ALL CAPS reads as the band's name, the same as matching capitals.
        (["THE BEATLES"], "real_person"),
        (["BEATLES"], "real_person"),
        (["The BEATLES"], "real_person"),
        (["THE EAGLES"], "real_person"),
        # A band that lost the pick to a kind item still blocks a name that names it.
        (["the Police"], "real_person"),  # the item "police" (with a P279) wins the pick
        (["The Police"], "real_person"),
        (["THE POLICE"], "real_person"),
        (["Police"], None),  # bare: the common word "police"
        (["the police"], None),
        (["a police"], None),
        (["the Doors"], "real_person"),  # "doorway" matches through its alias "doors"
        (["Doors"], None),
        (["Metallica"], "real_person"),  # its rival is a bare moth genus, not a common word
        (["the Metallica"], "real_person"),
        (["metallica"], None),
        (["the Grizzly Bear"], None),  # the band's label has no "The" of its own: the animal
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
    assert cached == NameCheck("B", "Eagles", "real_person", group=True)
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
        # ALL CAPS is compared ignoring case; mixed capitals still must match.
        ("THE BEATLES", "The Beatles", False, True),
        ("BEATLES", "The Beatles", False, True),
        ("The BEATLES", "The Beatles", True, True),
        ("THE EAGLES", "Eagles", True, True),
        ("EAGLES", "Eagles", True, False),  # a common word without "the"
        ("EAGLES", "Eagles", False, True),
        ("BeAtLeS", "The Beatles", False, False),
    ],
)
def test_names_group(typed: str, label: str | None, common: bool, expected: bool) -> None:
    assert names_group(typed, label, common) is expected


@pytest.mark.parametrize(
    ("typed", "label", "common", "expected"),
    [
        # A common-word kind took the pick: only the full label, with its own "The", names it.
        ("the Police", "The Police", True, True),
        ("THE POLICE", "The Police", True, True),
        ("Police", "The Police", True, False),
        ("the police", "The Police", True, False),
        ("the Grizzly Bear", "Grizzly Bear", True, False),
        ("Grizzly Bear", "Grizzly Bear", True, False),
        # The rival kind is not a common word (a bare taxon): as for a band that won the pick.
        ("Metallica", "Metallica", False, True),
        ("the Metallica", "Metallica", False, True),
        ("METALLICA", "Metallica", False, True),
        ("metallica", "Metallica", False, False),
    ],
)
def test_names_group_for_a_band_that_lost_the_pick(
    typed: str, label: str, common: bool, expected: bool
) -> None:
    assert names_group(typed, label, common, lost=True) is expected


@pytest.mark.parametrize(
    ("query", "lost", "common"),
    [
        ("police", "The Police", True),
        ("doors", "The Doors", True),
        ("metallica", "Metallica", False),
        ("grizzly bear", "Grizzly Bear", True),
        ("bulldozer", "Bulldozer", True),
        ("dragon", None, False),  # a magazine, not a band
        ("beatles", None, False),  # the band won the pick
        ("wolves", None, False),  # a band matching only through an alias is never recorded
    ],
)
async def test_a_band_that_lost_the_pick_is_recorded(
    query: str, lost: str | None, common: bool
) -> None:
    check = await resolve(query, MockWikidataLookup(), load_class_map())
    assert (check.lost_group, check.common if lost else False) == (lost, common)
    assert not (check.group and lost)


@pytest.mark.parametrize(
    ("rival", "blocks"),
    [
        (EntityClasses((TAXON,)), True),  # a bare taxon is not a common word
        (EntityClasses((COMMON_NAME,)), False),  # organisms known by a common name
        (EntityClasses((TAXON,), ("Q1",)), False),  # anything with a P279
    ],
)
async def test_a_lost_bands_bare_name_blocks_unless_a_common_word_shares_it(
    cache: WikidataCache, rival: EntityClasses, blocks: bool
) -> None:
    lookup = ExactMatches(("B", EntityClasses((MUSICAL_GROUP,))), ("K", rival), label="Gizmo")
    check = await resolve("gizmo", lookup, load_class_map())
    assert (check.qid, check.lost_group, check.common) == ("K", "Gizmo", not blocks)
    verdict = await check_names(["Gizmo"], lookup=lookup, cache=cache)
    assert verdict.reason == ("real_person" if blocks else None)


async def test_a_lost_band_is_cached(cache: WikidataCache) -> None:
    lookup = MockWikidataLookup()
    assert (await check_names(["the Police"], lookup=lookup, cache=cache)).reason == "real_person"
    cached = await cache.get("police", load_class_map().version)
    assert cached == NameCheck("Q900301", "police", None, common=True, lost_group="The Police")
    assert (await check_names(["Police"], lookup=lookup, cache=cache)).allowed  # a cache hit
    assert (await check_names(["THE POLICE"], lookup=lookup, cache=cache)).reason == "real_person"


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
    assert (check.qid, check.group, check.common) == ("B", True, common)
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
    assert cached == NameCheck("Q900160", "Eagles", "real_person", group=True, common=True)
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


# --- Sports teams: the band rule (D-59) -------------------------------------------------------


class AliasMatch(ExactMatches):
    """ExactMatches where every item is labelled `label` and matched only through the alias
    "Gizmos" (as live "Lakers" matches "Los Angeles Lakers")."""

    async def search(self, name: str) -> list[Candidate]:
        return [Candidate(qid, self.label or name, "Gizmos") for qid, _ in self.items]


def test_the_class_map_lists_sports_teams_as_groups() -> None:
    class_map = load_class_map()
    assert class_map.version >= 8
    teams = {SPORTS_TEAM, BASKETBALL_TEAM, FOOTBALL_CLUB}
    assert teams <= class_map.teams <= class_map.groups
    assert MUSICAL_GROUP in class_map.groups - class_map.teams
    assert {class_map.reasons[team] for team in class_map.teams} == {"real_person"}
    assert class_map.teams <= class_map.instance_only


@pytest.mark.parametrize(
    ("names", "reason"),
    [
        (["the Lakers"], "real_person"),  # "the" + the alias the team matched through
        (["The Lakers"], "real_person"),
        (["Lakers"], "real_person"),  # "laker" has no kind item: not a common word
        (["the lakers"], None),  # capitals must match the name
        (["lakers"], None),
        (["a Laker"], None),
        (["the Bulls"], "real_person"),
        (["Bulls"], None),  # "bull" is an animal: bare "Bulls" is the animals
        (["bulls"], None),
        (["Bulls", "the Bulls"], "real_person"),  # one typed name names the team
        (["Los Angeles Lakers"], "real_person"),  # the full label, not a common word
        # #310: full team names (live search order), and the nickname "Wolves".
        (["the Chicago Bulls"], "real_person"),
        (["Chicago Bulls"], "real_person"),
        (["the Philadelphia Eagles"], "real_person"),
        (["the chicago bulls"], None),  # lowercase after an article reads as a common noun
        (["the Wolves"], "real_person"),  # "the" + the alias of the club that is picked
        (["Wolves"], None),  # "wolf" is an animal (result 6): bare "Wolves" is the animals
        (["wolves"], None),
        # Companies, organizations and brands stay allowed: the Jeep car brand is a business.
        (["a Jeep"], None),
        (["Jeep"], None),
    ],
)
async def test_mock_fixture_team_examples(
    cache: WikidataCache, names: list[str], reason: str | None
) -> None:
    verdict = await check_names(names, lookup=MockWikidataLookup(), cache=cache)
    assert verdict.reason == reason
    assert verdict.layer == ("wikidata" if reason else None)


@pytest.mark.parametrize(
    ("query", "picked", "label", "common"),
    [
        ("lakers", "Q121783", "Lakers", False),  # picked through its alias; label is the alias
        ("bulls", "Q128109", "Bulls", True),  # beats the family name and the rugby "Bulls"
        ("wolves", "Q900171", "Wolves", True),  # the band matched only an alias; the club wins
        ("chicago bulls", "Q128109", "Chicago Bulls", False),  # the first of two teams
        ("philadelphia eagles", "Q219714", "Philadelphia Eagles", False),
    ],
)
async def test_the_mock_fixture_picks_teams_by_alias(
    query: str, picked: str, label: str, common: bool
) -> None:
    check = await resolve(query, MockWikidataLookup(), load_class_map())
    assert (check.qid, check.label, check.group, check.common) == (picked, label, True, common)


@pytest.mark.parametrize(
    ("names", "reason"),
    [
        (["the Gizmos"], "real_person"),
        (["Gizmos"], "real_person"),
        (["the gizmos"], None),
        (["Gizmo City Gizmos"], "real_person"),  # the full label names the team too
    ],
)
async def test_a_team_blocks_by_the_alias_it_matched(
    cache: WikidataCache, names: list[str], reason: str | None
) -> None:
    lookup = AliasMatch(("T", EntityClasses((BASKETBALL_TEAM,))), label="Gizmo City Gizmos")
    assert (await check_names(names, lookup=lookup, cache=cache)).reason == reason


async def test_a_band_still_needs_its_label_not_an_alias(cache: WikidataCache) -> None:
    lookup = AliasMatch(("B", EntityClasses((MUSICAL_GROUP,))), label="Gizmo City Gizmos")
    check = await resolve("gizmos", lookup, load_class_map())
    assert check.qid is None  # passed over, like the mock "Sharks" band
    assert (await check_names(["the Gizmos"], lookup=lookup, cache=cache)).allowed


@pytest.mark.parametrize("team", [SPORTS_TEAM, BASKETBALL_TEAM, FOOTBALL_CLUB])
async def test_a_team_yields_to_a_kind_item(cache: WikidataCache, team: str) -> None:
    lookup = ExactMatches(("T", EntityClasses((team,))), ("K", EntityClasses((TAXON,))))
    check = await resolve("gizmos", lookup, load_class_map())
    assert (check.qid, check.group) == ("K", False)
    assert (await check_names(["the Gizmos"], lookup=lookup, cache=cache)).allowed


async def test_a_team_that_lost_the_pick_follows_the_band_rule(cache: WikidataCache) -> None:
    # Teams keep the lost-pick rule (D-59: teams block like bands). The mock "heat": the kind
    # item "heat" (a P279, so a common word) wins the pick over the Miami Heat, which matched
    # through its "Heat" alias. The team is recorded, but its name has no "The" of its own, so
    # like "the Grizzly Bear" no wording names it here; the classifier is the remaining layer.
    check = await resolve("heat", MockWikidataLookup(), load_class_map())
    assert (check.qid, check.group, check.lost_group, check.common) == (
        "Q900331", False, "Heat", True,
    )  # fmt: skip
    for typed in ["the Heat", "THE HEAT", "Heat", "the heat"]:
        assert (await check_names([typed], lookup=MockWikidataLookup(), cache=cache)).allowed
    # When the rival kind is not a common word (a bare taxon), the team's alias blocks, the
    # same as "Metallica".
    lookup = AliasMatch(
        ("T", EntityClasses((BASKETBALL_TEAM,))), ("K", EntityClasses((TAXON,))),
        label="Gizmo City Gizmos",
    )  # fmt: skip
    check = await resolve("gizmos", lookup, load_class_map())
    assert (check.qid, check.lost_group, check.common) == ("K", "Gizmos", False)
    for typed, reason in [
        ("Gizmos", "real_person"),
        ("the Gizmos", "real_person"),
        ("gizmos", None),
    ]:
        assert (await check_names([typed], lookup=lookup, cache=cache)).reason == reason


async def test_the_yankees_is_a_known_miss(cache: WikidataCache) -> None:
    # Known limit (#310, docs/safety.md): live "yankees" ranks "Americans" first, then the New
    # York Yankees (alias "Yankees"), with the kind "Yankee" (alias "Yankees", a P279) in the top
    # 5. The team loses the pick to a common-word kind and its alias has no "The" of its own (the
    # "heat" shape above), so no wording names it here; the classifier blocks it (case team-07).
    check = await resolve("yankees", MockWikidataLookup(), load_class_map())
    assert (check.qid, check.reason, check.group) == ("Q846570", None, False)
    assert (check.lost_group, check.common) == ("Yankees", True)
    for typed in ["the Yankees", "Yankees", "the yankees"]:
        assert (await check_names([typed], lookup=MockWikidataLookup(), cache=cache)).allowed


async def test_a_club_that_is_also_a_business_is_still_a_team(cache: WikidataCache) -> None:
    # Live clubs often have more P31 values (Wolverhampton Wanderers: three team classes); any
    # group class makes the item a group, so the wording rule still decides.
    singular = [("K", EntityClasses((TAXON,)))]
    lookup = SingularLookup(("T", EntityClasses((FOOTBALL_CLUB, BUSINESS))), singular)
    check = await resolve("gizmos", lookup, load_class_map())
    assert (check.qid, check.reason, check.group, check.common) == ("T", "real_person", True, True)
    assert (await check_names(["Gizmos"], lookup=lookup, cache=cache)).allowed
    assert (await check_names(["the Gizmos"], lookup=lookup, cache=cache)).reason == "real_person"


async def test_the_common_word_check_reads_past_the_top_five(cache: WikidataCache) -> None:
    # Live "wolf": five other "Wolf" items rank before the grey wolf, so bare "Wolves" (the
    # Wolverhampton Wanderers nickname) must still read as the animals.
    others = [(f"N{i}", EntityClasses((FAMILY_NAME,))) for i in range(5)]
    lookup = SingularLookup(
        ("T", EntityClasses((FOOTBALL_CLUB,))), [*others, ("K", EntityClasses((TAXON,)))]
    )
    assert (await resolve("gizmos", lookup, load_class_map())).common
    assert (await check_names(["Gizmos"], lookup=lookup, cache=cache)).allowed
    assert (await check_names(["the Gizmos"], lookup=lookup, cache=cache)).reason == "real_person"


async def test_the_team_flags_are_cached(cache: WikidataCache) -> None:
    lookup, version = MockWikidataLookup(), load_class_map().version
    assert (await check_names(["the Bulls"], lookup=lookup, cache=cache)).reason == "real_person"
    assert (await check_names(["the Lakers"], lookup=lookup, cache=cache)).reason == "real_person"
    bulls = NameCheck("Q128109", "Bulls", "real_person", group=True, common=True)
    assert await cache.get("bulls", version) == bulls
    lakers = NameCheck("Q121783", "Lakers", "real_person", group=True)
    assert await cache.get("lakers", version) == lakers
    # Cache hits: the wording rule is redone from the stored flags and name.
    assert (await check_names(["Bulls"], lookup=lookup, cache=cache)).allowed
    assert (await check_names(["Lakers"], lookup=lookup, cache=cache)).reason == "real_person"
    assert (await check_names(["lakers"], lookup=lookup, cache=cache)).allowed


@pytest.mark.parametrize("org", [BUSINESS, CAR_BRAND, "Q43229"])  # Q43229: organization
async def test_companies_and_brands_are_not_teams(cache: WikidataCache, org: str) -> None:
    lookup = ExactMatches(("O", EntityClasses((org,))), label="Gizmos")
    check = await resolve("gizmos", lookup, load_class_map())
    assert (check.qid, check.reason, check.group) == ("O", None, False)
    assert (await check_names(["the Gizmos"], lookup=lookup, cache=cache)).allowed


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
        "Q900130", "The Beatles", "real_person", group=True
    )


# --- Migration 004 -----------------------------------------------------------------------------


def test_migration_004_adds_the_group_columns_to_an_existing_cache(tmp_path: Path) -> None:
    # Apply 003 alone, store a row, then apply 004: the old row gets the defaults, once.
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    shutil.copy(MIGRATIONS_DIR / "003-wikidata-safety-cache.sql", migrations)
    connection = sqlite3.connect(tmp_path / "app.db")
    connection.row_factory = sqlite3.Row
    try:
        assert apply_migrations(connection, migrations) == ["003-wikidata-safety-cache.sql"]
        with connection:
            connection.execute(
                "INSERT INTO wikidata_safety_cache VALUES ('moon', 'Q405', 'Moon', 'out_of_scope', "
                "5, '2026-11-10T00:00:00+00:00')"
            )
        shutil.copy(MIGRATIONS_DIR / "004-wikidata-cache-band.sql", migrations)
        assert apply_migrations(connection, migrations) == ["004-wikidata-cache-band.sql"]
        row = connection.execute(
            "SELECT qid, grouped, grouped_common, grouped_lost_label FROM wikidata_safety_cache"
        ).fetchone()
        assert tuple(row) == ("Q405", 0, 0, None)
        assert apply_migrations(connection, migrations) == []
    finally:
        connection.close()
