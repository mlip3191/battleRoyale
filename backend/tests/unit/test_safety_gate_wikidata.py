"""The Wikidata name check inside the safety gate (A04 part 2b, #27): acceptance examples through
check_matchup and check_parsed_sides, how its verdict combines with the other layers, and
outages. Mock Wikidata and a temp cache only; no network."""

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from app.models.matchup import FighterRequest, Matchup
from app.providers.base import ChatMessage
from app.providers.live.http import ProviderError
from app.safety import SafetyUnavailable, check_matchup, check_parsed_sides
from app.safety.gate import wikidata_names
from app.safety.wikidata import Candidate, EntityClasses, MockWikidataLookup, WikidataCache

OTHER_SIDE = ("a goose", "goose", None)


class StandInClassifier:
    """Classifier stand-in: blocks a text naming one of `blocked`'s words, else allows."""

    def __init__(self, blocked: dict[str, str] | None = None) -> None:
        self.blocked = blocked or {}
        self.calls = 0

    async def complete(self, messages: list[ChatMessage], **_: Any) -> str:
        self.calls += 1
        text = messages[1]["content"].lower()
        hits = [reason for word, reason in self.blocked.items() if word in text]
        return json.dumps({"verdict": hits[0] if hits else "allowed"})


class DownChat:
    """Chat endpoint that is down; fails only once `wait_for` is set (if given)."""

    def __init__(self, wait_for: asyncio.Event | None = None) -> None:
        self.wait_for = wait_for

    async def complete(self, messages: list[ChatMessage], **_: Any) -> str:
        if self.wait_for is not None:
            await self.wait_for.wait()
        raise ProviderError("chat endpoint unavailable")


class CountingLookup(MockWikidataLookup):
    """The mock fixture, counting every Wikidata call."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def search(self, name: str) -> list[Candidate]:
        self.calls += 1
        return await super().search(name)

    async def classes(self, qids: Sequence[str]) -> dict[str, EntityClasses]:
        self.calls += 1
        return await super().classes(qids)


class SlowLookup:
    """Wikidata that never answers in time; records whether it was asked or cancelled."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def search(self, name: str) -> list[Candidate]:
        self.started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return []

    async def classes(self, qids: Sequence[str]) -> dict[str, EntityClasses]:
        return {}


@pytest.fixture
def cache(tmp_path: Path) -> WikidataCache:
    return WikidataCache(tmp_path / "wikidata.db")


# A Matchup from (raw, entity, variant) sides.
def matchup(*sides: tuple[str, str, str | None]) -> Matchup:
    fighters = [FighterRequest(raw=r, entity=e, variant=v) for r, e, v in sides]
    return Matchup(fighters=fighters, raw_text=" vs ".join(r for r, _, _ in sides))


# Run one side against a goose through either gate entry point, with mock Wikidata.
async def gate(
    entry: str,
    side: tuple[str, str, str | None],
    cache: WikidataCache,
    *,
    chat: Any = None,
    lookup: Any = None,
) -> Any:
    m = matchup(side, OTHER_SIDE)
    chat = chat or StandInClassifier()
    lookup = lookup or MockWikidataLookup()
    if entry == "check_matchup":
        return await check_matchup(m, chat=chat, wikidata_lookup=lookup, wikidata_cache=cache)
    return await check_parsed_sides(
        m.fighters, m.raw_text, chat=chat, wikidata_lookup=lookup, wikidata_cache=cache
    )


ENTRIES = ["check_matchup", "check_parsed_sides"]

# #27 acceptance examples: (raw, entity) -> reason, or None for allowed. The classifier
# stand-in allows everything, so every block here comes from the Wikidata layer.
EXAMPLES = [
    (("Napoleon", "napoleon"), "real_person"),
    (("a Napoleon", "napoleon"), "real_person"),
    (("a napoleon", "napoleon"), None),
    (("the emperor", "emperor"), None),
    (("Robo-Tron", "robo-tron"), "copyrighted_character"),
    (("Zeus", "zeus"), "deity"),
    (("an assault rifle", "assault rifle"), "weapon"),
    (("the Moon", "moon"), "out_of_scope"),
    (("a Canadian goose", "canada goose"), None),
    (("a German Shepherd", "german shepherd"), None),
    (("a Bengal tiger", "bengal tiger"), None),
    (("a Roman legionary", "roman legionary"), None),
    (("a dragon", "dragon"), None),
    (("a toaster", "toaster"), None),
    (("a bulldozer", "bulldozer"), None),
]


@pytest.mark.parametrize("entry", ENTRIES)
@pytest.mark.parametrize(("side", "reason"), EXAMPLES, ids=[s[0] for s, _ in EXAMPLES])
async def test_acceptance_examples_through_the_gate(
    entry: str, side: tuple[str, str], reason: str | None, cache: WikidataCache
) -> None:
    verdict = await gate(entry, (*side, None), cache)
    assert verdict.reason == reason
    assert verdict.layer == ("wikidata" if reason else None)


@pytest.mark.parametrize(
    "side",
    [
        ("the short emperor", "napoleon", None),  # only the model's entity names him
        ("Napoleon", "french general", None),  # only the user's words name him
    ],
)
async def test_a_real_person_as_raw_or_entity_is_refused(
    side: tuple[str, str, None], cache: WikidataCache
) -> None:
    verdict = await gate("check_parsed_sides", side, cache)
    assert (verdict.reason, verdict.layer) == ("real_person", "wikidata")


def test_names_are_raw_plus_a_different_entity_never_the_variant() -> None:
    fighters = [
        FighterRequest(raw="a napoleon", entity="napoleon"),
        FighterRequest(raw="the short emperor", entity="napoleon"),
        FighterRequest(raw="a dog named Napoleon", entity="dog", variant="named Napoleon"),
    ]
    assert wikidata_names(fighters) == [
        "a napoleon",
        "the short emperor",
        "napoleon",
        "a dog named Napoleon",
        "dog",
    ]


async def test_a_classifier_block_is_never_overridden_by_wikidata(cache: WikidataCache) -> None:
    chat = StandInClassifier({"napoleon": "deity"})  # disagrees with Wikidata on purpose
    verdict = await gate("check_matchup", ("Napoleon", "napoleon", None), cache, chat=chat)
    assert (verdict.reason, verdict.layer) == ("deity", "classifier")


async def test_a_rules_block_needs_no_wikidata_call(cache: WikidataCache) -> None:
    lookup = CountingLookup()
    for entry in ENTRIES:
        verdict = await gate(entry, ("a toddler", "toddler", None), cache, lookup=lookup)
        assert (verdict.reason, verdict.layer) == ("minor", "rules")
    assert lookup.calls == 0


@pytest.mark.parametrize("entry", ENTRIES)
@pytest.mark.parametrize(
    ("blocked", "reason", "layer"),
    [({"napoleon": "real_person"}, "real_person", "classifier"), ({}, None, None)],
)
async def test_a_wikidata_timeout_leaves_the_rules_and_classifier_verdict(
    entry: str,
    blocked: dict[str, str],
    reason: str | None,
    layer: str | None,
    cache: WikidataCache,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.safety.wikidata.TIMEOUT_S", 0.05)
    lookup = SlowLookup()
    chat = StandInClassifier(blocked)
    # "the short emperor" -> "napoleon": the entity adds new words, so both entry points
    # call the classifier.
    side = ("the short emperor", "napoleon", None)
    verdict = await asyncio.wait_for(gate(entry, side, cache, chat=chat, lookup=lookup), 2)
    assert (verdict.reason, verdict.layer) == (reason, layer)
    assert lookup.started.is_set() and chat.calls > 0


@pytest.mark.parametrize("entry", ENTRIES)
async def test_a_classifier_outage_still_fails_closed_and_stops_the_lookup(
    entry: str, cache: WikidataCache
) -> None:
    lookup = SlowLookup()
    side = ("the short emperor", "napoleon", None)
    chat = DownChat(wait_for=lookup.started)  # fail while the lookup is in flight
    with pytest.raises(SafetyUnavailable):
        await asyncio.wait_for(gate(entry, side, cache, chat=chat, lookup=lookup), 2)
    assert lookup.cancelled.is_set()


async def test_a_repeat_check_through_the_gate_makes_no_wikidata_request(
    cache: WikidataCache,
) -> None:
    lookup = CountingLookup()
    first = await gate("check_matchup", ("Zeus", "zeus", None), cache, lookup=lookup)
    calls = lookup.calls
    second = await gate("check_matchup", ("Zeus", "zeus", None), cache, lookup=lookup)
    assert first == second and first.reason == "deity"
    assert calls > 0 and lookup.calls == calls
