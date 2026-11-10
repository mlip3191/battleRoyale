"""Wikipedia and Wikidata downloaders and the seed list, with no network calls."""

import json
import re
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from app.config import REPO_ROOT
from app.research.seed_fighters import load_seed_fighters
from app.research.sources import (
    USER_AGENT,
    SourceError,
    fetch_article,
    fetch_wikidata,
    save_raw,
)

Handler = Callable[[httpx.Request], httpx.Response]
# Reads the seed table in docs/research.md, so update this if that table changes shape.
SEED_ROW = re.compile(
    r"^\| \d+ \| `([a-z-]+)` \| (.+?) \| (.+?) \| (\w+) \| (\w+) \| (\w+) \| (.+?) \|$", re.M
)


def client_with(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def no_sleep(seconds: float) -> None:
    pass


async def test_article_uses_a_pinned_url_and_a_project_user_agent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == USER_AGENT
        assert request.url.path.endswith("/page/html/Grizzly_bear")
        return httpx.Response(200, headers={"ETag": '"123/abc"'}, content=b"<p>bear</p>")

    document = await fetch_article(client_with(handler), "Grizzly bear", sleep=no_sleep)
    assert document is not None
    assert document.url.endswith("title=Grizzly_bear&oldid=123")
    assert document.license == "CC BY-SA 4.0" and document.body == b"<p>bear</p>"


async def test_a_missing_article_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    assert await fetch_article(client_with(handler), "No such page", sleep=no_sleep) is None


async def test_rate_limits_are_retried_using_retry_after() -> None:
    waits: list[float] = []
    replies = [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, content=b"x")]

    async def record(seconds: float) -> None:
        waits.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        return replies.pop(0)

    document = await fetch_article(client_with(handler), "Horse", sleep=record)
    assert document is not None and waits == [7.0]


async def test_repeated_failures_raise_a_source_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(SourceError, match="HTTP 503"):
        await fetch_article(client_with(handler), "Horse", sleep=no_sleep)


async def test_wikidata_returns_the_entity_or_none_when_missing() -> None:
    def found(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"entities": {"Q1": {"id": "Q1", "claims": {}}}})

    def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"entities": {"-1": {"missing": ""}}})

    document = await fetch_wikidata(client_with(found), "Horse", sleep=no_sleep)
    assert document is not None
    assert document.url.endswith("/wiki/Q1") and document.license == "CC0 1.0"
    assert json.loads(document.body)["id"] == "Q1"
    assert await fetch_wikidata(client_with(missing), "Nope", sleep=no_sleep) is None


async def test_save_raw_writes_the_body_and_its_details(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<p>x</p>")

    document = await fetch_article(client_with(handler), "Horse", sleep=no_sleep)
    assert document is not None
    path = save_raw(tmp_path, "horse", "wikipedia", document)
    assert path.read_bytes() == b"<p>x</p>"
    details = json.loads((tmp_path / "horse" / "wikipedia.meta.json").read_text(encoding="utf-8"))
    assert set(details) == {"title", "url", "license", "retrieved_at", "media_type"}


def test_seed_list_matches_the_table_in_research_doc() -> None:
    text = (REPO_ROOT / "docs" / "research.md").read_text(encoding="utf-8")
    expected = [
        (slug, name, variant.replace("*", ""), category, body, habitat, article)
        for slug, name, variant, category, body, habitat, article in SEED_ROW.findall(text)
    ]
    fighters = load_seed_fighters()
    actual = [
        (f.id, f.display_name, f.variant, f.category, f.body, f.habitat, f.article)
        for f in fighters
    ]
    assert len(actual) == 30
    assert actual == expected
