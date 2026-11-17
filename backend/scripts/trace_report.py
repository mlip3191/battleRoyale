"""Check every stored battle for traceability and print a summary (G06, #40).

From the repo root:
  uv run --directory backend python scripts/trace_report.py
  uv run --directory backend python scripts/trace_report.py --db path/to/app.db
  uv run --directory backend python scripts/trace_report.py --require-quotes

Each battle gets one line ("b-7f3k2q: 0 issues (...)") and every issue is listed under it.
Extracted quotes whose article isn't stored here are counted as unchecked, not as issues.
The footer gives the share of battles with no issues and how many quotes it was checked against.
Exits 1 when any battle has an issue, so it can gate a run, and 2 when --db names no file. The
benchmark (F07) uses the same check for its traceability column.

Strict mode (--require-quotes, #370) also exits 1 when any extracted quote couldn't be checked
because its article isn't stored here, so "traceable" means every quote was really verified.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.connection import connect  # noqa: E402
from app.db.migrate import apply_migrations  # noqa: E402
from app.research.trace import (  # noqa: E402
    TraceReport,
    trace_stored_battles,
    traceable,
    traceable_share,
)


# The printed report: one line per battle, its issues indented, then the overall share.
def render(reports: list[TraceReport], require_quotes: bool = False) -> str:
    if not reports:
        return "No finished battles stored yet; nothing to check."
    lines = []
    for report in reports:
        lines.append(report.summary())
        lines += [f"  - {issue.where}: {issue.problem}" for issue in report.issues]
    # In strict mode the footer uses the same rule as the exit code and the benchmark (#377 review).
    share = traceable_share(reports, require_quotes)
    clean = sum(traceable(r, require_quotes) for r in reports)
    lines.append(f"\nTraceable: {clean} of {len(reports)} battles ({round((share or 0) * 100)}%).")
    # What the share rests on: a quote whose article isn't stored here can't fail (#353 review).
    checked = sum(r.quotes_checked for r in reports)
    unchecked = sum(r.quotes_unchecked for r in reports)
    lines.append(
        f"Extracted quotes checked against stored articles: {checked}; "
        f"not checkable here: {unchecked}."
    )
    if require_quotes and unchecked:
        names = ", ".join(r.battle_id for r in reports if r.quotes_unchecked)
        noun = "quote" if unchecked == 1 else "quotes"
        lines.append(
            f"Strict mode (--require-quotes): {unchecked} {noun} couldn't be checked, in {names}. "
            "Store their articles (npm run ingest) and run again."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--db", type=Path, default=None, help="database file (default: the app's)")
    parser.add_argument(
        "--require-quotes",
        action="store_true",
        help="also fail when any extracted quote couldn't be checked against a stored article",
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.db is not None and not args.db.is_file():  # a typo must not create an empty database
        print(f"No database at {args.db}; nothing was checked.", file=sys.stderr)
        return 2
    connection = connect(args.db) if args.db else connect()
    try:
        apply_migrations(connection)
        reports = trace_stored_battles(connection)
    finally:
        connection.close()
    print(render(reports, args.require_quotes))
    return 1 if any(not traceable(r, args.require_quotes) for r in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
