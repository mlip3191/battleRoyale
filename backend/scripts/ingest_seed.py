"""Build the knowledge base for the seed fighters and print a summary.

From the backend folder:
  uv run python -m scripts.ingest_seed            # uses PROVIDER_MODE from .env
  uv run python -m scripts.ingest_seed --live     # forces the live course services
  uv run python -m scripts.ingest_seed --only horse duck

Re-running skips articles already stored at the same revision. A mock run and a live run use
different vector sizes, so switching between them rebuilds the stored passages.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db.connection import connect  # noqa: E402
from app.db.migrate import apply_migrations  # noqa: E402
from app.providers.registry import get_provider  # noqa: E402
from app.research.ingest import IngestSummary, ingest_all  # noqa: E402
from app.research.seed_fighters import load_seed_fighters  # noqa: E402

DOWNLOAD_TIMEOUT_S = 60.0


# Print the summary table the G02 acceptance criteria ask for.
def print_summary(summary: IngestSummary, seconds: float) -> None:
    print("| fighters | documents | parsed | chunks | facts | failures |")
    print("|---|---|---|---|---|---|")
    print(
        f"| {summary.fighters} | {summary.documents} | {summary.parsed} | {summary.chunks} "
        f"| {summary.facts} | {len(summary.failures)} |"
    )
    print(f"Finished in {seconds:.0f} s.")
    for failure in summary.failures:
        print(f"Failed: {failure}")


# Run the ingest with the configured providers.
async def main(live: bool, only: list[str]) -> int:
    settings = get_settings()
    if live:
        settings = settings.model_copy(update={"provider_mode": "live"})
    fighters = load_seed_fighters()
    if only:
        fighters = [fighter for fighter in fighters if fighter.id in only]
    connection = connect(settings.data_dir / "app.db")
    apply_migrations(connection)
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_S) as client:
        summary = await ingest_all(
            connection,
            client,
            get_provider("doc_parser", settings),
            get_provider("embedder", settings),
            fighters,
            settings.data_dir / "kb",
        )
    connection.close()
    print_summary(summary, time.perf_counter() - started)
    return 1 if summary.failures else 0


if __name__ == "__main__":
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--live", action="store_true", help="use the live course services")
    arguments.add_argument("--only", nargs="*", default=[], help="fighter ids to ingest")
    options = arguments.parse_args()
    sys.exit(asyncio.run(main(options.live, options.only)))
