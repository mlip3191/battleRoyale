"""Per-provider status for GET /api/health: mock, or up/down from a cached quick ping."""

import asyncio
import time
from typing import Literal

import httpx

from app.config import Settings
from app.providers.base import ProviderName
from app.providers.registry import SETTINGS_PREFIX

Status = Literal["mock", "up", "down"]
PING_TIMEOUT_S = 2.0
CACHE_S = 2.0

_cache: tuple[float, dict[str, Status]] | None = None


# Any HTTP answer means the server is up; no answer in time means down.
async def _ping(client: httpx.AsyncClient, url: str) -> Status:
    if not url or "replace-me" in url:
        return "down"
    try:
        await client.get(url.rstrip("/") + "/health")
    except httpx.HTTPError:
        return "down"
    return "up"


# Status of every provider; live pings run in parallel and are cached for 2 seconds.
async def provider_statuses(settings: Settings) -> dict[str, Status]:
    global _cache
    names: list[ProviderName] = list(SETTINGS_PREFIX)
    if settings.provider_mode == "mock":
        return {name: "mock" for name in names}
    if _cache and time.monotonic() - _cache[0] < CACHE_S:
        return _cache[1]
    async with httpx.AsyncClient(timeout=PING_TIMEOUT_S) as client:
        urls = [str(getattr(settings, f"{SETTINGS_PREFIX[n]}_url", "") or "") for n in names]
        results = await asyncio.gather(*(_ping(client, url) for url in urls))
    statuses: dict[str, Status] = dict(zip(names, results, strict=True))
    _cache = (time.monotonic(), statuses)
    return statuses
