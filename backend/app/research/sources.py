"""Download raw reference documents (Wikipedia HTML, Wikidata JSON) and save them under data/kb/."""

import asyncio
import json
import re
import urllib.parse
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

USER_AGENT = "battle-royale-course-project/0.1"
WIKIPEDIA_HTML = "https://en.wikipedia.org/api/rest_v1/page/html/{title}"
WIKIPEDIA_PAGE = "https://en.wikipedia.org/wiki/{title}"
WIKIPEDIA_REVISION = "https://en.wikipedia.org/w/index.php?title={title}&oldid={revision}"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_PAGE = "https://www.wikidata.org/wiki/{entity}"
RETRIES = 4
BACKOFF_S = 2.0
MAX_WAIT_S = 60.0
RETRY_STATUSES = {429, 500, 502, 503, 504}

Sleep = Callable[[float], Awaitable[None]]


class SourceError(RuntimeError):
    """A download failed for a reason other than the page not existing."""


@dataclass(frozen=True)
class SourceDocument:
    """One downloaded document and where it came from."""

    title: str
    url: str
    license: str
    retrieved_at: datetime
    media_type: str
    body: bytes


# How long to wait before a retry: the server's Retry-After (capped) if given, else backoff.
def _wait_s(response: httpx.Response | None, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After", "") if response is not None else ""
    wait = float(retry_after) if retry_after.isdigit() else BACKOFF_S * 2**attempt
    return min(wait, MAX_WAIT_S)


# GET a URL with retries; None means the page does not exist.
async def _get(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, str] | None = None,
    sleep: Sleep = asyncio.sleep,
) -> httpx.Response | None:
    problem = "no response"
    for attempt in range(RETRIES + 1):
        response: httpx.Response | None = None
        try:
            response = await client.get(
                url, params=params, headers={"User-Agent": USER_AGENT}, follow_redirects=True
            )
        except httpx.TransportError as error:
            problem = type(error).__name__
        if response is not None:
            if response.status_code == 404:
                return None
            if response.status_code < 400:
                return response
            problem = f"HTTP {response.status_code}"
            if response.status_code not in RETRY_STATUSES:
                break
        if attempt < RETRIES:
            await sleep(_wait_s(response, attempt))
    raise SourceError(f"Download failed: {problem}.")


# Fetch one Wikipedia article's HTML; None if the article does not exist.
async def fetch_article(
    client: httpx.AsyncClient, title: str, sleep: Sleep = asyncio.sleep
) -> SourceDocument | None:
    slug = urllib.parse.quote(title.replace(" ", "_"), safe="")
    response = await _get(client, WIKIPEDIA_HTML.format(title=slug), sleep=sleep)
    if response is None:
        return None
    revision = re.search(r"(\d+)/", response.headers.get("ETag", ""))
    url = (
        WIKIPEDIA_REVISION.format(title=slug, revision=revision.group(1))
        if revision
        else WIKIPEDIA_PAGE.format(title=slug)
    )
    return SourceDocument(
        title=title,
        url=url,
        license="CC BY-SA 4.0",
        retrieved_at=datetime.now(UTC),
        media_type="text/html",
        body=response.content,
    )


# Fetch the Wikidata entity linked to a Wikipedia article; None if there is none.
async def fetch_wikidata(
    client: httpx.AsyncClient, title: str, sleep: Sleep = asyncio.sleep
) -> SourceDocument | None:
    params = {"action": "wbgetentities", "sites": "enwiki", "titles": title, "format": "json"}
    response = await _get(client, WIKIDATA_API, params=params, sleep=sleep)
    if response is None:
        return None
    entities: dict[str, Any] = response.json().get("entities", {})
    found = [(key, value) for key, value in entities.items() if not key.startswith("-")]
    if not found:
        return None
    entity_id, entity = found[0]
    return SourceDocument(
        title=title,
        url=WIKIDATA_PAGE.format(entity=entity_id),
        license="CC0 1.0",
        retrieved_at=datetime.now(UTC),
        media_type="application/json",
        body=json.dumps(entity, ensure_ascii=False).encode("utf-8"),
    )


# Save a document and its details as data/kb/<fighter>/<name>.<ext> plus <name>.meta.json.
def save_raw(kb_dir: Path, fighter_id: str, name: str, document: SourceDocument) -> Path:
    folder = kb_dir / fighter_id
    folder.mkdir(parents=True, exist_ok=True)
    extension = "html" if document.media_type == "text/html" else "json"
    path = folder / f"{name}.{extension}"
    path.write_bytes(document.body)
    details = {
        "title": document.title,
        "url": document.url,
        "license": document.license,
        "retrieved_at": document.retrieved_at.isoformat(),
        "media_type": document.media_type,
    }
    (folder / f"{name}.meta.json").write_text(
        json.dumps(details, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path
