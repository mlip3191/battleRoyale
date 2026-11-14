"""Open the app's SQLite database with WAL mode, foreign keys, and sqlite-vec loaded."""

import sqlite3
import time
from pathlib import Path

import sqlite_vec

from app.config import get_settings

BUSY_TIMEOUT_MS = 5000
WAL_RETRY_S = 0.02


# Open the database, creating its folder if needed; defaults to data/app.db.
def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or get_settings().data_dir / "app.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    _switch_to_wal(connection)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


# Turn on WAL mode, retrying briefly: on a brand-new file several openers race for the lock it
# needs, and SQLite answers "locked" at once instead of waiting (#170). The mode is stored in
# the file, so once one opener wins, the others' switch succeeds immediately.
def _switch_to_wal(connection: sqlite3.Connection) -> None:
    deadline = time.monotonic() + BUSY_TIMEOUT_MS / 1000
    while True:
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as error:
            if "locked" not in str(error) or time.monotonic() >= deadline:
                raise
            time.sleep(WAL_RETRY_S)
