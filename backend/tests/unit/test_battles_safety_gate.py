"""POST /api/battles runs the safety gate before research (#311): a blocked matchup gets intake's
blocked reply, starts no battle, and reaches no research, image or audio provider. Stand-in
classifier and Wikidata only; no network."""

import json
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.battles import get_safety_chat, get_store, get_wikidata_lookup
from app.config import Settings, use_settings
from app.main import create_app
from app.media import audio as media_audio
from app.media import images as media_images
from app.models.battle import BattleRecord
from app.models.matchup import IntakeResult, Matchup
from app.narration import writer
from app.pipeline import challenger, stages
from app.pipeline.store import BattleStore
from app.providers import registry
from app.providers.base import ChatMessage
from app.providers.live.http import ProviderError
from app.safety import blocked_result
from app.safety.verdict import BLOCKED_REASONS, MESSAGES, blocked
from app.safety.wikidata import Candidate, EntityClasses, MockWikidataLookup
from tests.conftest import mock_settings

WAIT_SECONDS = 30.0
# A made-up fighter word per reason: the classifier stand-in blocks a text naming it.
BLOCK_WORDS = {reason: f"zorp{index:02d}" for index, reason in enumerate(BLOCKED_REASONS)}
# Modules that ask the registry for a provider once a battle runs.
DOWNSTREAM_MODULES = (stages, media_images, media_audio, writer, challenger)


class StandInClassifier:
    """Classifier stand-in: blocks a text naming one of `blocked`'s words, else allows."""

    def __init__(self, blocked_words: dict[str, str] | None = None) -> None:
        self.blocked_words = blocked_words or {}
        self.calls = 0

    async def complete(self, messages: list[ChatMessage], **_: Any) -> str:
        self.calls += 1
        text = messages[1]["content"].lower()
        hits = [reason for word, reason in self.blocked_words.items() if word in text]
        return json.dumps({"verdict": hits[0] if hits else "allowed"})


class DownChat:
    """Chat endpoint that is down, so the classifier fails closed."""

    async def complete(self, messages: list[ChatMessage], **_: Any) -> str:
        raise ProviderError("chat endpoint unavailable")


class CountingLookup(MockWikidataLookup):
    """The mock Wikidata fixture, counting every call."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def search(self, name: str) -> list[Candidate]:
        self.calls += 1
        return await super().search(name)

    async def classes(self, qids: Sequence[str]) -> dict[str, EntityClasses]:
        self.calls += 1
        return await super().classes(qids)


class CountingStore(BattleStore):
    """A fresh in-memory store that counts the battles it creates."""

    def __init__(self) -> None:
        super().__init__()
        self.created = 0

    async def create(self, matchup: Matchup) -> BattleRecord:
        self.created += 1
        return await super().create(matchup)


class Downstream:
    """Counts every provider asked for after the gate, and every research stage run."""

    def __init__(self) -> None:
        self.providers: list[str] = []
        self.research_runs = 0


@pytest.fixture(autouse=True)
def _quick_simulation() -> None:
    use_settings(mock_settings(sim_runs=20))


@pytest.fixture
def downstream(monkeypatch: pytest.MonkeyPatch) -> Downstream:
    counts = Downstream()

    # Count, then hand back the usual mock, so an allowed battle still runs.
    def counting_provider(name: Any, settings: Any = None) -> Any:
        counts.providers.append(name)
        return registry.get_provider(name, settings)

    for module in DOWNSTREAM_MODULES:
        monkeypatch.setattr(module, "get_provider", counting_provider)
    real_research = stages.research

    async def counting_research(matchup: Matchup) -> stages.Research:
        counts.research_runs += 1
        return await real_research(matchup)

    monkeypatch.setattr(stages, "research", counting_research)
    return counts


@pytest.fixture
def chat() -> StandInClassifier:
    return StandInClassifier({word: reason for reason, word in BLOCK_WORDS.items()})


@pytest.fixture
def lookup() -> CountingLookup:
    return CountingLookup()


@pytest.fixture
def store() -> CountingStore:
    return CountingStore()


# The app with the stand-in classifier, Wikidata and store.
@pytest.fixture
def client(
    settings: Settings,
    store: CountingStore,
    chat: StandInClassifier,
    lookup: CountingLookup,
    tmp_path: Path,
) -> Iterator[TestClient]:
    app = create_app(settings, frontend_dist=tmp_path / "missing")
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_safety_chat] = lambda: chat
    app.dependency_overrides[get_wikidata_lookup] = lambda: lookup
    with TestClient(app) as test_client:
        yield test_client


def body(first: str, second: str = "a goose") -> dict[str, Any]:
    fighters = [{"raw": first, "entity": first.removeprefix("a ")}]
    fighters.append({"raw": second, "entity": second.removeprefix("a ")})
    return {"fighters": fighters, "raw_text": f"{first} vs {second}"}


# The reply intake gives for the same block (the shared blocked_result helper).
def intake_reply(reason: Any) -> dict[str, Any]:
    return blocked_result(blocked(reason, "classifier")).model_dump(mode="json")


def assert_blocked(response: Any, reason: str) -> None:
    assert response.status_code == 403, response.text
    reply = IntakeResult.model_validate(response.json())
    assert (reply.status, reply.blocked_reason, reply.message) == (
        "blocked",
        reason,
        MESSAGES[reason],
    )
    assert response.json() == intake_reply(reason)


# Poll GET until the battle stops running.
def wait_until_finished(client: TestClient, battle_id: str) -> BattleRecord:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        record = BattleRecord.model_validate(client.get(f"/api/battles/{battle_id}").json())
        if record.status != "running":
            return record
        time.sleep(0.02)
    raise AssertionError(f"battle {battle_id} never finished")


@pytest.mark.parametrize("reason", BLOCKED_REASONS)
def test_each_blocked_reason_gets_intakes_reply_and_starts_no_battle(
    client: TestClient, store: CountingStore, reason: str
) -> None:
    response = client.post("/api/battles", json=body(f"a {BLOCK_WORDS[reason]}"))
    assert_blocked(response, reason)
    assert store.created == 0


@pytest.mark.parametrize(
    ("fighter", "reason"),
    [("a toddler", "minor"), ("Zeus", "deity")],  # code rules; the Wikidata name check
)
def test_rules_and_wikidata_blocks_also_stop_the_battle(
    client: TestClient, store: CountingStore, fighter: str, reason: str
) -> None:
    assert_blocked(client.post("/api/battles", json=body(fighter)), reason)
    assert store.created == 0


def test_a_blocked_matchup_reaches_no_research_image_or_audio_provider(
    client: TestClient,
    store: CountingStore,
    chat: StandInClassifier,
    downstream: Downstream,
) -> None:
    response = client.post("/api/battles", json=body(f"a {BLOCK_WORDS['real_person']}"))
    assert_blocked(response, "real_person")
    assert chat.calls > 0  # the gate itself did run
    assert (store.created, downstream.research_runs, downstream.providers) == (0, 0, [])


def test_a_code_rules_block_makes_no_provider_call_at_all(
    client: TestClient,
    chat: StandInClassifier,
    lookup: CountingLookup,
    downstream: Downstream,
) -> None:
    assert_blocked(client.post("/api/battles", json=body("a toddler")), "minor")
    assert (chat.calls, lookup.calls, downstream.research_runs, downstream.providers) == (
        0,
        0,
        0,
        [],
    )


def test_an_allowed_matchup_still_starts_a_battle(
    client: TestClient, store: CountingStore, downstream: Downstream
) -> None:
    response = client.post("/api/battles", json=body("a grizzly bear", "a gray wolf"))
    assert response.status_code == 202, response.text
    record = wait_until_finished(client, response.json()["battle_id"])
    assert record.status == "done"
    assert store.created == 1 and downstream.research_runs == 1  # the counters are wired in


def test_a_classifier_outage_fails_closed_with_no_battle(
    client: TestClient, store: CountingStore, downstream: Downstream
) -> None:
    client.app.dependency_overrides[get_safety_chat] = DownChat  # type: ignore[attr-defined]
    response = client.post("/api/battles", json=body("a grizzly bear", "a gray wolf"))
    assert response.status_code == 503
    assert (store.created, downstream.research_runs, downstream.providers) == (0, 0, [])
