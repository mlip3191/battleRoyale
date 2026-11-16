"""#316: bands labelled "The <name>" ("the Who", "the Cure", "the Animals") block at the Wikidata
layer. The search for the bare name never reaches them, so "the" + a proper name also searches
"the " + the name, at the same time, and caches the answer under that text. Mock Wikidata and a
temp cache only; no network."""

import asyncio
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

MUSICAL_GROUP, ALBUM = "Q215380", "Q482994"


@pytest.fixture
def cache(tmp_path: Path) -> WikidataCache:
    return WikidataCache(tmp_path / "app.db")


class Recording(MockWikidataLookup):
    """The mock fixture, remembering every search text."""

    def __init__(self) -> None:
        super().__init__()
        self.searched: list[str] = []

    async def search(self, name: str) -> list[Candidate]:
        self.searched.append(name)
        return await super().search(name)


class Down:
    """Wikidata that is never reachable: only the cache can answer."""

    async def search(self, name: str) -> list[Candidate]:
        raise AssertionError(f"searched '{name}' instead of using the cache")

    async def classes(self, qids: Sequence[str]) -> dict[str, EntityClasses]:
        raise AssertionError("read classes instead of using the cache")


@pytest.mark.parametrize(
    "names",
    [
        ["the Who"],
        ["the Cure"],
        ["the Animals"],
        ["the Strokes"],
        ["the Cars"],
        ["The Who"],
        ["THE WHO"],  # ALL CAPS matches, as for "THE BEATLES"
        ["who", "the Who"],  # the model's entity plus the user's text
    ],
)
async def test_a_band_labelled_the_name_blocks_as_a_real_person(
    cache: WikidataCache, names: list[str]
) -> None:
    verdict = await check_names(names, lookup=MockWikidataLookup(), cache=cache)
    assert (verdict.reason, verdict.layer) == ("real_person", "wikidata")


@pytest.mark.parametrize(
    "names",
    [
        ["Who"],  # bare: the search for "who" has no band
        ["WHO"],  # the World Health Organization
        ["who"],
        ["the who"],  # lowercase after "the": a common noun
        ["the animals"],  # plural animals
        ["the cure"],
        ["eagles"],
        ["Eagles"],
    ],
)
async def test_the_bare_name_and_lowercase_forms_stay_allowed(
    cache: WikidataCache, names: list[str]
) -> None:
    verdict = await check_names(names, lookup=MockWikidataLookup(), cache=cache)
    assert verdict.reason is None


@pytest.mark.parametrize(
    ("names", "searched"),
    [
        (["the Who"], {"who", "the who"}),
        (["Who"], {"who"}),
        (["WHO"], {"who"}),
        (["the who"], {"who"}),  # a common noun can never name the band, so no extra search
    ],
)
async def test_only_the_plus_a_proper_name_searches_the_the_form(
    cache: WikidataCache, names: list[str], searched: set[str]
) -> None:
    lookup = Recording()
    await check_names(names, lookup=lookup, cache=cache)
    assert set(lookup.searched) == searched


class Together(MockWikidataLookup):
    """The mock fixture, where the search for "who" only answers once the search for "the who"
    has started: a lookup that ran them one after the other would never finish."""

    def __init__(self) -> None:
        super().__init__()
        self.the_started = asyncio.Event()

    async def search(self, name: str) -> list[Candidate]:
        if name == "the who":
            self.the_started.set()
        else:
            await self.the_started.wait()
        return await super().search(name)


async def test_both_searches_run_at_the_same_time() -> None:
    check = await asyncio.wait_for(
        resolve("who", Together(), load_class_map(), the_form=True), timeout=1
    )
    assert (check.lost_group, check.common) == ("The Who", True)


async def test_the_the_form_is_cached_under_its_own_text(cache: WikidataCache) -> None:
    version = load_class_map().version
    first = await check_names(["the Who"], lookup=MockWikidataLookup(), cache=cache)
    assert first.reason == "real_person"
    full = await cache.get("the who", version)
    assert full is not None and (full.qid, full.lost_group, full.common) == (
        "Q7817",
        "The Who",
        True,
    )
    plain = await cache.get("who", version)  # the "who" search alone: no band
    assert plain is not None and (plain.qid, plain.lost_group, plain.common) == (
        "Q7817",
        None,
        False,
    )
    # Cache hits give the same answers, with Wikidata down.
    again = await check_names(["the Who"], lookup=Down(), cache=cache)
    assert (again.reason, again.layer) == ("real_person", "wikidata")
    assert (await check_names(["Who"], lookup=Down(), cache=cache)).reason is None
    assert (await check_names(["THE WHO"], lookup=Down(), cache=cache)).reason == "real_person"


async def test_a_plain_lookup_never_answers_a_the_lookup(cache: WikidataCache) -> None:
    version = load_class_map().version
    assert (await check_names(["Who"], lookup=MockWikidataLookup(), cache=cache)).reason is None
    assert await cache.get("the who", version) is None
    lookup = Recording()
    verdict = await check_names(["the Who"], lookup=lookup, cache=cache)
    assert verdict.reason == "real_person"
    assert set(lookup.searched) == {"who", "the who"}


class TheSearch:
    """Nothing matches the plain query; the "the" search returns these items, all labelled
    "The Zorbs"."""

    def __init__(self, *items: tuple[str, EntityClasses]) -> None:
        self.entities = dict(items)

    async def search(self, name: str) -> list[Candidate]:
        if name != "the zorbs":
            return []
        return [Candidate(qid, "The Zorbs", "The Zorbs") for qid in self.entities]

    async def classes(self, qids: Sequence[str]) -> dict[str, EntityClasses]:
        return {q: self.entities[q] for q in qids}


async def test_only_a_group_labelled_the_name_is_kept() -> None:
    class_map = load_class_map()
    album = ("Q1", EntityClasses((ALBUM,)))
    band = ("Q2", EntityClasses((MUSICAL_GROUP,)))
    only_album = await resolve("zorbs", TheSearch(album), class_map, the_form=True)
    assert only_album.lost_group is None
    album_then_band = await resolve("zorbs", TheSearch(album, band), class_map, the_form=True)
    assert (album_then_band.lost_group, album_then_band.common) == ("The Zorbs", True)
    without_the = await resolve("zorbs", TheSearch(album, band), class_map)
    assert without_the.lost_group is None
