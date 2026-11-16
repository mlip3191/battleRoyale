"""Run the benchmark and write docs/benchmark-results.md.

From the repo root:
  uv run --directory backend python scripts/run_benchmark.py --mock
      CI-safe: three matchups from test fixtures, nothing is written unless --output is given.
  uv run --directory backend python scripts/run_benchmark.py --live --sheets seed
  uv run --directory backend python scripts/run_benchmark.py --live --sheets seed --tuning-only
  uv run --directory backend python scripts/run_benchmark.py --live --sheets research
      The real run: data/benchmark/matchups.yaml (tuning) and heldout.yaml (never tuned on).

The simulation itself uses no endpoints. `--sheets research` builds every sheet with the research
pipeline (G04) and so uses the providers set in `.env` (PROVIDER_MODE=mock needs none, but then
the sheets are mock output, not a real result). It ignores the hand-verified seed sheets.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db.connection import connect  # noqa: E402
from app.db.migrate import apply_migrations  # noqa: E402
from app.providers.registry import ProviderConfigError, get_provider  # noqa: E402
from app.research.benchmark_sheets import research_sheets  # noqa: E402
from app.research.trace import trace_stored_battles, traceable_share  # noqa: E402
from app.simulation import benchmark as bm  # noqa: E402


def build_research_sheets(entries: list[bm.Entry]) -> bm.SheetSource:
    """Run the research pipeline for every fighter in the benchmark (can take a while, and live
    providers cost calls)."""
    try:
        providers = (get_provider("chat"), get_provider("embedder"), get_provider("reranker"))
    except ProviderConfigError as error:
        raise bm.BenchmarkError(f"the providers are not set up: {error}") from error
    connection = connect()
    try:
        apply_migrations(connection)
        if connection.execute("SELECT 1 FROM chunks LIMIT 1").fetchone() is None:
            raise bm.BenchmarkError(
                "the knowledge base is empty, so every sheet would be built from defaults: "
                "run `npm run ingest` first"
            )
        return asyncio.run(research_sheets(entries, connection, providers))
    finally:
        connection.close()


def add_traceability(report: bm.RunReport, mock: bool) -> None:
    """Fill the traceability column from G06's check of every stored battle (trace_report.py)."""
    if mock:
        report.notes.append(
            "Traceability (G06) isn't checked in mock mode; it needs stored battles."
        )
        return
    connection = connect()
    try:
        apply_migrations(connection)
        traced = trace_stored_battles(connection)
    finally:
        connection.close()
    report.traceability = traceable_share(traced)
    clean = sum(t.ok for t in traced)
    checked = sum(t.quotes_checked for t in traced)
    unchecked = sum(t.quotes_unchecked for t in traced)
    report.notes.append(
        f"Traceability (G06): {clean} of {len(traced)} stored battles have no issues; "
        f"{checked} extracted quotes were checked against stored articles and "
        f"{unchecked} could not be checked here. Run `scripts/trace_report.py` for details."
        if traced
        else "Traceability (G06): no finished battles stored yet, so it shows n/a."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock", action="store_true", help="use test fixtures (CI-safe)")
    mode.add_argument("--live", action="store_true", help="use the real benchmark set")
    parser.add_argument("--sheets", choices=["seed", "research"], default="seed")
    parser.add_argument("--runs", type=int, default=None, help="simulation runs per matchup")
    parser.add_argument("--matchups", type=Path, default=None)
    parser.add_argument("--heldout", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None, help="results file to update")
    parser.add_argument(
        "--tuning-only", action="store_true",
        help="do not run or show the held-out set (use while changing constants)",
    )  # fmt: skip
    args = parser.parse_args(argv)

    try:
        if args.mock:
            tuning = bm.load_entries(args.matchups or bm.MOCK_DIR / "matchups.yaml", False)
            held = bm.load_entries(args.heldout or bm.MOCK_DIR / "heldout.yaml", True)
            sheets, label = bm.mock_sheets(), "mock"
            runs, output = args.runs or 200, args.output  # mock never touches docs/ by default
        else:
            tuning = bm.load_entries(args.matchups or bm.BENCHMARK_DIR / "matchups.yaml", False)
            held = bm.load_entries(args.heldout or bm.BENCHMARK_DIR / "heldout.yaml", True)
            sheets = (
                bm.seed_sheets()
                if args.sheets == "seed"
                else build_research_sheets([*tuning, *held])
            )
            label = args.sheets
            runs, output = args.runs or get_settings().sim_runs, args.output or bm.RESULTS_FILE
        report = bm.run_benchmark(sheets, label, tuning, held, runs, args.tuning_only)
        add_traceability(report, args.mock)
    except bm.BenchmarkError as error:
        print(f"Cannot run the benchmark: {error}", file=sys.stderr)
        return 2

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # reports contain dashes; Windows consoles may not
    print(bm.render_run(report))
    if output is not None:
        bm.write_report(output, report)
        print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
