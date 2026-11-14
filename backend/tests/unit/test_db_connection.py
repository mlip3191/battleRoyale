"""#170: several openers of a brand-new database wait for each other instead of failing."""

import sqlite3
import threading
from pathlib import Path

from app.db.connection import connect

OPENERS = 8
ROUNDS = 10  # a fresh file each round, so the WAL switch is contended every time


# Open one fresh database from many threads released at the same instant; return any errors.
def open_together(path: Path) -> list[Exception]:
    start = threading.Barrier(OPENERS)
    errors: list[Exception] = []
    lock = threading.Lock()

    def opener() -> None:
        start.wait()
        try:
            connection = connect(path)
            connection.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
            connection.commit()
            connection.close()
        except sqlite3.OperationalError as error:
            with lock:
                errors.append(error)

    threads = [threading.Thread(target=opener) for _ in range(OPENERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return errors


def test_simultaneous_opens_of_a_new_database_never_fail_with_locked(tmp_path: Path) -> None:
    errors = [e for i in range(ROUNDS) for e in open_together(tmp_path / f"fresh-{i}.db")]
    assert errors == [], f"{len(errors)} opens failed, e.g. {errors[0]}"


def test_a_connection_waits_rather_than_failing_when_busy(tmp_path: Path) -> None:
    connection = connect(tmp_path / "app.db")
    try:
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        connection.close()
