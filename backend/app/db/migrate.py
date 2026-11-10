"""Apply the numbered SQL files in migrations/ once each, in order."""

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


# Apply every migration not yet recorded and return the names applied now.
def apply_migrations(connection: sqlite3.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    connection.commit()
    done = {row[0] for row in connection.execute("SELECT name FROM schema_migrations")}
    pending = [path for path in sorted(directory.glob("*.sql")) if path.name not in done]
    for path in pending:
        _apply_one(connection, path)
    return [path.name for path in pending]


# Run one file and record it in a single transaction, so a failure leaves nothing behind.
def _apply_one(connection: sqlite3.Connection, path: Path) -> None:
    name = path.name.replace("'", "''")
    script = (
        f"BEGIN;\n{path.read_text(encoding='utf-8')}\n"
        f"INSERT INTO schema_migrations (name) VALUES ('{name}');\nCOMMIT;"
    )
    try:
        connection.executescript(script)
    except sqlite3.Error:
        connection.rollback()
        raise
