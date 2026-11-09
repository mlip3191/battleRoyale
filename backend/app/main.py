"""FastAPI app factory: API routes, CORS, and the built front end for `npm start`."""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import REPO_ROOT, Settings, get_settings

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

    # Liveness check used by the front end and CI.
    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    if frontend_dist.is_dir():
        _serve_frontend(app, frontend_dist.resolve())
    return app


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
