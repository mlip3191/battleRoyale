"""G03 (#34): a fighter off the seed list gets its needed article sections on demand, in time."""

import asyncio
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.stats import StatName
from app.providers.live.http import ProviderError
from app.providers.mock.text import MockEmbedder, MockReranker
from app.research import ingest
from app.research.ingest import ingest_on_demand, needed_sections
from app.research.retrieve import evidence_on_demand

LEAD = "<p>The moose is the largest member of the deer family.</p>"
DESCRIPTION = "<p>Adult bulls weigh 380 to 700 kg.</p>"
ANTLERS = "<p>Antlers can span 1.8 m.</p>"
HISTORY = "<p>The name comes from an Algonquian word.</p>"
ARTICLE = (
    "<html><head><title>Moose</title></head><body>"
    f'<section data-mw-section-id="0" id="a">{LEAD}</section>'
    '<section data-mw-section-id="1" id="b"><h2 id="Etymology">Etymology</h2>'
    f"{HISTORY}</section>"
    '<section data-mw-section-id="2" id="c"><h2 id="Description">Description</h2>'
    f'{DESCRIPTION}<section data-mw-section-id="3" id="d"><h3 id="Antlers">Antlers</h3>'
    f"{ANTLERS}</section></section></body></html>"
)


class RecordingParser:
    """Returns each piece's text as-is, waits a moment, and records how many ran at once."""

    def __init__(self, pause: float = 0.05, fail: bool = False) -> None:
        self.pause, self.fail = pause, fail
        self.pieces: list[str] = []
        self.in_flight = self.most = 0

    async def parse(self, data: bytes, mime: str) -> str:
        self.in_flight += 1
        self.most = max(self.most, self.in_flight)
        await asyncio.sleep(self.pause)
        self.in_flight -= 1
        if self.fail:
            raise ProviderError("Live 'doc_parser' call failed: HTTP 503.")
        piece = data.decode("utf-8")
        self.pieces.append(piece)
        return piece


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "app.db")
    apply_migrations(connection)
    yield connection
    connection.close()


def client(status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"ETag": '"42/abc"'}, content=ARTICLE.encode())

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def run(db: sqlite3.Connection, parser: RecordingParser, status: int = 200) -> bool:
    async with client(status) as http:
        return await ingest_on_demand(db, http, parser, MockEmbedder(), "moose", "Moose")


async def test_an_article_already_fetched_is_not_downloaded_again(db) -> None:  # #535
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, headers={"ETag": '"42/abc"'}, content=ARTICLE.encode())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        article = await ingest.fetch_article(http, "Moose")
        parser = RecordingParser(pause=0)
        stored = await ingest_on_demand(
            db, http, parser, MockEmbedder(), "moose", "Moose", article=article
        )
    assert stored and len(requests) == 1  # only the fetch above
    assert any(DESCRIPTION in piece for piece in parser.pieces)


def test_only_the_lead_and_size_sections_are_kept() -> None:
    lead, description = needed_sections(ARTICLE)
    assert LEAD in lead and HISTORY not in lead
    assert DESCRIPTION in description and ANTLERS in description  # subsections come along
    assert all(HISTORY not in piece for piece in needed_sections(ARTICLE))
    assert needed_sections("<p>No sections here.</p>") == ["<p>No sections here.</p>"]


async def test_needed_sections_are_parsed_in_parallel_and_stored(db: sqlite3.Connection) -> None:
    parser = RecordingParser()
    assert await run(db, parser)
    assert len(parser.pieces) == 2 and parser.most == 2  # both pieces were parsing at once
    row = db.execute("SELECT title, raw_text FROM documents WHERE fighter_id = 'moose'").fetchone()
    assert row[0] == "Moose" and "380 to 700 kg" in row[1] and "Algonquian" not in row[1]


async def test_a_slow_ingest_gives_up_and_stores_nothing(
    db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ingest, "ON_DEMAND_BUDGET_S", 0.05)
    assert not await run(db, RecordingParser(pause=5.0))
    assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


async def test_a_parser_failure_or_missing_article_returns_false(db: sqlite3.Connection) -> None:
    assert not await run(db, RecordingParser(fail=True))
    assert not await run(db, RecordingParser(), status=404)
    assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


async def test_evidence_on_demand_ingests_once_then_searches(db: sqlite3.Connection) -> None:
    parser = RecordingParser()
    providers = (parser, MockEmbedder(), MockReranker())
    async with client() as http:
        first = await evidence_on_demand(db, http, providers, "moose", "Moose", StatName.MASS)
        again = await evidence_on_demand(db, http, providers, "moose", "Moose", StatName.MASS)
    assert first and all(p.doc_title == "Moose" and p.url for p in first)
    assert len(parser.pieces) == 2  # the second call reused the stored article
    assert [p.chunk_id for p in again] == [p.chunk_id for p in first]


async def test_a_failed_ingest_gives_no_evidence_rather_than_an_error(
    db: sqlite3.Connection,
) -> None:
    providers = (RecordingParser(fail=True), MockEmbedder(), MockReranker())
    async with client() as http:
        found = await evidence_on_demand(db, http, providers, "moose", "Moose", StatName.MASS)
    assert found == []


async def test_a_long_section_is_cut_into_pieces_that_are_parsed_at_once(
    db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    long_lead = "<p>" + "The moose browses on willow and birch all winter long. " * 400 + "</p>"
    article = ARTICLE.replace(LEAD, long_lead)  # about 22,000 characters of lead text

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"ETag": '"42/abc"'}, content=article.encode())

    parser = RecordingParser()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert await ingest_on_demand(db, http, parser, MockEmbedder(), "moose", "Moose")
    assert len(parser.pieces) >= 4 and parser.most == len(parser.pieces)


class OneFailsParser:
    """The first piece fails at once; the rest wait, and record whether they were cancelled."""

    def __init__(self) -> None:
        self.calls = 0
        self.cancelled = 0

    async def parse(self, data: bytes, mime: str) -> str:
        self.calls += 1
        if self.calls == 1:
            raise ProviderError("Live 'doc_parser' call failed: HTTP 503.")
        try:
            await asyncio.sleep(5.0)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        return data.decode("utf-8")


class BlankParser:
    """Replies with nothing at all, as a broken parser might."""

    async def parse(self, data: bytes, mime: str) -> str:
        return "  \n"


async def test_one_failed_piece_cancels_the_others(db: sqlite3.Connection) -> None:
    parser = OneFailsParser()
    async with client() as http:
        assert not await ingest_on_demand(db, http, parser, MockEmbedder(), "moose", "Moose")
    assert parser.calls == 2 and parser.cancelled == 1  # the other piece stopped, not left running
    assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


async def test_blank_parser_replies_store_nothing_so_a_later_lookup_retries(
    db: sqlite3.Connection,
) -> None:
    async with client() as http:
        assert not await ingest_on_demand(db, http, BlankParser(), MockEmbedder(), "moose", "Moose")
    assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
