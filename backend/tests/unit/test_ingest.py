"""The ingest pipeline and Wikidata facts, with no network or live services."""

import json
import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.providers.mock.text import MockDocParser, MockEmbedder
from app.research.facts import Fact, store_facts, wikidata_facts
from app.research.ingest import ingest_all
from app.research.seed_fighters import SeedFighter

UNIT = "http://www.wikidata.org/entity/"
ENTITY = {
    "id": "Q726",
    "claims": {
        "P2067": [
            {
                "id": "Q726$a",
                "rank": "normal",
                "mainsnak": {"datavalue": {"value": {"amount": "+500", "unit": UNIT + "Q11570"}}},
            },
            {
                "id": "Q726$b",
                "rank": "deprecated",
                "mainsnak": {"datavalue": {"value": {"amount": "+1", "unit": UNIT + "Q11570"}}},
            },
            {
                "id": "Q726$c",
                "rank": "normal",
                "mainsnak": {"datavalue": {"value": {"amount": "+9", "unit": UNIT + "Q999"}}},
            },
        ],
        "P2052": [
            {
                "id": "Q726$d",
                "rank": "normal",
                "mainsnak": {"datavalue": {"value": {"amount": "+48", "unit": UNIT + "Q180154"}}},
            }
        ],
        "P2048": [{"id": "Q726$e", "rank": "normal", "mainsnak": {"snaktype": "somevalue"}}],
    },
}


def fighter(fighter_id: str, article: str) -> SeedFighter:
    return SeedFighter(fighter_id, article, "Adult", "mammal", "living", "land", article)


def make_handler(calls: list[str], missing: tuple[str, ...] = (), wikidata: str = "found"):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if "page/html" in request.url.path:
            if any(name in request.url.path for name in missing):
                return httpx.Response(404)
            html = "<p>" + "A horse weighs 500 kg. " * 80 + "</p>"
            return httpx.Response(200, headers={"ETag": '"77/abc"'}, content=html.encode())
        if wikidata == "no item":
            return httpx.Response(200, json={"entities": {"-1": {"missing": ""}}})
        if wikidata == "refused":
            return httpx.Response(403)  # not retried, so the test needs no waiting
        return httpx.Response(200, json={"entities": {"Q726": ENTITY}})

    return handler


class CountingParser(MockDocParser):
    def __init__(self) -> None:
        self.calls = 0

    async def parse(self, data: bytes, mime: str) -> str:
        self.calls += 1
        return await super().parse(data, mime)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "app.db")
    apply_migrations(connection)
    yield connection
    connection.close()


def rows(connection: sqlite3.Connection) -> tuple[int, int, int, int]:
    tables = ("documents", "chunks", "chunks_vec", "facts")
    return tuple(connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables)


def test_wikidata_facts_keep_usable_statements_only() -> None:
    facts = wikidata_facts(ENTITY)
    assert [(f.field, f.value, f.unit) for f in facts] == [
        ("P2067", 500.0, "kg"),
        ("P2052", 48.0, "km/h"),
    ]
    assert facts[0].source == "wikidata"
    assert facts[0].reference == "https://www.wikidata.org/wiki/Q726#Q726$a"


def test_a_fact_must_say_where_it_came_from(database: sqlite3.Connection) -> None:
    bad = Fact(source="wikidata", field="P2067", value=1.0, unit="kg", reference="")
    with pytest.raises(sqlite3.IntegrityError):
        store_facts(database, "horse", "wikidata", [bad], "CC0 1.0", "2026-11-10")


async def test_ingest_stores_passages_facts_and_raw_files(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    calls: list[str] = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(make_handler(calls))) as client:
        summary = await ingest_all(
            database,
            client,
            CountingParser(),
            MockEmbedder(),
            [fighter("horse", "Horse")],
            tmp_path,
        )
    assert (summary.fighters, summary.documents, summary.parsed) == (1, 1, 1)
    assert summary.chunks > 1 and summary.facts == 2 and summary.failures == []
    assert (tmp_path / "horse" / "wikipedia.html").exists()
    details = json.loads((tmp_path / "horse" / "wikidata.meta.json").read_text(encoding="utf-8"))
    assert details["license"] == "CC0 1.0"


async def test_every_fetched_article_goes_through_the_parser(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    parser = CountingParser()
    fighters = [fighter("horse", "Horse"), fighter("duck", "Mallard")]
    async with httpx.AsyncClient(transport=httpx.MockTransport(make_handler([]))) as client:
        summary = await ingest_all(database, client, parser, MockEmbedder(), fighters, tmp_path)
    assert parser.calls == summary.documents == summary.parsed == 2


async def test_a_second_run_changes_nothing_and_parses_nothing(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    fighters = [fighter("horse", "Horse")]
    parser = CountingParser()
    async with httpx.AsyncClient(transport=httpx.MockTransport(make_handler([]))) as client:
        await ingest_all(database, client, parser, MockEmbedder(), fighters, tmp_path)
        before = rows(database)
        await ingest_all(database, client, parser, MockEmbedder(), fighters, tmp_path)
    assert rows(database) == before
    assert parser.calls == 1


async def test_a_missing_article_is_logged_and_not_fatal(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    fighters = [fighter("ghost", "No_such_page"), fighter("horse", "Horse")]
    handler = make_handler([], missing=("No_such_page",))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        summary = await ingest_all(
            database, client, CountingParser(), MockEmbedder(), fighters, tmp_path
        )
    assert summary.parsed == 1 and len(summary.failures) == 1
    assert "ghost" in summary.failures[0]


async def test_no_wikidata_item_keeps_the_article_and_is_logged(
    database: sqlite3.Connection, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    handler = make_handler([], wikidata="no item")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with caplog.at_level(logging.INFO, logger="app.research.ingest"):
            summary = await ingest_all(
                database,
                client,
                CountingParser(),
                MockEmbedder(),
                [fighter("horse", "Horse")],
                tmp_path,
            )
    assert (summary.parsed, summary.facts, summary.failures) == (1, 0, [])
    assert "No Wikidata item for horse" in caplog.text


async def test_a_wikidata_error_is_recorded_and_not_fatal(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    fighters = [fighter("horse", "Horse"), fighter("duck", "Mallard")]
    handler = make_handler([], wikidata="refused")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        summary = await ingest_all(
            database, client, CountingParser(), MockEmbedder(), fighters, tmp_path
        )
    assert summary.parsed == 2 and summary.facts == 0  # both articles still stored
    assert sorted(failure.split(":")[0] for failure in summary.failures) == ["duck", "horse"]
