"""Shared HTTP helper for live adapters: timeout, 2 retries with backoff, latency-only logging."""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RETRIES = 2
BACKOFF_S = 0.5
RETRY_STATUSES = {429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    """A live call failed; the message names the provider and status, never the URL or key."""


# POST JSON and return the parsed reply, retrying transient failures.
async def post_json(
    *,
    provider: str,
    base_url: str,
    path: str,
    api_key: str,
    payload: dict[str, Any],
    timeout_s: float,
    client: httpx.AsyncClient | None = None,
) -> Any:
    return await _request_json(
        "POST", provider, base_url, path, api_key, payload, timeout_s, client
    )


# GET a JSON reply, with the same retries as post_json.
async def get_json(
    *,
    provider: str,
    base_url: str,
    path: str,
    api_key: str,
    timeout_s: float,
    client: httpx.AsyncClient | None = None,
) -> Any:
    return await _request_json("GET", provider, base_url, path, api_key, None, timeout_s, client)


# Send one request and return the parsed reply, retrying transient failures.
async def _request_json(
    method: str,
    provider: str,
    base_url: str,
    path: str,
    api_key: str,
    payload: dict[str, Any] | None,
    timeout_s: float,
    client: httpx.AsyncClient | None,
) -> Any:
    headers = {"Authorization": f"Bearer {api_key}"}
    owned = client is None
    client = client or httpx.AsyncClient(timeout=timeout_s)
    try:
        for attempt in range(RETRIES + 1):
            started = time.perf_counter()
            try:
                response = await client.request(
                    method, base_url + path, json=payload, headers=headers
                )
            except httpx.TransportError as error:
                problem = f"{type(error).__name__}"
            else:
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.info(
                    "%s %s -> %s in %.0f ms", provider, path, response.status_code, elapsed_ms
                )
                if response.status_code < 400:
                    return response.json()
                problem = f"HTTP {response.status_code}"
                if response.status_code not in RETRY_STATUSES:
                    break
            if attempt < RETRIES:
                await asyncio.sleep(BACKOFF_S * 2**attempt)
        raise ProviderError(f"Live '{provider}' call to {path} failed: {problem}.")
    finally:
        if owned:
            await client.aclose()
