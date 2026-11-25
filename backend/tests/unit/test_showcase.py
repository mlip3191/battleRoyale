"""G08 (#47): showcase battles export to data/showcase/, load at startup (missing ones only),
and list on GET /api/battles?showcase=true."""

import json
import logging
import sqlite3
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.battles import get_db, get_showcase_dir
from app.config import Settings
from app.db import battles as saved
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.db.showcase import (
    MAX_SHOWCASE_BYTES,
    export_showcase,
    import_showcase,
    load_manifest,
    showcase_rows,
)
from app.main import PLACEHOLDER_VOICE, _startup, create_app
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


# A setup that already has its own battles still gets the showcase, and keeps its own (#47).
def test_import_adds_the_missing_showcase_battles_and_keeps_the_users_own(
    source, tmp_path: Path
) -> None:
    connection, media = source
    out = tmp_path / "showcase"
    export_showcase(connection, [("b-7f3k2q", None)], media, out)
    busy = database(tmp_path / "busy.db")
    try:
        saved.save(busy, record("b-mine"), cache_key=None)
        assert import_showcase(busy, tmp_path / "m", out) == 1
        assert saved.get(busy, "b-7f3k2q") is not None and saved.get(busy, "b-mine") is not None
        assert import_showcase(busy, tmp_path / "m", out) == 0  # the next start adds nothing
    finally:
        busy.close()


# A showcase battle the database already holds is never replaced, even if it was changed.
def test_import_never_replaces_a_battle_with_the_same_id(source, tmp_path: Path) -> None:
    connection, media = source
    out = tmp_path / "showcase"
    export_showcase(connection, [("b-7f3k2q", None)], media, out)
    mine = record("b-7f3k2q").model_copy(update={"created_at": datetime(2020, 1, 1, tzinfo=UTC)})
    busy = database(tmp_path / "busy.db")
    try:
        saved.save(busy, mine, cache_key=None)
        assert import_showcase(busy, tmp_path / "m", out) == 0
        kept = saved.get(busy, "b-7f3k2q")
        assert kept is not None and kept.created_at == mine.created_at
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


# The logged messages that are about the announcer voice id.
def voice_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if "ANNOUNCER_VOICE_ID" in r.getMessage()]


# #45: live mode warns once at startup when the voice id is blank or a placeholder.
@pytest.mark.parametrize(
    ("mode", "voice_id", "warns"),
    [
        ("live", "replace-me", True),
        ("live", "", True),
        ("live", "default", False),
        ("mock", "replace-me", False),
    ],
)
def test_startup_warns_about_a_placeholder_voice_id_in_live_mode(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, mode: str, voice_id: str, warns: bool
) -> None:
    settings = Settings(
        _env_file=None, provider_mode=mode, data_dir=tmp_path, announcer_voice_id=voice_id
    )
    with caplog.at_level(logging.WARNING, logger="app.main"):
        _startup(settings, None)
    warnings = voice_warnings(caplog)
    assert warnings == ([PLACEHOLDER_VOICE] if warns else [])


# The voice warning still fires when the database step fails (data_dir is a file, not a folder).
def test_the_voice_warning_fires_even_when_the_database_step_fails(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    not_a_folder = tmp_path / "file"
    not_a_folder.write_text("x")
    settings = Settings(
        _env_file=None, provider_mode="live", data_dir=not_a_folder, announcer_voice_id=""
    )
    with caplog.at_level(logging.WARNING, logger="app.main"):
        _startup(settings, None)
    assert voice_warnings(caplog) == [PLACEHOLDER_VOICE]
    assert "Startup checks skipped" in caplog.text


def test_a_manifest_id_that_points_outside_the_folder_is_refused(source, tmp_path: Path) -> None:
    connection, media = source
    out = tmp_path / "showcase"
    export_showcase(connection, [("b-7f3k2q", None)], media, out)
    (out / "manifest.json").write_text('[{"battle_id": "../escape", "title": "x"}]')
    fresh = database(tmp_path / "fresh.db")
    try:
        with pytest.raises(ValueError, match="plain id"):
            import_showcase(fresh, tmp_path / "m", out)
    finally:
        fresh.close()


def test_a_broken_battle_file_leaves_the_database_empty_not_half_loaded(
    source, tmp_path: Path
) -> None:
    connection, media = source
    out = tmp_path / "showcase"
    export_showcase(connection, [("b-7f3k2q", None)], media, out)
    manifest = [{"battle_id": "b-7f3k2q", "title": "One"}, {"battle_id": "b-gone", "title": "Two"}]
    (out / "manifest.json").write_text(json.dumps(manifest))
    fresh = database(tmp_path / "fresh.db")
    try:
        with pytest.raises(ValueError, match="b-gone.json is missing"):
            import_showcase(fresh, tmp_path / "m", out)
        assert fresh.execute("SELECT COUNT(*) FROM battles").fetchone()[0] == 0
    finally:
        fresh.close()


# The committed showcase (data/showcase/) loads whole into an empty database, media included.
def test_the_committed_showcase_loads_into_an_empty_database(tmp_path: Path) -> None:
    connection = database(tmp_path / "app.db")
    media = tmp_path / "media"
    rows = load_manifest()
    assert rows and import_showcase(connection, media) == len(rows)
    assert showcase_rows(connection) == rows
    for row in rows:
        battle = saved.get(connection, row.battle_id)
        assert battle is not None and battle.status == "done"
        for asset in battle.assets:
            assert (media / asset.url.removeprefix("/media/")).is_file(), asset.url
    connection.close()


# Mike's G08 checks on the dragon battle: every dragon stat is an assumption, the lore names both
# analogs, the script says "according to legend", and the tank only rams or crushes.
def test_the_showcase_dragon_battle_plays_by_the_legend_rules() -> None:
    showcase = Path(__file__).parents[3] / "data" / "showcase" / "battles"
    battles = [
        BattleRecord.model_validate_json(p.read_text("utf-8")) for p in showcase.glob("*.json")
    ]
    dragon = next(b for b in battles if b.stat_sheets[0].display_name == "Dragon")
    sheet, tank = dragon.stat_sheets
    assert all(stat.method == "assumption" for stat in sheet.stats.values())
    assert sheet.lore is not None and sheet.lore.body_analog and sheet.lore.size_analog
    assert "according to legend" in dragon.model_dump_json().lower()
    assert set(tank.weapons) <= {"ramming", "crushing"}
    tank_moves = {
        e.text_hint
        for e in dragon.result.representative_log
        if e.side == 1 and e.type in ("hit", "miss")
    }
    assert tank_moves and all(m.split()[:1] in (["ram"], ["crush"]) for m in tank_moves)


# #546: every committed showcase battle keeps its announcer voice and the folder stays under
# the cap, which is 30 MB because the narration is uncompressed WAV.
def test_the_committed_showcase_has_the_announcer_voice_and_fits_the_cap() -> None:
    showcase = Path(__file__).parents[3] / "data" / "showcase"
    for row in load_manifest(showcase):
        battle = BattleRecord.model_validate_json(
            (showcase / "battles" / f"{row.battle_id}.json").read_text("utf-8")
        )
        stages = {s.stage: s.status for s in battle.stages}
        assert stages["script"] == "done" and stages["audio"] == "done", row.title
        clips = [a for a in battle.assets if a.kind == "narration_audio"]
        assert clips, row.title
        assert all(clip.line_times_s for clip in clips), row.title  # the announcer stays in sync
    size = sum(p.stat().st_size for p in showcase.rglob("*") if p.is_file())
    assert size <= MAX_SHOWCASE_BYTES
