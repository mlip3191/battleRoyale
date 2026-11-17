"""Check every stored battle for traceability and print a summary (G06, #40).

From the repo root:
  uv run --directory backend python scripts/trace_report.py
  uv run --directory backend python scripts/trace_report.py --db path/to/app.db

Each battle gets one line ("b-7f3k2q: 0 issues (...)") and every issue is listed under it.
Extracted quotes whose article isn't stored here are counted as unchecked, not as issues.
The footer gives the share of battles with no issues and how many quotes it was checked against.
Exits 1 when any battle has an issue, so it can gate a run, and 2 when --db names no file. The
benchmark (F07) uses the same check for its traceability column.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.connection import connect  # noqa: E402
from app.db.migrate import apply_migrations  # noqa: E402
from app.research.trace import TraceReport, trace_stored_battles, traceable_share  # noqa: E402


# The printed report: one line per battle, its issues indented, then the overall share.
def render(reports: list[TraceReport]) -> str:
    if not reports:
        return "No finished battles stored yet; nothing to check."
    lines = []
    for report in reports:
        lines.append(report.summary())
        lines += [f"  - {issue.where}: {issue.problem}" for issue in report.issues]
    share = traceable_share(reports)
    clean = sum(r.ok for r in reports)
    lines.append(f"\nTraceable: {clean} of {len(reports)} battles ({round((share or 0) * 100)}%).")
    # What the share rests on: a quote whose article isn't stored here can't fail (#353 review).
    checked = sum(r.quotes_checked for r in reports)
    unchecked = sum(r.quotes_unchecked for r in reports)
    lines.append(
        f"Extracted quotes checked against stored articles: {checked}; "
        f"not checkable here: {unchecked}."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--db", type=Path, default=None, help="database file (default: the app's)")
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
    print(render(reports))
    return 1 if any(not r.ok for r in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
