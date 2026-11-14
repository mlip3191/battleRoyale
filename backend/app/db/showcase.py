"""Showcase battles (G08, #47): saved battles shipped in data/showcase/ for a fresh clone.

The export copies chosen finished battles and the media they use out of the app database and
data/media/; the import loads them back into an empty database at startup, with no endpoint
calls. data/showcase/ holds manifest.json (ids and titles, in home-page order), one JSON file
per battle under battles/, and the media files under media/ with the same paths as data/media/.
"""

import json
import logging
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.config import REPO_ROOT
from app.db import battles as saved
from app.models.api import ShowcaseBattle
from app.models.battle import BattleRecord

logger = logging.getLogger(__name__)

SHOWCASE_DIR = REPO_ROOT / "data" / "showcase"
MAX_SHOWCASE_BYTES = 20 * 1024 * 1024  # the committed folder stays small (G08)
# Media dropped first when the export is too big: music, then narration audio. Sprites and
# battlefields always stay, because the battle can't be shown without them.
DROP_ORDER = ("music", "narration_audio")
MEDIA_PREFIX = "/media/"


@dataclass
class ExportResult:
    """What an export wrote, and which kinds of media it had to leave out to fit."""

    battles: int = 0
    total_bytes: int = 0
    dropped: list[str] = field(default_factory=list)


# The matchup title shown on the home page, from the sheets' display names.
def default_title(record: BattleRecord) -> str:
    names = [sheet.display_name for sheet in record.stat_sheets]
    return " vs ".join(names) if names else record.battle_id


# The media file an asset points at, or None for a URL outside /media/.
def media_path(url: str, media_dir: Path) -> Path | None:
    if not url.startswith(MEDIA_PREFIX):
        return None
    path = (media_dir / url.removeprefix(MEDIA_PREFIX)).resolve()
    return path if path.is_relative_to(media_dir.resolve()) else None


# A copy of the record without the given kinds of media.
def _without(record: BattleRecord, kinds: set[str]) -> BattleRecord:
    return record.model_copy(update={"assets": [a for a in record.assets if a.kind not in kinds]})


# Bytes the folder would take: each record's JSON plus each media file it points at, once.
def _size(records: list[BattleRecord], media_dir: Path) -> int:
    files = {
        path
        for record in records
        for asset in record.assets
        if (path := media_path(asset.url, media_dir)) is not None and path.is_file()
    }
    records_bytes = sum(len(r.model_dump_json(indent=2).encode("utf-8")) for r in records)
    return records_bytes + sum(path.stat().st_size for path in files)


# Copy the chosen finished battles and their media into out_dir, replacing what was there.
def export_showcase(
    connection: sqlite3.Connection,
    entries: list[tuple[str, str | None]],
    media_dir: Path,
    out_dir: Path = SHOWCASE_DIR,
    max_bytes: int = MAX_SHOWCASE_BYTES,
) -> ExportResult:
    records: list[BattleRecord] = []
    for battle_id, _ in entries:
        record = saved.get(connection, battle_id)
        if record is None or record.status != "done":
            raise ValueError(f"{battle_id} is not a finished battle in this database")
        records.append(record)
    result = ExportResult()
    for kind in DROP_ORDER:
        if _size(records, media_dir) <= max_bytes:
            break
        records = [_without(r, set(result.dropped) | {kind}) for r in records]
        result.dropped.append(kind)
    result.total_bytes = _size(records, media_dir)
    if result.total_bytes > max_bytes:
        raise ValueError(f"showcase is {result.total_bytes} bytes even without music and audio")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "battles").mkdir(parents=True)
    manifest = []
    for record, (battle_id, title) in zip(records, entries, strict=True):
        (out_dir / "battles" / f"{battle_id}.json").write_text(
            record.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        for asset in record.assets:
            source = media_path(asset.url, media_dir)
            if source is not None and source.is_file():
                target = out_dir / "media" / asset.url.removeprefix(MEDIA_PREFIX)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        manifest.append({"battle_id": battle_id, "title": title or default_title(record)})
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    result.battles = len(records)
    return result


# The showcase rows in the folder, in home-page order (empty when there is no showcase).
def load_manifest(showcase_dir: Path = SHOWCASE_DIR) -> list[ShowcaseBattle]:
    path = showcase_dir / "manifest.json"
    if not path.is_file():
        return []
    return [ShowcaseBattle.model_validate(row) for row in json.loads(path.read_text("utf-8"))]


# Load the showcase into an empty database and copy its media; returns how many were loaded.
# A database that already has battles is left alone, so nothing a user made is replaced.
def import_showcase(
    connection: sqlite3.Connection, media_dir: Path, showcase_dir: Path = SHOWCASE_DIR
) -> int:
    rows = load_manifest(showcase_dir)
    if not rows or connection.execute("SELECT 1 FROM battles LIMIT 1").fetchone():
        return 0
    for row in rows:
        text = (showcase_dir / "battles" / f"{row.battle_id}.json").read_text("utf-8")
        record = BattleRecord.model_validate_json(text)
        saved.save(connection, record, cache_key=None)
        for asset in record.assets:
            source = showcase_dir / "media" / asset.url.removeprefix(MEDIA_PREFIX)
            target = media_path(asset.url, media_dir)
            if target is not None and source.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    logger.info("Loaded %d showcase battles.", len(rows))
    return len(rows)


# The showcase rows whose battles are in the database, in manifest order.
def showcase_rows(
    connection: sqlite3.Connection, showcase_dir: Path = SHOWCASE_DIR
) -> list[ShowcaseBattle]:
    return [row for row in load_manifest(showcase_dir) if saved.get(connection, row.battle_id)]
