"""The health endpoint answers, and the built front end is served with an index.html fallback."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_returns_ok(settings: Settings, tmp_path: Path) -> None:
    client = TestClient(create_app(settings, frontend_dist=tmp_path / "missing"))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["provider_mode"] == "mock"
    assert set(response.json()["providers"].values()) == {"mock"}
    assert len(response.json()["providers"]) == 8


def test_serves_built_frontend_with_route_fallback(settings: Settings, tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<p>home</p>", encoding="utf-8")
    (tmp_path / "app.js").write_text("console.log(1)", encoding="utf-8")
    client = TestClient(create_app(settings, frontend_dist=tmp_path))
    assert client.get("/").text == "<p>home</p>"
    assert client.get("/app.js").text == "console.log(1)"
    assert client.get("/battle/42").text == "<p>home</p>"
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/nope").status_code == 404
