"""G08 (#47): showcase battles export to data/showcase/, load into an empty database at startup,
and list on GET /api/battles?showcase=true."""

import json
import sqlite3
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.battles import get_db, get_showcase_dir
from app.config import Settings
from app.db import battles as saved
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.db.showcase import export_showcase, import_showcase, load_manifest, showcase_rows
from app.main import create_app
from app.models.battle import BattleRecord

FIXTURE = Path(__file__).parents[1] / "fixtures" / "contracts" / "battle-record-done.json"
# Media sizes in bytes; the record's own JSON adds about 16 KB.
SIZES = {"sprite": 1_000, "battlefield": 2_000, "narration_audio": 30_000, "music": 50_000}


def record(battle_id: str = "b-7f3k2q") -> BattleRecord:
    base = BattleRecord.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    return base.model_copy(update={"battle_id": battle_id})


def database(path: Path) -> sqlite3.Connection:
    connection = connect(path)
    apply_migrations(connection)
    return connection


# A database holding one finished battle, plus a media folder with a file for every asset.
@pytest.fixture
def source(tmp_path: Path) -> Iterator[tuple[sqlite3.Connection, Path]]:
    media = tmp_path / "media"
    battle = record()
    for asset in battle.assets:
        path = media / asset.url.removeprefix("/media/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * SIZES[asset.kind])
    connection = database(tmp_path / "source.db")
    saved.save(connection, battle, cache_key="key")
    yield connection, media
    connection.close()


def test_export_then_import_round_trips_records_and_media(source, tmp_path: Path) -> None:
    connection, media = source
    out = tmp_path / "showcase"
    result = export_showcase(
        connection, [("b-7f3k2q", "Grizzly bear vs 6 Gray wolves")], media, out
    )
    assert (result.battles, result.dropped) == (1, [])
    assert [r.model_dump() for r in load_manifest(out)] == [
        {"battle_id": "b-7f3k2q", "title": "Grizzly bear vs 6 Gray wolves"}
    ]
    fresh_media = tmp_path / "fresh-media"
    fresh = database(tmp_path / "fresh.db")
    try:
        assert import_showcase(fresh, fresh_media, out) == 1
        assert saved.get(fresh, "b-7f3k2q") == saved.get(connection, "b-7f3k2q")
        for asset in record().assets:
            relative = asset.url.removeprefix("/media/")
            assert (fresh_media / relative).read_bytes() == (media / relative).read_bytes()
    finally:
        fresh.close()


def test_the_title_defaults_to_the_fighters_names(source, tmp_path: Path) -> None:
    connection, media = source
    export_showcase(connection, [("b-7f3k2q", None)], media, tmp_path / "showcase")
    names = [sheet.display_name for sheet in record().stat_sheets]
    assert load_manifest(tmp_path / "showcase")[0].title == " vs ".join(names)


def test_import_skips_a_database_that_already_has_battles(source, tmp_path: Path) -> None:
    connection, media = source
    out = tmp_path / "showcase"
    export_showcase(connection, [("b-7f3k2q", None)], media, out)
    busy = database(tmp_path / "busy.db")
    try:
        saved.save(busy, record("b-mine"), cache_key=None)
        assert import_showcase(busy, tmp_path / "m", out) == 0
        assert saved.get(busy, "b-7f3k2q") is None
    finally:
        busy.close()


def test_no_showcase_folder_imports_nothing(tmp_path: Path) -> None:
    empty = database(tmp_path / "empty.db")
    try:
        assert import_showcase(empty, tmp_path / "m", tmp_path / "missing") == 0
        assert showcase_rows(empty, tmp_path / "missing") == []
    finally:
        empty.close()


@pytest.mark.parametrize(
    ("limit", "dropped"),
    [(200_000, []), (60_000, ["music"]), (30_000, ["music", "narration_audio"])],
)
def test_an_oversized_export_drops_music_then_audio(source, tmp_path: Path, limit, dropped):
    connection, media = source
    out = tmp_path / "showcase"
    result = export_showcase(connection, [("b-7f3k2q", None)], media, out, max_bytes=limit)
    assert result.dropped == dropped and result.total_bytes <= limit
    kinds = {
        a["kind"] for a in json.loads((out / "battles" / "b-7f3k2q.json").read_text())["assets"]
    }
    assert not kinds & set(dropped) and {"sprite", "battlefield"} <= kinds


def test_an_unfinished_or_unknown_battle_is_not_exported(source, tmp_path: Path) -> None:
    connection, media = source
    with pytest.raises(ValueError, match="b-nope"):
        export_showcase(connection, [("b-nope", None)], media, tmp_path / "showcase")


def test_the_route_lists_showcase_battles_in_order(source, tmp_path: Path) -> None:
    connection, media = source
    out = tmp_path / "showcase"
    export_showcase(connection, [("b-7f3k2q", "Grizzly bear vs 6 Gray wolves")], media, out)
    db_path = tmp_path / "app.db"
    database(db_path).close()

    async def same_file() -> AsyncIterator[sqlite3.Connection]:
        live = connect(db_path)
        try:
            yield live
        finally:
            live.close()

    app = create_app(frontend_dist=tmp_path / "missing", showcase_dir=None)
    app.dependency_overrides[get_db] = same_file
    app.dependency_overrides[get_showcase_dir] = lambda: out
    with TestClient(app) as client:
        assert client.get("/api/battles", params={"showcase": "true"}).json() == []
        load = database(db_path)
        try:
            import_showcase(load, tmp_path / "m", out)
        finally:
            load.close()
        reply = client.get("/api/battles", params={"showcase": "true"})
        assert reply.json() == [{"battle_id": "b-7f3k2q", "title": "Grizzly bear vs 6 Gray wolves"}]
        assert client.get("/api/battles").status_code == 404


def test_startup_loads_the_showcase_and_warns_about_an_empty_knowledge_base(
    source, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    connection, media = source
    out = tmp_path / "showcase"
    export_showcase(connection, [("b-7f3k2q", None)], media, out)
    data = tmp_path / "data"
    settings = Settings(_env_file=None, provider_mode="live", data_dir=data)  # never reads .env
    app = create_app(settings, frontend_dist=tmp_path / "missing", showcase_dir=out)
    with TestClient(app):
        pass
    assert "npm run ingest" in capsys.readouterr().out
    loaded = connect(data / "app.db")
    try:
        assert saved.get(loaded, "b-7f3k2q") is not None
    finally:
        loaded.close()
