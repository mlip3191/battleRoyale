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
from app.research.traits import animaltraits_facts, pantheria_facts, taxon_name

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


PANTHERIA_TEXT = (
    "MSW05_Binomial\t5-1_AdultBodyMass_g\t13-1_AdultHeadBodyLen_mm\n"
    "Equus caballus\t403598.53\t-999.00\n"
    "Mus musculus\t19.30\t\n"
)
TRAITS_TEXT = (
    '"species","sex","inTextReference","body mass","body mass - units"\n'
    '"Equus caballus","female","Smith, 1990",450,"kg"\n'
    '"Equus caballus","","Jones, 2001",480,"kg"\n'
    '"Equus caballus","","Brown, 2005",,"kg"\n'
)
HORSE = {
    **ENTITY,
    "claims": {
        **ENTITY["claims"],
        "P225": [{"mainsnak": {"datavalue": {"value": "Equus caballus"}}}],
    },
}


def make_handler(
    calls: list[str],
    missing: tuple[str, ...] = (),
    wikidata: str = "found",
    entity: dict = ENTITY,
    datasets: str = "ok",
):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.host in ("esapubs.org", "zenodo.org"):
            if datasets == "refused":
                return httpx.Response(403)
            if datasets == "new format":
                return httpx.Response(200, content=b"name,weight\nEquus caballus,400\n")
            text = PANTHERIA_TEXT if request.url.host == "esapubs.org" else TRAITS_TEXT
            return httpx.Response(200, content=text.encode())
        if "page/html" in request.url.path:
            if any(name in request.url.path for name in missing):
                return httpx.Response(404)
            html = "<p>" + "A horse weighs 500 kg. " * 80 + "</p>"
            return httpx.Response(200, headers={"ETag": '"77/abc"'}, content=html.encode())
        if wikidata == "no item":
            return httpx.Response(200, json={"entities": {"-1": {"missing": ""}}})
        if wikidata == "refused":
            return httpx.Response(403)  # not retried, so the test needs no waiting
        return httpx.Response(200, json={"entities": {"Q726": entity}})

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


def test_pantheria_skips_missing_values() -> None:
    table = pantheria_facts(PANTHERIA_TEXT)
    assert [(f.field, f.value, f.unit) for f in table["Equus caballus"]] == [
        ("5-1_AdultBodyMass_g", 403598.53, "g")
    ]
    assert table["Equus caballus"][0].reference.endswith("#Equus_caballus")
    assert "Mus musculus" in table and len(table["Mus musculus"]) == 1


def test_animaltraits_facts_point_at_their_row_and_study() -> None:
    facts = animaltraits_facts(TRAITS_TEXT)["Equus caballus"]
    assert [(f.value, f.unit) for f in facts] == [(450.0, "kg"), (480.0, "kg")]
    assert facts[0].reference.endswith("#row-2 (Smith, 1990; female)")
    assert facts[1].reference.endswith("#row-3 (Jones, 2001)")


def test_taxon_name_comes_from_wikidata() -> None:
    assert taxon_name(HORSE) == "Equus caballus"
    assert taxon_name(ENTITY) is None


def test_taxon_name_skips_deprecated_and_prefers_preferred() -> None:
    def claim(name: str, rank: str) -> dict[str, object]:
        return {"rank": rank, "mainsnak": {"datavalue": {"value": name}}}

    wrong_first = {"claims": {"P225": [claim("Equus wrongus", "deprecated")]}}
    assert taxon_name(wrong_first) is None
    ranked = {
        "claims": {
            "P225": [
                claim("Equus wrongus", "deprecated"),
                claim("Equus ferus caballus", "normal"),
                claim("Equus caballus", "preferred"),
            ]
        }
    }
    assert taxon_name(ranked) == "Equus caballus"


async def test_trait_facts_are_stored_by_scientific_name(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    handler = make_handler([], entity=HORSE)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        summary = await ingest_all(
            database,
            client,
            CountingParser(),
            MockEmbedder(),
            [fighter("horse", "Horse")],
            tmp_path,
        )
    sources = database.execute("SELECT source, COUNT(*) FROM facts GROUP BY source").fetchall()
    assert dict(sources) == {"animaltraits": 2, "pantheria": 1, "wikidata": 2}
    assert summary.unmatched == [] and summary.failures == []
    assert (tmp_path / "traits" / "pantheria.txt").exists()


async def test_a_fighter_with_no_trait_row_is_reported(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(make_handler([]))) as client:
        summary = await ingest_all(
            database,
            client,
            CountingParser(),
            MockEmbedder(),
            [fighter("horse", "Horse")],
            tmp_path,
        )
    assert summary.unmatched == ["horse (no scientific name)"]


async def test_a_dataset_with_no_usable_rows_is_flagged(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    handler = make_handler([], entity=HORSE, datasets="new format")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        summary = await ingest_all(
            database,
            client,
            CountingParser(),
            MockEmbedder(),
            [fighter("horse", "Horse")],
            tmp_path,
        )
    assert sorted(f.split(":")[0] for f in summary.failures) == ["animaltraits", "pantheria"]
    assert summary.facts == 2  # only Wikidata, and no saved file is left half-written
    assert not list((tmp_path / "traits").glob("*.part"))
    # The unusable copies are deleted, so the next run downloads them again.
    assert not list((tmp_path / "traits").glob("*"))


async def test_a_dataset_that_fails_to_download_is_not_fatal(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    handler = make_handler([], entity=HORSE, datasets="refused")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        summary = await ingest_all(
            database,
            client,
            CountingParser(),
            MockEmbedder(),
            [fighter("horse", "Horse")],
            tmp_path,
        )
    assert summary.parsed == 1 and summary.facts == 2  # the article and Wikidata still load
    assert sorted(f.split(":")[0] for f in summary.failures) == ["animaltraits", "pantheria"]


async def test_datasets_download_once_and_a_rerun_changes_nothing(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    calls: list[str] = []
    fighters = [fighter("horse", "Horse")]
    handler = make_handler(calls, entity=HORSE)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await ingest_all(database, client, CountingParser(), MockEmbedder(), fighters, tmp_path)
        before = rows(database)
        await ingest_all(database, client, CountingParser(), MockEmbedder(), fighters, tmp_path)
    assert rows(database) == before
    assert sum("PanTHERIA" in path for path in calls) == 1
