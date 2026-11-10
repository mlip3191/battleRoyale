"""Open the app's SQLite database with WAL mode, foreign keys, and sqlite-vec loaded."""

import sqlite3
from pathlib import Path

import sqlite_vec

from app.config import get_settings


# Open the database, creating its folder if needed; defaults to data/app.db.
def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or get_settings().data_dir / "app.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection
