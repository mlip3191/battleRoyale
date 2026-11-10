"""Safety layer 3 (A04 part 2): look fighter names up on Wikidata and block D-38 classes.

check_names() finds each name's top exact Wikidata match (passing over name items, bands when a
kind item matched too, and creative works while another exact match is left), reads its classes
(P31 and P279, then P279 up to two more levels), and blocks it if they include a class in
wikidata_classes.yaml. A band blocks only when typed as "the" + its label, or as its bare label
when that is not a common word ("Beatles" blocks, "Eagles" does not: "eagle" is an animal).
Results are cached in SQLite. This layer fails open: if Wikidata is slow or down, it gives no
verdict and the rules and classifier still decide. gate.py runs it alongside the classifier.
"""

import asyncio
import functools
import json
import logging
import re
import sqlite3
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import httpx
import yaml

from app.config import REPO_ROOT, get_settings
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.intake.rules import (
    ARTICLES,
    NUMBER_TOKEN,
    QUANTITY_WORDS,
    normalize_entity,
    read_count,
    singular_word,
)
from app.research.sources import USER_AGENT, WIKIDATA_API
from app.safety.verdict import ALLOWED, BLOCKED_REASONS, BlockedReason, SafetyVerdict, blocked

logger = logging.getLogger(__name__)

CLASSES_PATH = Path(__file__).with_name("wikidata_classes.yaml")
MOCK_FIXTURE = (
    REPO_ROOT / "backend" / "tests" / "fixtures" / "providers" / "wikidata" / "entities.json"
)
TIMEOUT_S = 2.5
"""Most time one name's lookup may take (all its calls together); no retries."""
PARENT_LEVELS = 2
"""How many P279 (subclass of) levels to climb above the entity's own classes."""
SEARCH_LIMIT = 5
MAX_IDS_PER_CALL = 50
MATCH_TTL = timedelta(days=30)
NO_MATCH_TTL = timedelta(days=7)


class WikidataUnavailable(RuntimeError):
    """Wikidata could not be reached or sent something unreadable."""


@dataclass(frozen=True)
class Candidate:
    """One wbsearchentities result: the item and the text that matched the search."""

    qid: str
    label: str
    matched_text: str


@dataclass(frozen=True)
class EntityClasses:
    """An item's P31 (instance of) and P279 (subclass of) values."""

    instance_of: tuple[str, ...] = ()
    subclass_of: tuple[str, ...] = ()


@dataclass(frozen=True)
class NameCheck:
    """What Wikidata says about one name; qid is None when nothing matched exactly. band is True
    when the picked item is a band (its block then depends on how the name was typed, see
    names_band); common is True when that band's name is also a common word ("Eagles")."""

    qid: str | None
    label: str | None
    reason: BlockedReason | None
    band: bool = False
    common: bool = False


class WikidataLookup(Protocol):
    """Search and class reads; LiveWikidataLookup in live mode, MockWikidataLookup in mock."""

    async def search(self, name: str) -> list[Candidate]: ...

    async def classes(self, qids: Sequence[str]) -> dict[str, EntityClasses]: ...


# --- Class map -------------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassMap:
    """wikidata_classes.yaml: blocked class Q-ID -> reason, in file order."""

    version: int
    reasons: dict[str, BlockedReason]
    instance_only: frozenset[str]
    name_items: frozenset[str] = frozenset()
    """skip_matches: P31 classes of name/meta items, passed over when picking the top match."""
    demoted: frozenset[str] = frozenset()
    """demote_matches plus band classes: P31 classes of creative works and bands."""
    bands: frozenset[str] = frozenset()
    """Classes marked band: true (musical group, rock band, girl group, ...)."""
    kinds: frozenset[str] = frozenset()
    """kind_matches: P31 classes that make an item a kind of thing (taxon, ...)."""

    # True when an item's P31 is non-empty and only name/meta classes (family name, etc.).
    def is_name_item(self, classes: EntityClasses) -> bool:
        return bool(classes.instance_of) and set(classes.instance_of) <= self.name_items

    # True when an item's P31 is non-empty and only creative-work or band classes (magazine, ...).
    def is_demoted(self, classes: EntityClasses) -> bool:
        return bool(classes.instance_of) and set(classes.instance_of) <= self.demoted

    # True when a demoted item is a band (its P31 includes a band class).
    def is_band(self, classes: EntityClasses) -> bool:
        return self.is_demoted(classes) and bool(set(classes.instance_of) & self.bands)

    # True when an item is a kind of thing (has a P279, or a kind P31 like taxon), not demoted.
    def is_kind(self, classes: EntityClasses) -> bool:
        kind = bool(classes.subclass_of) or bool(set(classes.instance_of) & self.kinds)
        return kind and not self.is_demoted(classes)

    # The first blocked reason among these class IDs (file order), skipping instance-only ones
    # unless allowed.
    def reason_for(self, qids: Iterable[str], *, direct: bool) -> BlockedReason | None:
        found = set(qids)
        for qid, reason in self.reasons.items():
            if qid in found and (direct or qid not in self.instance_only):
                return reason
        return None


# Read wikidata_classes.yaml once, checking every reason is a contract value.
@functools.cache
def load_class_map(path: Path = CLASSES_PATH) -> ClassMap:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    reasons: dict[str, BlockedReason] = {}
    instance_only, bands = set[str](), set[str]()
    for entry in data["classes"]:
        if entry["reason"] not in BLOCKED_REASONS:
            raise ValueError(f"{path.name}: unknown reason '{entry['reason']}' for {entry['qid']}.")
        reasons[entry["qid"]] = entry["reason"]
        if entry.get("instance_only"):
            instance_only.add(entry["qid"])
        if entry.get("band"):
            bands.add(entry["qid"])
    name_items = frozenset(entry["qid"] for entry in data.get("skip_matches") or [])
    demoted = frozenset(entry["qid"] for entry in data.get("demote_matches") or []) | bands
    kinds = frozenset(entry["qid"] for entry in data.get("kind_matches") or [])
    return ClassMap(
        int(data["classes_version"]),
        reasons,
        frozenset(instance_only),
        name_items,
        demoted,
        frozenset(bands),
        kinds,
    )


# --- Names -----------------------------------------------------------------------------------


# The text to look up and whether it reads as a proper name, judged on the original casing:
# no article or count -> proper ("Napoleon"); after one, proper only if a remaining word is
# capitalized. "a Napoleon" -> ("napoleon", True); "3 napoleons" -> ("napoleon", False). A
# proper name after just "a", "an" or "the" keeps its last word as typed, since singularizing
# would lose the name: "the Beatles" -> ("beatles", True), but "the beatles" -> ("beatle", False).
def lookup_query(name: str) -> tuple[str, bool]:
    text = name.strip()
    lowered = text.lower()
    if read_count(lowered).count is None:
        return _plain(lowered), True
    words = text.split()
    prefix = 0
    while prefix < len(words) and (
        words[prefix].lower() in QUANTITY_WORDS or NUMBER_TOKEN.match(words[prefix])
    ):
        prefix += 1
    proper = any(word[:1].isupper() for word in words[prefix:])
    query = normalize_entity(lowered).split()
    if proper and prefix == 1 and words[0].lower() in ARTICLES and query:
        typed = re.sub(r"[^a-z0-9' -]+", " ", words[-1].lower()).split()
        if typed and singular_word(typed[-1]) == query[-1]:
            query[-1] = typed[-1]  # undo the singular: "beatle" -> "beatles"
    return " ".join(query), proper


# Lowercase text with punctuation (other than ' and -) turned to spaces and spaces collapsed.
def _plain(lowered: str) -> str:
    return " ".join(re.sub(r"[^\w' -]+", " ", lowered).split())


# Every search result whose label or alias equals the query, ignoring case, in search order.
def exact_matches(query: str, candidates: Sequence[Candidate]) -> list[Candidate]:
    wanted = query.casefold()
    return [c for c in candidates if wanted in (c.label.casefold(), c.matched_text.casefold())]


# The exact match to judge, with its own classes, in search order, passing over: name and meta
# items (the family name "Moon", the given name "Thor"); a band when a kind item also matched
# (the band "Grizzly Bear" for the animal) or when its label is not the query (a band that only
# matched an alias); and creative works, used only if nothing else fits (the magazine "Dragon").
# A band otherwise keeps its search rank, so "the Beatles" the band beats the asteroid
# "8749 Beatles". Every match's classes must be known, or the pick is unsafe.
async def top_exact_match(
    query: str, lookup: WikidataLookup, class_map: ClassMap
) -> tuple[Candidate, EntityClasses] | None:
    matches = exact_matches(query, await lookup.search(query))
    if not matches:
        return None
    found = await _classes_of(lookup, list(dict.fromkeys(c.qid for c in matches)))
    usable = [(m, found[m.qid]) for m in matches if not class_map.is_name_item(found[m.qid])]
    has_kind = any(class_map.is_kind(own) for _, own in usable)
    fallback: tuple[Candidate, EntityClasses] | None = None
    for match, own in usable:
        if class_map.is_band(own):
            if not has_kind and _bare_label(match.label) == _bare_label(query):
                return match, own
        elif not class_map.is_demoted(own):
            return match, own
        else:
            fallback = fallback or (match, own)
    return fallback


# A label or query lowercased, punctuation dropped as in lookup_query, without a leading "the".
def _bare_label(text: str) -> str:
    return re.sub(r"^the ", "", _plain(text.lower()))


# True when a typed name names a band (capitals must match; "the" may be any case): a leading
# "the" plus the label without its own "the" ("the Eagles", "the Beatles"), or, only when the
# band's name is not a common word, the bare label ("Beatles" blocks; "Eagles" does not).
def names_band(typed: str, label: str | None, common: bool) -> bool:
    if label is None:
        return False
    text = " ".join(typed.split())
    bare_label = re.sub(r"^the ", "", " ".join(label.split()), flags=re.IGNORECASE)
    rest = re.sub(r"^the ", "", text, flags=re.IGNORECASE)
    if rest != text:
        return rest == bare_label
    return not common and text == bare_label


# True when a band's name is also a common word: its singular form ("eagle" for "eagles") has
# an exact match that is a kind item. The query's own exact matches had no kind item, or the
# band would not have been picked. Costs one extra search (plus a class read of its exact
# matches), only for band picks whose last word is plural.
async def is_common_word(query: str, lookup: WikidataLookup, class_map: ClassMap) -> bool:
    words = query.split()
    singular = " ".join([*words[:-1], singular_word(words[-1])]) if words else query
    if singular == query:
        return False
    matches = exact_matches(singular, await lookup.search(singular))
    if not matches:
        return False
    found = await _classes_of(lookup, list(dict.fromkeys(c.qid for c in matches)))
    return any(class_map.is_kind(found[m.qid]) for m in matches)


# Ask Wikidata about one query: top exact match, then its classes up to PARENT_LEVELS higher;
# for a band, also whether its name is a common word.
async def resolve(query: str, lookup: WikidataLookup, class_map: ClassMap) -> NameCheck:
    picked = await top_exact_match(query, lookup, class_map)
    if picked is None:
        return NameCheck(None, None, None)
    match, own = picked
    reason = class_map.reason_for(own.instance_of, direct=True)
    level, seen = set(own.instance_of) | set(own.subclass_of), set[str]()
    for climbed in range(PARENT_LEVELS + 1):
        reason = reason or class_map.reason_for(level, direct=False)
        if reason or climbed == PARENT_LEVELS or not level:
            break
        seen |= level
        parents = await _classes_of(lookup, sorted(level))
        level = {p for c in parents.values() for p in c.subclass_of} - seen
    band = class_map.is_band(own)
    common = band and await is_common_word(query, lookup, class_map)
    return NameCheck(match.qid, match.label, reason, band, common)


# Classes for every requested item; an item Wikidata sends back missing or empty means the walk
# would be incomplete, so it counts as Wikidata being unavailable (no verdict, not cached).
async def _classes_of(lookup: WikidataLookup, qids: Sequence[str]) -> dict[str, EntityClasses]:
    found = await lookup.classes(qids)
    missing = [qid for qid in qids if qid not in found]
    if missing:
        raise WikidataUnavailable(f"Wikidata sent no data for {', '.join(missing[:3])}.")
    return found


# --- Cache -----------------------------------------------------------------------------------


class WikidataCache:
    """wikidata_safety_cache rows in SQLite; stale or older-version rows count as misses.

    The cache fails open like Wikidata itself: a database or file-system error on read is a miss
    and on write is skipped, each with a warning, so a cache problem never crashes the safety check.
    """

    _setup_lock = threading.Lock()
    """Shared by all caches: only one thread at a time opens a not-yet-migrated database."""

    def __init__(
        self, path: Path | None = None, *, now: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.path = path
        self.now = now
        self._migrated = False

    # Open the database; the first open (and its migrations) runs under the lock and is only
    # marked done once it succeeds, so parallel checks never set up the table at the same time.
    def _connect(self) -> sqlite3.Connection:
        if self._migrated:
            return connect(self.path)
        with self._setup_lock:
            connection = connect(self.path)
            if not self._migrated:
                try:
                    apply_migrations(connection)
                except BaseException:
                    connection.close()
                    raise
                self._migrated = True
            return connection

    # The cached check for a query, or None if missing, expired, from another class map,
    # unreadable, or the database failed.
    async def get(self, query: str, classes_version: int) -> NameCheck | None:
        return await asyncio.to_thread(self._get, query, classes_version)

    def _get(self, query: str, classes_version: int) -> NameCheck | None:
        try:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT qid, label, reason, band, band_common, classes_version, checked_at "
                    "FROM wikidata_safety_cache WHERE query = ?",
                    (query,),
                ).fetchone()
            finally:
                connection.close()
        except (sqlite3.Error, OSError) as error:
            logger.warning("Wikidata cache read failed (%s); treating it as a miss.", error)
            return None
        if row is None or row["classes_version"] != classes_version:
            return None
        if not self._fresh(row["checked_at"], MATCH_TTL if row["qid"] else NO_MATCH_TTL):
            return None
        return NameCheck(
            row["qid"], row["label"], row["reason"], bool(row["band"]), bool(row["band_common"])
        )

    # True when checked_at is a readable, time-zoned moment no later than now and within ttl.
    def _fresh(self, checked_at: object, ttl: timedelta) -> bool:
        try:
            checked = datetime.fromisoformat(str(checked_at))
            age = self.now() - checked
        except (ValueError, TypeError):  # unreadable, or no time zone to compare with
            return False
        return timedelta(0) <= age <= ttl

    # Store a successful check (failures are never passed here); a database error skips it.
    async def put(self, query: str, check: NameCheck, classes_version: int) -> None:
        await asyncio.to_thread(self._put, query, check, classes_version)

    def _put(self, query: str, check: NameCheck, classes_version: int) -> None:
        try:
            connection = self._connect()
            try:
                with connection:
                    connection.execute(
                        "INSERT OR REPLACE INTO wikidata_safety_cache "
                        "(query, qid, label, reason, band, band_common, classes_version, "
                        "checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (query, check.qid, check.label, check.reason, int(check.band),
                         int(check.common), classes_version, self.now().isoformat()),
                    )  # fmt: skip
            finally:
                connection.close()
        except (sqlite3.Error, OSError) as error:
            logger.warning("Wikidata cache write skipped (%s).", error)


# --- Lookups ---------------------------------------------------------------------------------


# P31 and P279 item IDs from one wbgetentities entity.
def _read_classes(entity: dict[str, Any]) -> EntityClasses:
    claims = entity.get("claims") or {}

    def ids(prop: str) -> tuple[str, ...]:
        values = (
            c.get("mainsnak", {}).get("datavalue", {}).get("value") for c in claims.get(prop, [])
        )
        return tuple(v["id"] for v in values if isinstance(v, dict) and "id" in v)

    return EntityClasses(ids("P31"), ids("P279"))


class LiveWikidataLookup:
    """Wikidata's public API over httpx (no key). One try per call; errors raise Unavailable."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client

    # GET the API once and return its JSON, or raise WikidataUnavailable.
    async def _get(self, params: dict[str, str]) -> dict[str, Any]:
        params = {**params, "format": "json"}
        headers = {"User-Agent": USER_AGENT}
        try:
            if self.client is not None:
                response = await self.client.get(WIKIDATA_API, params=params, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                    response = await client.get(WIKIDATA_API, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise WikidataUnavailable(type(error).__name__) from error
        if not isinstance(data, dict) or "error" in data:
            raise WikidataUnavailable("Wikidata sent an error reply.")
        return data

    async def search(self, name: str) -> list[Candidate]:
        data = await self._get({
            "action": "wbsearchentities", "search": name, "language": "en", "type": "item",
            "limit": str(SEARCH_LIMIT),
        })  # fmt: skip
        return [
            Candidate(r["id"], r.get("label", ""), (r.get("match") or {}).get("text", ""))
            for r in data.get("search", [])
            if isinstance(r, dict) and "id" in r
        ]

    # Classes in batches of MAX_IDS_PER_CALL (wbgetentities' limit); items Wikidata reports as
    # missing, or sends without claims, are left out so the caller sees the gap.
    async def classes(self, qids: Sequence[str]) -> dict[str, EntityClasses]:
        found: dict[str, EntityClasses] = {}
        for start in range(0, len(qids), MAX_IDS_PER_CALL):
            batch = qids[start : start + MAX_IDS_PER_CALL]
            data = await self._get(
                {"action": "wbgetentities", "ids": "|".join(batch), "props": "claims"}
            )
            entities = data.get("entities") or {}
            found.update(
                (qid, _read_classes(e))
                for qid, e in entities.items()
                if isinstance(e, dict) and "missing" not in e and "claims" in e
            )
        return found


class MockWikidataLookup:
    """Recorded search results and classes from tests/fixtures/providers/wikidata/entities.json.

    A missing file, or a name with no entry and no "default", raises LookupError (never fails
    open), so a gap in the fixtures shows up as a test failure.
    """

    def __init__(self, path: Path = MOCK_FIXTURE) -> None:
        if not path.is_file():
            raise LookupError(f"No mock Wikidata fixture (expected {path}).")
        self.data = json.loads(path.read_text(encoding="utf-8"))

    async def search(self, name: str) -> list[Candidate]:
        searches = self.data["search"]
        results = searches.get(name.casefold(), searches.get("default"))
        if results is None:
            raise LookupError(f"Mock Wikidata fixture has no search entry for '{name}'.")
        return [Candidate(r["id"], r["label"], r.get("match", r["label"])) for r in results]

    async def classes(self, qids: Sequence[str]) -> dict[str, EntityClasses]:
        entities = self.data["entities"]
        return {
            qid: EntityClasses(
                tuple(entities[qid].get("P31", [])), tuple(entities[qid].get("P279", []))
            )
            for qid in qids
            if qid in entities
        }


# The lookup for the current PROVIDER_MODE.
def get_lookup() -> WikidataLookup:
    if get_settings().provider_mode == "mock":
        return MockWikidataLookup()
    return LiveWikidataLookup()


# --- The layer -------------------------------------------------------------------------------


# One name's check from the cache or Wikidata; None means no verdict (Wikidata failed).
async def _check_one(
    query: str, lookup: WikidataLookup, cache: WikidataCache, class_map: ClassMap
) -> NameCheck | None:
    cached = await cache.get(query, class_map.version)
    if cached is not None:
        return cached
    try:
        check = await asyncio.wait_for(resolve(query, lookup, class_map), TIMEOUT_S)
    except (WikidataUnavailable, TimeoutError) as error:
        detail = f"{type(error).__name__}: {error}" if str(error) else type(error).__name__
        logger.warning("Wikidata check skipped (%s); other safety layers still apply.", detail)
        return None
    await cache.put(query, check, class_map.version)
    return check


# Check fighter names (each side's entity and raw text) against Wikidata. Returns a block from
# the "wikidata" layer, or ALLOWED, which here means "no objection": no match, nothing blocked,
# or Wikidata unavailable. real_person only counts for names that read as proper names (see
# lookup_query): "a Napoleon" counts, "a napoleon" does not. A band also needs one of the typed
# names to name it (names_band): "the Eagles" and "Beatles" count; "Eagles" and "eagles" do not.
async def check_names(
    names: Sequence[str],
    *,
    lookup: WikidataLookup | None = None,
    cache: WikidataCache | None = None,
    class_map: ClassMap | None = None,
) -> SafetyVerdict:
    proper_by_query: dict[str, bool] = {}
    typed_by_query: dict[str, list[str]] = {}
    for name in names:
        query, proper = lookup_query(name)
        if query:
            proper_by_query[query] = proper_by_query.get(query, False) or proper
            typed_by_query.setdefault(query, []).append(name)
    if not proper_by_query:
        return ALLOWED
    lookup = lookup or get_lookup()
    cache = cache or WikidataCache()
    class_map = class_map or load_class_map()
    checks = await asyncio.gather(
        *(_check_one(q, lookup, cache, class_map) for q in proper_by_query)
    )
    for (query, proper), check in zip(proper_by_query.items(), checks, strict=True):
        if check is None or check.reason is None:
            continue
        if check.reason == "real_person" and not proper:
            continue
        typed = typed_by_query[query]
        if check.band and not any(names_band(t, check.label, check.common) for t in typed):
            continue
        return blocked(check.reason, "wikidata")
    return ALLOWED
