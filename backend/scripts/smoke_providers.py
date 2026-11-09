"""Call each configured course endpoint once and write what we learn to docs/providers.md.

Run by hand (never in CI), from the repo root:
  uv run --directory backend python scripts/smoke_providers.py
The report records only shapes (keys and types), statuses, and latency: never response text.
Every host, URL, and key is redacted before writing; if anything is left, nothing is written.
The terminal shows only a pass/fail line per service.
"""

import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import REPO_ROOT, Settings, get_settings  # noqa: E402
from app.providers.live.chat import LiveChatLLM  # noqa: E402
from app.providers.registry import service_config  # noqa: E402

REPORT = REPO_ROOT / "docs" / "providers.md"
DISCOVERY_PATHS = ("/v1/models", "/docs", "/openapi.json", "/health")
TIMEOUT_S = 30.0
SLOW_TIMEOUT_S = 180.0

# (label, settings prefix, what the course list calls it)
SERVICES = (
    ("chat", "chat_llm", "Chat / Classification LLM"),
    ("structured", "structured_llm", "Structured Decisions"),
    ("embeddings", "embeddings", "Text Embeddings"),
    ("rerank", "rerank", "Multimodal Reranking"),
    ("doc_parse", "doc_parse", "Document Parsing"),
    ("image", "image", "Image Generation and Editing"),
    ("tts", "tts", "Text-to-Speech and Voice Cloning"),
    ("music", "music", "Music Generation"),
    ("stt", "stt", "Speech-to-Text (stretch)"),
    ("mm_embeddings", "mm_embeddings", "Multimodal Embeddings (stretch)"),
)


@dataclass
class Finding:
    """One service's results, as Markdown-ready lines."""

    label: str
    title: str
    url_shape: str
    lines: list[str] = field(default_factory=list)
    passed: bool = True


# Describe JSON by structure only (keys and types), so no response text reaches the report.
def shape(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "…"
    if isinstance(value, dict):
        return {key: shape(item, depth + 1) for key, item in list(value.items())[:25]}
    if isinstance(value, list):
        return [shape(value[0], depth + 1), f"({len(value)} items)"] if value else []
    return type(value).__name__


# One request; returns (status or error name, latency ms, parsed JSON or None, response).
async def call(
    client: httpx.AsyncClient, method: str, url: str, **kwargs: Any
) -> tuple[str, float, Any, httpx.Response | None]:
    started = time.perf_counter()
    try:
        response = await client.request(method, url, **kwargs)
    except httpx.HTTPError as error:
        return type(error).__name__, (time.perf_counter() - started) * 1000, None, None
    elapsed = (time.perf_counter() - started) * 1000
    try:
        body = response.json()
    except ValueError:
        body = None
    return str(response.status_code), elapsed, body, response


# Format one request's result as a Markdown bullet.
def bullet(what: str, status: str, ms: float, detail: str = "") -> str:
    return f"- `{what}` → **{status}** in {ms:.0f} ms{(' — ' + detail) if detail else ''}"


# Discovery: which standard paths answer, the model list, the OpenAPI paths, and the auth style.
async def discover(client: httpx.AsyncClient, base: str, headers: dict[str, str], f: Finding):
    models: list[str] = []
    for path in DISCOVERY_PATHS:
        status, ms, body, response = await call(client, "GET", base + path, headers=headers)
        kind = response.headers.get("content-type", "").split(";")[0] if response else ""
        detail = kind
        if path == "/v1/models" and isinstance(body, dict):
            models = [m.get("id", "") for m in body.get("data", []) if isinstance(m, dict)]
            detail = f"models: {', '.join(f'`{m}`' for m in models)}"
        if path == "/openapi.json" and isinstance(body, dict):
            routes = [
                f"{method.upper()} {route}"
                for route, ops in body.get("paths", {}).items()
                for method in (ops if isinstance(ops, dict) else {})
            ]
            detail = "paths: " + ", ".join(f"`{r}`" for r in routes[:40])
        f.lines.append(bullet(f"GET {path}", status, ms, detail))

    probe = "/v1/models" if models else "/openapi.json"
    no_auth, _, _, _ = await call(client, "GET", base + probe)
    with_auth, _, _, _ = await call(client, "GET", base + probe, headers=headers)
    if no_auth in ("401", "403") and with_auth.startswith("2"):
        auth = "Bearer key **required** (`Authorization: Bearer <key>`)"
    elif no_auth.startswith("2") and with_auth.startswith("2"):
        auth = "no key enforced on discovery paths; Bearer key accepted"
    else:
        auth = f"unclear (without key: {no_auth}, with Bearer key: {with_auth})"
    f.lines.insert(0, f"- **Auth:** {auth}")
    return models


# Record a JSON request's status, latency, and reply shape.
async def try_json(
    client: httpx.AsyncClient, f: Finding, path: str, base: str, headers: dict, payload: dict
) -> tuple[str, Any]:
    status, ms, body, response = await call(
        client, "POST", base + path, headers=headers, json=payload
    )
    kind = response.headers.get("content-type", "").split(";")[0] if response else ""
    f.lines.append(bullet(f"POST {path}", status, ms, kind))
    f.lines.append(f"  - request keys: `{json.dumps(shape(payload))}`")
    if body is not None:
        f.lines.append(f"  - reply shape: `{json.dumps(shape(body))}`")
    elif response is not None:
        f.lines.append(f"  - reply: {len(response.content)} bytes of `{kind or 'unknown'}`")
    return status, body


# The tiny real request for each service (or discovery only, where a call is costly).
async def exercise(
    label: str,
    client: httpx.AsyncClient,
    base: str,
    headers: dict,
    models: list[str],
    settings: Settings,
    f: Finding,
) -> None:
    first_model = models[0] if models else ""
    if label == "chat":
        await exercise_chat(settings, f)
    elif label == "embeddings":
        payload = {"model": settings.embeddings_model, "input": ["a gray wolf"]}
        status, body = await try_json(client, f, "/v1/embeddings", base, headers, payload)
        f.passed = status == "200"
        if isinstance(body, dict) and body.get("data"):
            f.lines.append(f"  - vector length: {len(body['data'][0].get('embedding', []))}")
    elif label == "rerank":
        payload = {"model": first_model, "query": "wolf", "documents": ["a gray wolf", "a toaster"]}
        for path in ("/v1/rerank", "/rerank", "/v1/score"):
            status, _ = await try_json(client, f, path, base, headers, payload)
            if status == "200":
                break
        f.passed = status == "200"
    elif label == "structured":
        status, ms, body, _ = await call(client, "GET", base + "/examples", headers=headers)
        f.lines.append(bullet("GET /examples", status, ms))
        if body is not None:
            f.lines.append(f"  - examples shape: `{json.dumps(shape(body))}`")
        example = first_example(body)
        if example is not None:
            status, _ = await try_json(client, f, "/v1/decisions", base, headers, example)
        f.passed = status == "200"
    elif label == "tts":
        status, ms, body, _ = await call(client, "GET", base + "/v1/voices", headers=headers)
        f.lines.append(bullet("GET /v1/voices", status, ms))
        if body is not None:
            f.lines.append(f"  - voices shape: `{json.dumps(shape(body))}`")
        payload = {"model": "chatterbox-v3", "input": "Let's get ready to rumble!"}
        status, _ = await try_json(client, f, "/v1/audio/speech", base, headers, payload)
        f.passed = status == "200"
    elif label == "image":
        payload = {
            "model": first_model,
            "prompt": "a red apple on a wooden table",
            "size": "256x256",
            "n": 1,
        }
        async with httpx.AsyncClient(timeout=SLOW_TIMEOUT_S) as slow:
            status, _ = await try_json(slow, f, "/v1/images/generations", base, headers, payload)
        f.passed = status == "200"
    else:
        f.lines.append(
            "- Discovery only (a real request is slow or needs an upload); "
            "the adapter task should test a request by hand."
        )


# Pick a request body from the /examples reply, whatever its layout.
def first_example(body: Any) -> dict | None:
    if isinstance(body, dict):
        for key in ("examples", "requests"):
            if isinstance(body.get(key), list) and body[key]:
                body = body[key]
                break
        else:
            values = [v for v in body.values() if isinstance(v, dict)]
            body = values or body
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        for key in ("request", "body", "payload", "value"):
            if isinstance(body.get(key), dict):
                return body[key]
        return body
    return None


# Chat goes through the real LiveChatLLM adapter: plain text, then JSON-schema mode.
async def exercise_chat(settings: Settings, f: Finding) -> None:
    chat = LiveChatLLM(service_config("chat", settings), settings)
    messages = [{"role": "user", "content": "Reply with the single word OK."}]
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    for mode, kwargs in (("plain", {}), ("json_schema", {"json_schema": schema})):
        started = time.perf_counter()
        try:
            reply = await chat.complete(messages, prompt_name="smoke", **kwargs)  # type: ignore[arg-type]
        except Exception as error:  # noqa: BLE001 - report any failure by type only
            f.passed = False
            f.lines.append(f"- LiveChatLLM ({mode}) → **failed**: {type(error).__name__}")
            continue
        ms = (time.perf_counter() - started) * 1000
        detail = f"{len(reply)} characters"
        if mode == "json_schema":
            try:
                parsed = json.loads(reply)
                valid = isinstance(parsed, dict) and isinstance(parsed.get("ok"), bool)
                detail += ", valid JSON matching the schema" if valid else ", JSON but off-schema"
                f.passed = f.passed and valid
            except ValueError:
                detail += ", **not JSON**"
                f.passed = False
        f.lines.append(
            f"- LiveChatLLM ({mode}) via `POST /v1/chat/completions` → **ok** in "
            f"{ms:.0f} ms — {detail}"
        )


# Every configured secret: hosts, URLs, origins, and keys (longest first, so URLs go before hosts).
def secrets(settings: Settings) -> list[tuple[str, str]]:
    found: dict[str, str] = {}
    for _, prefix, _ in SERVICES:
        url = str(getattr(settings, f"{prefix}_url", "") or "")
        if url:
            parts = urlsplit(url)
            found[url.rstrip("/")] = "<url>"
            found[f"{parts.scheme}://{parts.netloc}"] = "<url>"
            if parts.hostname:
                found[parts.hostname] = "<host>"
        key = getattr(settings, f"{prefix}_api_key", None)
        if key and key.get_secret_value():
            found[key.get_secret_value()] = "<key>"
    if settings.course_api_key.get_secret_value():
        found[settings.course_api_key.get_secret_value()] = "<key>"
    return sorted(found.items(), key=lambda item: -len(item[0]))


# Replace every secret in any letter case; return the text and how many are left (must be 0).
def redact(text: str, settings: Settings) -> tuple[str, int]:
    pairs = secrets(settings)
    for value, placeholder in pairs:
        text = re.sub(re.escape(value), placeholder, text, flags=re.IGNORECASE)
    remaining = sum(text.lower().count(value.lower()) for value, _ in pairs)
    return text, remaining


# Build the Markdown report.
def render(findings: list[Finding]) -> str:
    out = [
        "# Course providers: what the smoke test found",
        "",
        f"Generated by `backend/scripts/smoke_providers.py` on {date.today().isoformat()} "
        "(task M06). Hosts and keys are replaced with `<host>`, `<url>`, and `<key>`; "
        "replies are recorded by shape only.",
        "",
        "| Service | Course list name | Base URL shape | Result |",
        "|---|---|---|---|",
    ]
    for f in findings:
        out.append(
            f"| `{f.label}` | {f.title} | `{f.url_shape}` | {'pass' if f.passed else 'FAIL'} |"
        )
    for f in findings:
        out += ["", f"## `{f.label}` — {f.title}", "", f"Base URL: `{f.url_shape}`", "", *f.lines]
    return "\n".join(out) + "\n"


# Run every configured service, then write the redacted report.
async def main() -> int:
    settings = get_settings()
    findings: list[Finding] = []
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        for label, prefix, title in SERVICES:
            url = str(getattr(settings, f"{prefix}_url", "") or "").rstrip("/")
            if not url or "replace-me" in url:
                continue
            key = getattr(settings, f"{prefix}_api_key", None) or settings.course_api_key
            headers = {"Authorization": f"Bearer {key.get_secret_value()}"}
            port = urlsplit(url).port
            f = Finding(label, title, f"http://<host>:{port}" if port else "http://<host>")
            try:
                models = await discover(client, url, headers, f)
                await exercise(label, client, url, headers, models, settings, f)
            except Exception as error:  # noqa: BLE001 - report any failure by type only
                f.passed = False
                f.lines.append(f"- Smoke run stopped: {type(error).__name__}")
            findings.append(f)
            print(f"{label:14} {'pass' if f.passed else 'FAIL'}")

    if not findings:
        print("No services configured. Run npm run env:check.")
        return 1
    text, remaining = redact(render(findings), settings)
    if remaining:
        print(f"Redaction scan: {remaining} secret value(s) still present. Nothing written.")
        return 1
    REPORT.write_text(text, encoding="utf-8")
    print(f"Redaction scan: 0 remaining. Wrote {REPORT.relative_to(REPO_ROOT)}.")
    return 0 if all(f.passed for f in findings) else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
