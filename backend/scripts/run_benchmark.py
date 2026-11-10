"""Run the benchmark and write docs/benchmark-results.md.

From the repo root:
  uv run --directory backend python scripts/run_benchmark.py --mock
      CI-safe: three matchups from test fixtures, nothing is written unless --output is given.
  uv run --directory backend python scripts/run_benchmark.py --live --sheets seed
  uv run --directory backend python scripts/run_benchmark.py --live --sheets seed --tuning-only
  uv run --directory backend python scripts/run_benchmark.py --live --sheets research
      The real run: data/benchmark/matchups.yaml (tuning) and heldout.yaml (never tuned on).

The simulation itself uses no endpoints; only `--sheets research` would (task G04).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.simulation import benchmark as bm  # noqa: E402


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
            sheets = bm.seed_sheets() if args.sheets == "seed" else bm.research_sheets()
            label = args.sheets
            runs, output = args.runs or get_settings().sim_runs, args.output or bm.RESULTS_FILE
        report = bm.run_benchmark(sheets, label, tuning, held, runs, args.tuning_only)
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
