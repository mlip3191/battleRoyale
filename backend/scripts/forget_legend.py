"""List or forget legends cached by earlier battles, so a bad one is modeled again (#324).

A legend that isn't in data/seed/mythical.yaml is modeled from its Wikipedia article the first
time someone fights it, and its sheet is saved and reused. If that sheet turned out wrong,
forget it here; the next battle with that name looks it up again.

From the repo root:
  uv run --directory backend python scripts/forget_legend.py --list
  uv run --directory backend python scripts/forget_legend.py hydra

Seed fighters and the creatures in mythical.yaml are never cached legends, so they're refused.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.connection import connect  # noqa: E402
from app.db.migrate import apply_migrations  # noqa: E402
from app.research.sheet_store import cached_legends, forget_legend  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("name", nargs="?", help="the legend to forget, e.g. hydra")
    parser.add_argument("--list", action="store_true", help="show the cached legends")
    args = parser.parse_args(argv)
    if not args.list and not args.name:
        parser.error("give a legend's name, or --list")
    connection = connect()
    try:
        apply_migrations(connection)
        if args.list:
            legends = cached_legends(connection)
            for fighter_id, display_name, versions in legends:
                print(f"{fighter_id}: {display_name} ({versions} saved)")
            print(f"{len(legends)} cached legends.")
            return 0
        try:
            removed = forget_legend(connection, args.name)
        except ValueError as error:
            print(f"Not forgotten: {error}.", file=sys.stderr)
            return 2
    finally:
        connection.close()
    if removed:
        print(f"Forgot {args.name!r} ({removed} saved). The next battle models it again.")
    else:
        print(f"No cached legend called {args.name!r}; nothing to forget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
