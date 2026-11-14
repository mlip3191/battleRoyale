"""The health endpoint answers, the built front end is served with an index.html fallback, and
generated media is served from /media."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import mock_settings


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


def test_serves_generated_media_even_with_the_frontend_built(tmp_path: Path) -> None:
    settings = mock_settings(data_dir=tmp_path / "data")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<p>home</p>", encoding="utf-8")
    client = TestClient(create_app(settings, frontend_dist=dist))
    sprite = tmp_path / "data" / "media" / "sprites" / "gray-wolf-v1.png"
    sprite.parent.mkdir(parents=True)
    sprite.write_bytes(b"\x89PNG fake")
    response = client.get("/media/sprites/gray-wolf-v1.png")
    assert response.status_code == 200 and response.content == b"\x89PNG fake"
    assert response.headers["content-type"] == "image/png"
    assert client.get("/media/sprites/missing.png").status_code == 404
