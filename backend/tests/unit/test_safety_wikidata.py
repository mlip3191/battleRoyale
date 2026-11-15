"""Safety layer 3: the Wikidata name check, its cache, and its live and mock lookups (offline)."""

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from app.db.connection import connect
from app.safety.verdict import BLOCKED_REASONS
from app.safety.wikidata import (
    CLASSES_PATH,
    MOCK_FIXTURE,
    TIMEOUT_S,
    Candidate,
    ClassMap,
    EntityClasses,
    LiveWikidataLookup,
    MockWikidataLookup,
    WikidataCache,
    WikidataUnavailable,
    check_names,
    load_class_map,
    lookup_query,
    resolve,
)

START = datetime(2026, 11, 10, tzinfo=UTC)
FIREARM = "Q12796"
ASTRO = "Q6999"  # astronomical object
FAMILY_NAME, GIVEN_NAME, DISAMBIGUATION = "Q101352", "Q202444", "Q4167410"


class Clock:
    """A settable 'now' for TTL tests."""

    def __init__(self) -> None:
        self.time = START

    def __call__(self) -> datetime:
        return self.time


class FakeLookup:
    """In-memory Wikidata that counts calls; a chain of classes leads to a firearm."""

    def __init__(self, chain_depth: int = 2, fail: Exception | None = None) -> None:
        self.calls = 0
        self.fail = fail
        # "gizmo" (Q1) P279 -> C0 -> C1 ... -> C<chain_depth-1> -> firearm.
        chain = [f"C{n}" for n in range(chain_depth)] + [FIREARM]
        self.entities = {"Q1": EntityClasses(subclass_of=(chain[0],))}
        for child, parent in zip(chain, chain[1:], strict=False):
            self.entities[child] = EntityClasses(subclass_of=(parent,))

    async def search(self, name: str) -> list[Candidate]:
        self.calls += 1
        if self.fail:
            raise self.fail
        return [Candidate("Q1", "Gizmo", "gizmo")] if name == "gizmo" else []

    async def classes(self, qids: Sequence[str]) -> dict[str, EntityClasses]:
        self.calls += 1
        return {q: self.entities[q] for q in qids if q in self.entities}


class SlowLookup(FakeLookup):
    """Never answers in time."""

    async def search(self, name: str) -> list[Candidate]:
        await asyncio.sleep(10)
        return []


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def cache(tmp_path: Path, clock: Clock) -> WikidataCache:
    return WikidataCache(tmp_path / "app.db", now=clock)


def test_the_class_map_uses_only_contract_reasons() -> None:
    class_map = load_class_map()
    assert class_map.version >= 3
    assert set(class_map.reasons.values()) <= set(BLOCKED_REASONS)
    # Only human and the band classes count on the item's own P31 alone.
    assert class_map.instance_only == {"Q5"} | class_map.bands
    assert {"Q215380", "Q5741069"} <= class_map.bands  # musical group, rock band
    assert {FAMILY_NAME, GIVEN_NAME, DISAMBIGUATION} <= class_map.name_items
    assert not class_map.name_items & set(class_map.reasons)
    assert not class_map.name_items & class_map.demoted
    assert not class_map.kinds & (class_map.demoted | class_map.name_items)


class NameItemsFirst(FakeLookup):
    """Like live 'the Moon': name/meta items come first among the exact matches."""

    def __init__(self, first: list[EntityClasses], second: EntityClasses | None) -> None:
        super().__init__()
        self.items = [(f"N{n}", c) for n, c in enumerate(first)]
        if second is not None:
            self.items.append(("Q405", second))
        self.entities.update(self.items)

    async def search(self, name: str) -> list[Candidate]:
        return [Candidate(qid, "Moon", "Moon") for qid, _ in self.items]


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        # Family name, then the Moon: the name item is skipped.
        ([EntityClasses((FAMILY_NAME,))], EntityClasses((ASTRO,)), ("Q405", "out_of_scope")),
        # Given name and disambiguation page are skipped too.
        (
            [EntityClasses((GIVEN_NAME,)), EntityClasses((DISAMBIGUATION,))],
            EntityClasses((ASTRO,)),
            ("Q405", "out_of_scope"),
        ),
        # Only name items: no match, no verdict.
        ([EntityClasses((FAMILY_NAME,))], None, (None, None)),
        # A name item that is also something else is kept (P31 not only name classes).
        ([EntityClasses((FAMILY_NAME, ASTRO))], EntityClasses(("Q1",)), ("N0", "out_of_scope")),
        # An item with no P31 is kept.
        ([EntityClasses()], EntityClasses((ASTRO,)), ("N0", None)),
    ],
)
async def test_name_items_are_skipped_when_picking_the_top_match(
    cache: WikidataCache,
    first: list[EntityClasses],
    second: EntityClasses | None,
    expected: tuple[str | None, str | None],
) -> None:
    check = await resolve("moon", NameItemsFirst(first, second), load_class_map())
    assert (check.qid, check.reason) == expected


async def test_a_skipped_match_without_class_data_gives_no_verdict(cache: WikidataCache) -> None:
    lookup = NameItemsFirst([EntityClasses((FAMILY_NAME,))], EntityClasses((ASTRO,)))
    del lookup.entities["N0"]
    with pytest.raises(WikidataUnavailable):
        await resolve("moon", lookup, load_class_map())
    assert (await check_names(["the Moon"], lookup=lookup, cache=cache)).allowed


@pytest.mark.parametrize(
    ("lookup", "logged"),
    [
        (SlowLookup(), "Wikidata check skipped (TimeoutError)"),
        (FakeLookup(fail=WikidataUnavailable("down")), "skipped (WikidataUnavailable: down)"),
    ],
)
async def test_a_skipped_check_logs_the_error_type(
    cache: WikidataCache,
    lookup: FakeLookup,
    logged: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("app.safety.wikidata.TIMEOUT_S", 0.05)
    await check_names(["gizmo"], lookup=lookup, cache=cache)
    assert logged in caplog.text


def test_the_lookup_time_limit_fits_the_intake_budget() -> None:
    assert TIMEOUT_S == 2.5


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Napoleon", ("napoleon", True)),
        ("napoleon", ("napoleon", True)),
        ("a napoleon", ("napoleon", False)),
        ("a Napoleon", ("napoleon", True)),
        ("the emperor", ("emperor", False)),
        ("the Emperor", ("emperor", True)),
        ("The emperor", ("emperor", False)),
        ("3 gray wolves", ("gray wolf", False)),
        ("Three napoleons", ("napoleon", False)),
        ("5 Testor Blipworths", ("testor blipworth", True)),
        ("an Testor blipworth", ("testor blipworth", True)),
        ("Hercules", ("hercules", True)),
        ("the Beatles", ("beatles", True)),  # a proper name keeps its plural
        ("the beatles", ("beatle", False)),
        ("2 Beatles", ("beatle", True)),  # a count still means several of one thing
        ("a Moose-Sized Napoleon", ("napoleon", True)),  # size words still dropped
    ],
)
def test_lookup_query_reads_proper_names_from_original_casing(
    name: str, expected: tuple[str, bool]
) -> None:
    assert lookup_query(name) == expected


async def test_a_repeat_lookup_uses_the_cache(cache: WikidataCache) -> None:
    lookup = FakeLookup()
    first = await check_names(["gizmo"], lookup=lookup, cache=cache)
    calls = lookup.calls
    second = await check_names(["Gizmo"], lookup=lookup, cache=cache)
    assert first == second
    assert (first.reason, first.layer) == ("weapon", "wikidata")
    assert calls > 0 and lookup.calls == calls


@pytest.mark.parametrize(("name", "ttl_days"), [("gizmo", 30), ("unknown thing", 7)])
async def test_cache_rows_expire(
    cache: WikidataCache, clock: Clock, name: str, ttl_days: int
) -> None:
    lookup = FakeLookup()
    await check_names([name], lookup=lookup, cache=cache)
    clock.time = START + timedelta(days=ttl_days) - timedelta(minutes=1)
    calls = lookup.calls
    await check_names([name], lookup=lookup, cache=cache)
    assert lookup.calls == calls
    clock.time = START + timedelta(days=ttl_days, minutes=1)
    await check_names([name], lookup=lookup, cache=cache)
    assert lookup.calls > calls


async def test_a_new_classes_version_ignores_old_rows(cache: WikidataCache) -> None:
    lookup = FakeLookup()
    old = load_class_map()
    await check_names(["gizmo"], lookup=lookup, cache=cache, class_map=old)
    calls = lookup.calls
    new = ClassMap(old.version + 1, old.reasons, old.instance_only)
    await check_names(["gizmo"], lookup=lookup, cache=cache, class_map=new)
    assert lookup.calls > calls


@pytest.mark.parametrize("lookup", [SlowLookup(), FakeLookup(fail=WikidataUnavailable("down"))])
async def test_an_outage_fails_open_and_is_not_cached(
    cache: WikidataCache, lookup: FakeLookup, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.safety.wikidata.TIMEOUT_S", 0.05)
    verdict = await check_names(["gizmo"], lookup=lookup, cache=cache)
    assert verdict.allowed
    assert await cache.get("gizmo", load_class_map().version) is None


async def test_mock_fixture_errors_are_not_swallowed(cache: WikidataCache) -> None:
    lookup = FakeLookup(fail=LookupError("no fixture"))
    with pytest.raises(LookupError):
        await check_names(["gizmo"], lookup=lookup, cache=cache)


async def test_no_exact_match_gives_no_verdict(cache: WikidataCache) -> None:
    class NearMiss(FakeLookup):
        async def search(self, name: str) -> list[Candidate]:
            return [Candidate("Q1", "Gizmo 3000", "Gizmo 3000")]

    assert (await check_names(["gizmo"], lookup=NearMiss(), cache=cache)).allowed


@pytest.mark.parametrize(("depth", "allowed"), [(0, False), (2, False), (3, True)])
async def test_the_class_walk_climbs_two_levels(
    cache: WikidataCache, depth: int, allowed: bool
) -> None:
    verdict = await check_names(["gizmo"], lookup=FakeLookup(chain_depth=depth), cache=cache)
    assert verdict.allowed is allowed


@pytest.mark.parametrize(
    ("names", "reason"),
    [
        (["Napoleon"], "real_person"),
        (["a napoleon"], None),
        (["3 napoleons"], None),
        (["the emperor"], None),
        (["a napoleon", "Napoleon"], "real_person"),
        (["a Napoleon"], "real_person"),
        (["a Testor Blipworth"], "real_person"),
        (["the Testor Blipworth"], "real_person"),
        (["5 Testor Blipworths"], "real_person"),
        (["a testor blipworth"], None),
        (["a tesla"], None),
        (["a Tesla"], "real_person"),  # a capitalized brand that is also a person's name
        (["Robo-Tron"], "copyrighted_character"),
        (["Zeus"], "deity"),
        (["an assault rifle"], "weapon"),
        (["the Moon"], "out_of_scope"),
        (["Mercury"], "out_of_scope"),
        (["a dragon", "a toaster", "a bulldozer", "a Roman legionary", "a boxer"], None),
        (["a grizzly bear"], None),
        (["Thor"], "deity"),  # the male given name ranks first and is skipped
    ],
)
async def test_mock_fixture_examples(
    cache: WikidataCache, names: list[str], reason: str | None
) -> None:
    verdict = await check_names(names, lookup=MockWikidataLookup(), cache=cache)
    assert verdict.reason == reason
    assert verdict.layer == ("wikidata" if reason else None)


async def test_the_real_moon_shape_is_blocked_by_natural_satellite(cache: WikidataCache) -> None:
    # Live Q405: P31 three moon classes, each P279 natural satellite (Q2537), which is more than
    # two levels below astronomical object. Without Q2537 in the class map it would pass.
    class_map = load_class_map()
    verdict = await check_names(["the Moon"], lookup=MockWikidataLookup(), cache=cache)
    assert (verdict.reason, verdict.layer) == ("out_of_scope", "wikidata")
    without = ClassMap(
        class_map.version + 1,
        {q: r for q, r in class_map.reasons.items() if q != "Q2537"},
        class_map.instance_only,
        class_map.name_items,
    )
    check = await resolve("moon", MockWikidataLookup(), without)
    assert (check.qid, check.reason) == ("Q405", None)


def test_a_missing_mock_fixture_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(LookupError, match="No mock Wikidata fixture"):
        MockWikidataLookup(tmp_path / "missing.json")


async def test_a_mock_name_without_entry_or_default_fails_loudly(tmp_path: Path) -> None:
    path = tmp_path / "entities.json"
    path.write_text(json.dumps({"search": {}, "entities": {}}), encoding="utf-8")
    with pytest.raises(LookupError, match="no search entry"):
        await MockWikidataLookup(path).search("gizmo")


def test_the_mock_fixture_reaches_only_mapped_or_test_classes() -> None:
    data = json.loads(MOCK_FIXTURE.read_text(encoding="utf-8"))
    mapped = set(load_class_map(CLASSES_PATH).reasons)
    for entity in data["entities"].values():
        for qid in entity.get("P31", []) + entity.get("P279", []):
            assert qid in data["entities"] or qid in mapped, qid


async def test_the_live_lookup_sends_read_only_queries_and_reads_replies() -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.params["action"] == "wbsearchentities":
            hit = {"id": "Q42", "label": "Gizmo", "match": {"type": "alias", "text": "gizmo"}}
            return httpx.Response(200, json={"search": [hit]})
        claim = {"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}
        return httpx.Response(200, json={"entities": {"Q42": {"claims": {"P31": [claim]}}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        lookup = LiveWikidataLookup(client)
        assert await lookup.search("gizmo") == [Candidate("Q42", "Gizmo", "gizmo")]
        assert await lookup.classes(["Q42"]) == {"Q42": EntityClasses(("Q5",), ())}
    assert all(r.method == "GET" and r.url.host == "www.wikidata.org" for r in seen)
    assert seen[0].url.params["search"] == "gizmo"
    assert seen[1].url.params["ids"] == "Q42"
    assert all(r.headers["User-Agent"] for r in seen)


@pytest.mark.parametrize("attempt", range(20))
async def test_many_names_at_once_on_a_fresh_database(tmp_path: Path, attempt: int) -> None:
    # Regression for "database is locked": parallel first checks used to race on table setup.
    names = ["Zeus", "a dragon", "a toaster", "a bulldozer", "a Roman legionary", "a boxer"]
    cache = WikidataCache(tmp_path / f"fresh-{attempt}.db")
    verdict = await check_names(names, lookup=MockWikidataLookup(), cache=cache)
    assert (verdict.reason, verdict.layer) == ("deity", "wikidata")
    version = load_class_map().version
    for query in ["zeus", "dragon", "toaster", "bulldozer", "roman legionary", "boxer"]:
        assert await cache.get(query, version) is not None, query  # every write landed


async def test_a_broken_cache_database_fails_open(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cache = WikidataCache(tmp_path)  # a folder, so SQLite cannot open it
    verdict = await check_names(["Zeus"], lookup=MockWikidataLookup(), cache=cache)
    assert (verdict.reason, verdict.layer) == ("deity", "wikidata")
    assert "cache read failed" in caplog.text and "cache write skipped" in caplog.text


async def test_a_cache_os_error_fails_open(
    cache: WikidataCache, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Opening the cache raises OSError (e.g. disk or permission trouble), not sqlite3.Error.
    def broken_connect(path: Path | None = None) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr("app.safety.wikidata.connect", broken_connect)
    verdict = await check_names(["Zeus"], lookup=MockWikidataLookup(), cache=cache)
    assert (verdict.reason, verdict.layer) == ("deity", "wikidata")
    assert "cache read failed" in caplog.text and "cache write skipped" in caplog.text


@pytest.mark.parametrize(
    "checked_at", ["not a date", "2026-11-10T00:00:00", "2026-12-01T00:00+00:00"]
)
async def test_unreadable_or_future_check_dates_are_misses(
    cache: WikidataCache, checked_at: str
) -> None:
    version = load_class_map().version
    await check_names(["gizmo"], lookup=FakeLookup(), cache=cache)
    connection = connect(cache.path)
    with connection:
        connection.execute("UPDATE wikidata_safety_cache SET checked_at = ?", (checked_at,))
    connection.close()
    assert await cache.get("gizmo", version) is None


@pytest.mark.parametrize("entity", [{"id": "Q1", "missing": ""}, {"id": "Q1"}])
async def test_an_item_sent_back_missing_gives_no_verdict_and_is_not_cached(
    cache: WikidataCache, entity: dict[str, str]
) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.params["action"] == "wbsearchentities":
            return httpx.Response(200, json={"search": [{"id": "Q1", "label": "Gizmo"}]})
        return httpx.Response(200, json={"entities": {"Q1": entity}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        lookup = LiveWikidataLookup(client)
        assert await lookup.classes(["Q1"]) == {}
        verdict = await check_names(["gizmo"], lookup=lookup, cache=cache)
    assert verdict.allowed
    assert await cache.get("gizmo", load_class_map().version) is None


async def test_class_reads_go_in_batches_of_fifty() -> None:
    sizes: list[int] = []

    def answer(request: httpx.Request) -> httpx.Response:
        ids = request.url.params["ids"].split("|")
        sizes.append(len(ids))
        return httpx.Response(200, json={"entities": {q: {"claims": {}} for q in ids}})

    qids = [f"Q{n}" for n in range(1, 121)]
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        found = await LiveWikidataLookup(client).classes(qids)
    assert sizes == [50, 50, 20]
    assert set(found) == set(qids)


@pytest.mark.parametrize("response", [httpx.Response(503), httpx.Response(200, text="not json")])
async def test_live_lookup_errors_raise_unavailable(response: httpx.Response) -> None:
    transport = httpx.MockTransport(lambda request: response)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(WikidataUnavailable):
            await LiveWikidataLookup(client).search("gizmo")
