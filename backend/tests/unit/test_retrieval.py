"""Retrieval, reranking, and evidence_for on mock providers, plus the live reranker adapter."""

import json
import logging
import sqlite3
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest
import yaml

from app.config import Settings
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.stats import ASSUMABLE_STATS, StatName
from app.providers.live.http import ProviderError
from app.providers.live.rerank import LiveReranker
from app.providers.mock.text import MockEmbedder, MockReranker
from app.providers.registry import get_provider, service_config
from app.research.kb_store import DocumentRecord, ensure_vector_table, store_document
from app.research.retrieve import (
    STAT_QUERIES,
    TOP_N,
    Passage,
    evidence_for,
    rerank,
    retrieve,
)
from app.research.seed_fighters import load_seed_fighters

CASES = Path(__file__).parents[1] / "fixtures" / "retrieval_cases.yaml"
BEAR_TEXT = (
    "## Size\nCoastal males weigh 389 kilograms. "
    + "Grizzlies roam widely across the north. " * 30
    + "\n## Speed\nThe maximum speed reliably recorded is 48 km/h."
)
Handler = Callable[[httpx.Request], httpx.Response]


def record(fighter_id: str, title: str, text: str) -> DocumentRecord:
    return DocumentRecord(
        doc_id=f"{fighter_id}/wikipedia",
        fighter_id=fighter_id,
        source="wikipedia",
        title=title,
        url=f"https://example.test/{title}",
        license="CC BY-SA 4.0",
        retrieved_at="2026-11-10T00:00:00+00:00",
        text=text,
    )


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[sqlite3.Connection]:
    connection = connect(tmp_path / "app.db")
    apply_migrations(connection)
    embedder = MockEmbedder()
    await ensure_vector_table(connection, embedder)
    await store_document(connection, record("grizzly-bear", "Grizzly bear", BEAR_TEXT), embedder)
    await store_document(connection, record("gray-wolf", "Wolf", "Wolves weigh 40 kg."), embedder)
    yield connection
    connection.close()


class FailingReranker:
    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        raise ProviderError("Live 'reranker' call to /v1/rerank failed: HTTP 503.")


class ShortReranker:
    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        return [1.0]


class GarbledReranker:
    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


async def test_retrieve_returns_only_that_fighters_passages(database: sqlite3.Connection) -> None:
    passages = await retrieve(database, MockEmbedder(), "gray-wolf", "weight")
    assert [p.text for p in passages] == ["Wolves weigh 40 kg."]
    assert passages[0].doc_title == "Wolf" and passages[0].url.endswith("/Wolf")


async def test_retrieve_puts_the_closest_passage_first(database: sqlite3.Connection) -> None:
    target = database.execute("SELECT text FROM chunks WHERE heading = 'Speed'").fetchone()[0]
    passages = await retrieve(database, MockEmbedder(), "grizzly-bear", target)
    assert passages[0].text == target and passages[0].distance == pytest.approx(0, abs=1e-6)
    assert [p.distance for p in passages] == sorted(p.distance for p in passages)


async def test_retrieve_respects_k_and_unknown_fighters(database: sqlite3.Connection) -> None:
    assert len(await retrieve(database, MockEmbedder(), "grizzly-bear", "bear", k=1)) == 1
    assert await retrieve(database, MockEmbedder(), "toaster", "bear") == []


async def test_rerank_reorders_by_relevance(database: sqlite3.Connection) -> None:
    passages = await retrieve(database, MockEmbedder(), "grizzly-bear", "anything")
    ranked = await rerank(MockReranker(), "maximum speed reliably recorded", passages)
    assert ranked[0].heading == "Speed"
    assert len(ranked) <= TOP_N


async def test_a_failing_reranker_keeps_vector_order_and_logs(
    database: sqlite3.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    passages = await retrieve(database, MockEmbedder(), "grizzly-bear", "anything")
    for reranker in (FailingReranker(), ShortReranker(), GarbledReranker()):
        with caplog.at_level(logging.WARNING, logger="app.research.retrieve"):
            assert await rerank(reranker, "speed", passages) == passages[:TOP_N]
    assert caplog.text.count("kept vector order") == 3


async def test_rerank_of_nothing_is_nothing() -> None:
    assert await rerank(FailingReranker(), "speed", []) == []


async def test_evidence_for_returns_at_most_five_cited_passages(
    database: sqlite3.Connection,
) -> None:
    passages = await evidence_for(
        database, MockEmbedder(), MockReranker(), "grizzly-bear", StatName.MASS
    )
    assert 0 < len(passages) <= TOP_N
    assert all(isinstance(p, Passage) and p.doc_title and p.url and p.text for p in passages)


async def test_evidence_for_refuses_behavioral_stats(database: sqlite3.Connection) -> None:
    for stat in ASSUMABLE_STATS:
        with pytest.raises(ValueError):
            await evidence_for(database, MockEmbedder(), MockReranker(), "grizzly-bear", stat)


def test_every_physical_stat_has_a_query() -> None:
    assert set(STAT_QUERIES) == {name for name in StatName if name not in ASSUMABLE_STATS}


def test_the_quality_cases_are_well_formed() -> None:
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    seed = {fighter.id for fighter in load_seed_fighters()}
    assert len(cases) == 15
    for case in cases:
        assert case["fighter_id"] in seed, case
        assert StatName(case["stat"]) in STAT_QUERIES, case
        assert case["phrase"].strip(), case
    assert len({(c["fighter_id"], c["stat"]) for c in cases}) == 15


def live_reranker(handler: Handler) -> LiveReranker:
    settings = Settings(
        _env_file=None,
        provider_mode="live",
        course_api_key="decoy-key",
        rerank_url="http://course.test:9004",
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LiveReranker(service_config("reranker", settings), settings, client=client)


def test_live_mode_builds_the_reranker() -> None:
    settings = Settings(
        _env_file=None, provider_mode="live", course_api_key="k", rerank_url="http://course.test"
    )
    assert isinstance(get_provider("reranker", settings), LiveReranker)


async def test_live_reranker_returns_scores_in_input_order() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "decoy/rerank"}]})
        body = json.loads(request.content)
        assert body["model"] == "decoy/rerank" and body["documents"] == ["a", "b"]
        results = [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]
        return httpx.Response(200, json={"results": results})

    reranker = live_reranker(handler)
    assert await reranker.rerank("q", ["a", "b"]) == [0.1, 0.9]
    await reranker.rerank("q", ["a", "b"])
    assert calls.count("/v1/models") == 1


async def test_live_reranker_rejects_a_duplicated_index() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "decoy/rerank"}]})
        rows = [
            {"index": 0, "relevance_score": 0.5},
            {"index": 1, "relevance_score": 0.4},
            {"index": 1, "relevance_score": 0.9},
        ]
        return httpx.Response(200, json={"results": rows})

    with pytest.raises(ProviderError, match="every passage"):
        await live_reranker(handler).rerank("q", ["a", "b"])


async def test_live_reranker_rejects_a_reply_missing_a_passage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "decoy/rerank"}]})
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.5}]})

    with pytest.raises(ProviderError, match="every passage"):
        await live_reranker(handler).rerank("q", ["a", "b"])


async def test_live_reranker_makes_no_call_for_no_passages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    assert await live_reranker(handler).rerank("q", []) == []
