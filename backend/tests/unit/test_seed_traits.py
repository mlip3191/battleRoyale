"""G02: seed trait rows come from the Hugging Face team dataset, else the original files."""

import asyncio
import logging
import secrets
from pathlib import Path

import httpx
import pytest

from app.config import get_settings, use_settings
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.providers.mock.text import MockDocParser, MockEmbedder
from app.research.facts import Fact
from app.research.ingest import ingest_all
from app.research.traits import (
    HF_TRAITS_REVISION,
    HF_TRAITS_URL,
    TraitTables,
    load_trait_tables,
    team_csv,
    team_rows,
    team_tables,
)
from tests.conftest import mock_settings

PANTHERIA_TEXT = (
    "MSW05_Binomial\t5-1_AdultBodyMass_g\t13-1_AdultHeadBodyLen_mm\nCanis lupus\t31000\t-999\n"
)
TRAITS_TEXT = (
    '"species","sex","inTextReference","body mass","body mass - units"\n'
    '"Canis lupus","male","Crile, 1940",22.68,"kg"\n'
)
# A random stand-in, made fresh for each run, so no fixed credential-like text is committed.
TOKEN = secrets.token_hex(16)


def wolf_tables() -> TraitTables:
    wolf = "Canis lupus"
    return TraitTables(
        by_source={
            "pantheria": {
                wolf: [Fact("pantheria", "5-1_AdultBodyMass_g", 31000.0, "g", "p#Canis_lupus")]
            },
            "animaltraits": {
                wolf: [
                    Fact("animaltraits", "body mass", 22.68, "kg", "a#row-2 (Crile, 1940; male)")
                ],
                "Mus musculus": [Fact("animaltraits", "body mass", 0.02, "kg", "a#row-3 (x)")],
            },
        },
    )


def test_the_team_csv_holds_only_the_seed_species_and_reads_back() -> None:
    text = team_csv(team_rows(wolf_tables(), {"Canis lupus"}))
    assert "Mus musculus" not in text
    tables = team_tables(text)
    assert set(tables.by_source) == {"pantheria", "animaltraits"}
    fact = tables.by_source["animaltraits"]["Canis lupus"][0]
    assert (fact.value, fact.unit, fact.field) == (22.68, "kg", "body mass")
    assert fact.reference.startswith("a#row-2 (Crile, 1940; male)")  # the original source first
    assert HF_TRAITS_URL in fact.reference
    assert tables.licenses["pantheria"].startswith("No copyright restrictions")
    assert "Hugging Face" in tables.origin


def test_bad_team_rows_are_skipped() -> None:
    text = (
        "scientific_name,source,field,value,unit,reference\n"
        "Canis lupus,made-up-source,body mass,20,kg,x\n"
        "Canis lupus,animaltraits,body mass,not a number,kg,x\n"
        ",animaltraits,body mass,20,kg,x\n"
        "Canis lupus,animaltraits,body mass,-5,kg,x\n"
    )
    assert team_tables(text).by_source == {}


def handler_for(hf: str, seen: list[httpx.Request]):
    team = team_csv(team_rows(wolf_tables(), {"Canis lupus"})).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "huggingface.co":
            if hf == "rejects token":  # a bad or expired token on a public dataset
                rejected = "Authorization" in request.headers
                return httpx.Response(401) if rejected else httpx.Response(200, content=team)
            return {"ok": httpx.Response(200, content=team), "missing": httpx.Response(404)}.get(
                hf, httpx.Response(200, content=b"<html>not a csv</html>")
            )
        text = PANTHERIA_TEXT if request.url.host == "esapubs.org" else TRAITS_TEXT
        return httpx.Response(200, content=text.encode())

    return handler


def load(hf: str, tmp_path: Path, token: str | None = None):
    seen: list[httpx.Request] = []

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler_for(hf, seen))
        ) as client:
            return await load_trait_tables(client, tmp_path, hf_token=token)

    tables, failures = asyncio.run(run())
    return tables, failures, seen


def test_the_team_dataset_is_used_when_hugging_face_answers(tmp_path: Path) -> None:
    tables, failures, seen = load("ok", tmp_path)
    assert failures == [] and "Hugging Face" in tables.origin
    assert [r.url.host for r in seen] == ["huggingface.co"]  # the originals aren't downloaded
    assert not (tmp_path / "traits").exists()


@pytest.mark.parametrize("hf", ["missing", "garbage"])
def test_the_originals_are_used_when_the_team_dataset_fails(hf: str, tmp_path: Path) -> None:
    tables, failures, _ = load(hf, tmp_path)
    assert failures == [] and tables.origin == "the original dataset downloads"
    assert "Canis lupus" in tables.by_source["pantheria"]


def test_the_token_goes_only_in_the_header_and_never_in_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        _, _, seen = load("missing", tmp_path, token=TOKEN)
    hf = [r for r in seen if r.url.host == "huggingface.co"]
    assert hf and all(r.headers["Authorization"] == f"Bearer {TOKEN}" for r in hf)
    assert all("Authorization" not in r.headers for r in seen if r.url.host != "huggingface.co")
    assert TOKEN not in caplog.text and all(TOKEN not in str(r.url) for r in seen)


def test_no_token_sends_no_authorization_header(tmp_path: Path) -> None:
    _, _, seen = load("ok", tmp_path)
    assert all("Authorization" not in r.headers for r in seen)


def test_a_row_with_no_reference_is_skipped() -> None:
    text = (
        "scientific_name,source,field,value,unit,reference\n"
        "Canis lupus,animaltraits,body mass,20,kg,\n"
        'Canis lupus,animaltraits,body mass,22,kg,"a#row-2 (Crile, 1940)"\n'
    )
    facts = team_tables(text).by_source["animaltraits"]["Canis lupus"]
    assert [f.value for f in facts] == [22.0]


def test_the_dataset_file_is_pinned_to_one_version() -> None:
    assert f"/resolve/{HF_TRAITS_REVISION}/seed-traits.csv" in HF_TRAITS_URL
    assert "/resolve/main/" not in HF_TRAITS_URL


def test_a_rejected_token_is_retried_without_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        tables, failures, seen = load("rejects token", tmp_path, token=TOKEN)
    assert failures == [] and "Hugging Face" in tables.origin
    hf = [r for r in seen if r.url.host == "huggingface.co"]
    assert ["Authorization" in r.headers for r in hf] == [True, False]
    assert "rejected HF_TOKEN" in caplog.text and TOKEN not in caplog.text


def test_ingest_reads_the_token_from_settings_and_never_shows_it(tmp_path: Path) -> None:
    use_settings(mock_settings(hf_token=TOKEN))
    assert TOKEN not in repr(get_settings()) and TOKEN not in str(get_settings())
    seen: list[httpx.Request] = []
    connection = connect(tmp_path / "app.db")
    apply_migrations(connection)

    async def run():
        transport = httpx.MockTransport(handler_for("ok", seen))
        async with httpx.AsyncClient(transport=transport) as client:
            return await ingest_all(
                connection, client, MockDocParser(), MockEmbedder(), [], tmp_path
            )

    try:
        summary = asyncio.run(run())
    finally:
        connection.close()
    hf = [r for r in seen if r.url.host == "huggingface.co"]
    assert hf and hf[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert "Hugging Face" in summary.trait_origin
