"""Shared HTTP helper for live adapters: timeout, retries with backoff, latency-only logging."""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RETRIES = 2  # default; a caller can pass fewer (intake uses Settings.intake_retries)
BACKOFF_S = 0.5
RETRY_STATUSES = {429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    """A live call failed; the message names the provider and status, never the URL or key."""

    # `status` and `detail` (the start of the error reply) let code tell one failure from
    # another (#176). The detail is never put in the message, so it isn't logged or shown.
    def __init__(self, message: str, status: int | None = None, detail: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


# How much of an error reply ProviderError keeps for code to check.
DETAIL_CHARS = 1_000


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
    retries: int = RETRIES,
) -> Any:
    return await _request_json(
        "POST", provider, base_url, path, api_key, payload, timeout_s, client, retries
    )


# POST multipart/form-data (text fields plus file parts) and return the parsed JSON reply,
# with the same retries as post_json. files maps a field name to (filename, bytes, mime).
async def post_multipart(
    *,
    provider: str,
    base_url: str,
    path: str,
    api_key: str,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    timeout_s: float,
    client: httpx.AsyncClient | None = None,
    retries: int = RETRIES,
) -> Any:
    return await _request_json(
        "POST",
        provider,
        base_url,
        path,
        api_key,
        None,
        timeout_s,
        client,
        retries,
        form=(fields, files),
    )


# POST JSON and return the raw reply bytes (e.g. audio from TTS), with the same retries as
# post_json. The reply is never parsed as JSON.
async def post_bytes(
    *,
    provider: str,
    base_url: str,
    path: str,
    api_key: str,
    payload: dict[str, Any],
    timeout_s: float,
    client: httpx.AsyncClient | None = None,
    retries: int = RETRIES,
) -> bytes:
    reply: bytes = await _request_json(
        "POST", provider, base_url, path, api_key, payload, timeout_s, client, retries, raw=True
    )
    return reply


# GET a JSON reply, with the same retries as post_json.
async def get_json(
    *,
    provider: str,
    base_url: str,
    path: str,
    api_key: str,
    timeout_s: float,
    client: httpx.AsyncClient | None = None,
    retries: int = RETRIES,
) -> Any:
    return await _request_json(
        "GET", provider, base_url, path, api_key, None, timeout_s, client, retries
    )


# Send one request and return the parsed reply (or its raw bytes when raw is set), retrying
# transient failures. Every live call goes through here, so scripts/eval_cost.py can count them.
async def _request_json(
    method: str,
    provider: str,
    base_url: str,
    path: str,
    api_key: str,
    payload: dict[str, Any] | None,
    timeout_s: float,
    client: httpx.AsyncClient | None,
    retries: int = RETRIES,
    form: tuple[dict[str, str], dict[str, tuple[str, bytes, str]]] | None = None,
    raw: bool = False,
) -> Any:
    headers = {"Authorization": f"Bearer {api_key}"}
    body: dict[str, Any] = (
        {"json": payload} if form is None else {"data": form[0], "files": form[1]}
    )
    owned = client is None
    client = client or httpx.AsyncClient(timeout=timeout_s)
    status: int | None = None
    detail = ""
    try:
        for attempt in range(retries + 1):
            started = time.perf_counter()
            try:
                response = await client.request(method, base_url + path, headers=headers, **body)
            except httpx.TransportError as error:
                problem = f"{type(error).__name__}"
            else:
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.info(
                    "%s %s -> %s in %.0f ms", provider, path, response.status_code, elapsed_ms
                )
                if response.status_code < 400:
                    return response.content if raw else response.json()
                problem = f"HTTP {response.status_code}"
                status, detail = response.status_code, response.text[:DETAIL_CHARS]
                if response.status_code not in RETRY_STATUSES:
                    break
            if attempt < retries:
                await asyncio.sleep(BACKOFF_S * 2**attempt)
        raise ProviderError(f"Live '{provider}' call to {path} failed: {problem}.", status, detail)
    finally:
        if owned:
            await client.aclose()
