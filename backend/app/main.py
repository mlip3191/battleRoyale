"""FastAPI app factory: API routes, CORS, and the built front end for `npm start`."""

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse

from app.api.intake import router as intake_router
from app.config import REPO_ROOT, Settings, get_settings
from app.models import contract_schemas
from app.providers.health import provider_statuses

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

# At INFO these loggers print full request URLs, which include course endpoint hosts.
for _noisy in ("httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


# Build the app; tests pass their own settings and front-end folder.
def create_app(settings: Settings | None = None, frontend_dist: Path = FRONTEND_DIST) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Battle Royale", version="0.1.0")
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
    if frontend_dist.is_dir():
        _serve_frontend(app, frontend_dist.resolve())
    app.openapi = lambda: _openapi_with_contracts(app)
    return app


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
