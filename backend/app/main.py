"""FastAPI app factory: API routes, CORS, and the built front end for `npm start`."""

import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.battles import router as battles_router
from app.api.intake import router as intake_router
from app.config import REPO_ROOT, Settings, get_settings
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.db.showcase import SHOWCASE_DIR, import_showcase
from app.models import contract_schemas
from app.providers.health import provider_statuses

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
logger = logging.getLogger(__name__)
EMPTY_KB = (
    "The knowledge base is empty, so new fighters can't be researched yet. "
    "Run `npm run ingest` once (it takes a few minutes), then restart."
)

# At INFO these loggers print full request URLs, which include course endpoint hosts.
for _noisy in ("httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


# Build the app; tests pass their own settings and front-end folder.
def create_app(
    settings: Settings | None = None,
    frontend_dist: Path = FRONTEND_DIST,
    showcase_dir: Path | None = SHOWCASE_DIR,
) -> FastAPI:
    settings = settings or get_settings()

    # At startup: load the showcase into an empty database, and in live mode say if the
    # knowledge base still needs building. Neither step may stop the app from starting.
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        _startup(settings, showcase_dir)
        yield

    app = FastAPI(title="Battle Royale", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Liveness check used by the front end and CI, with each provider's mock/up/down status.
    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "provider_mode": settings.provider_mode,
            "providers": await provider_statuses(settings),
        }

    app.include_router(intake_router)
    app.include_router(battles_router)
    # Generated sprites and battlefields (A08), e.g. /media/sprites/gray-wolf-v1.png.
    media_dir = settings.data_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=media_dir), name="media")
    if frontend_dist.is_dir():
        _serve_frontend(app, frontend_dist.resolve())
    app.openapi = lambda: _openapi_with_contracts(app)
    return app


# Load the showcase if the database is empty, and warn about an empty knowledge base in live mode.
def _startup(settings: Settings, showcase_dir: Path | None) -> None:
    try:
        connection = connect(settings.data_dir / "app.db")
        try:
            apply_migrations(connection)
            if showcase_dir is not None:
                import_showcase(connection, settings.data_dir / "media", showcase_dir)
            if settings.provider_mode == "live" and not _has_passages(connection):
                logger.warning(EMPTY_KB)
                print(EMPTY_KB)
        finally:
            connection.close()
    except (sqlite3.Error, OSError, ValueError) as error:
        logger.warning("Startup checks skipped (%s).", type(error).__name__)


# True when the knowledge base has at least one stored passage.
def _has_passages(connection: sqlite3.Connection) -> bool:
    try:
        return connection.execute("SELECT 1 FROM chunks LIMIT 1").fetchone() is not None
    except sqlite3.Error:
        return False


# OpenAPI lists only models used by routes; add every contract so the front end gets all types.
def _openapi_with_contracts(app: FastAPI) -> dict[str, Any]:
    if app.openapi_schema is None:
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        schema.setdefault("components", {}).setdefault("schemas", {}).update(contract_schemas())
        app.openapi_schema = schema
    return app.openapi_schema


# Serve built files, falling back to index.html for front-end routes like /battle/42.
def _serve_frontend(app: FastAPI, dist: Path) -> None:
    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path.startswith(("api/", "media/")) or path in ("api", "media"):
            raise HTTPException(status_code=404)
        file = (dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(dist):
            return FileResponse(file)
        return FileResponse(dist / "index.html")


app = create_app()
