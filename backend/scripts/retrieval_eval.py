"""Score retrieval on tests/fixtures/retrieval_cases.yaml (G03, #34), and time on-demand ingest.

A case is a hit when its phrase is in one of the 5 passages evidence_for returns. Run the seed
ingest first so the knowledge base exists. From the backend folder:
  uv run python -m scripts.retrieval_eval                      # uses PROVIDER_MODE from .env
  uv run python -m scripts.retrieval_eval --on-demand moose Moose
The second form ingests one fighter off the seed list (its id, then its article title), prints
how long it took against the 30 s limit, and shows its mass evidence. Exits 1 below 80% hit@5.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.connection import connect  # noqa: E402
from app.db.migrate import apply_migrations  # noqa: E402
from app.models.stats import StatName  # noqa: E402
from app.providers.registry import get_provider  # noqa: E402
from app.research.evidence_check import normalize_text  # noqa: E402
from app.research.ingest import ON_DEMAND_BUDGET_S, ingest_on_demand  # noqa: E402
from app.research.retrieve import evidence_for  # noqa: E402

CASES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "retrieval_cases.yaml"
TARGET = 0.8
DOWNLOAD_TIMEOUT_S = 15.0


# Print one row per case and the hit@5 score; True when it meets the target.
async def score() -> bool:
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    embedder, reranker = get_provider("embedder"), get_provider("reranker")
    connection = connect()
    hits = 0
    try:
        apply_migrations(connection)
        print("| fighter | stat | phrase | hit | rank |\n|---|---|---|---|---|")
        for case in cases:
            stat = StatName(case["stat"])
            found = await evidence_for(connection, embedder, reranker, case["fighter_id"], stat)
            phrase = normalize_text(case["phrase"])
            ranks = [i for i, p in enumerate(found, 1) if phrase in normalize_text(p.text)]
            hits += bool(ranks)
            rank = str(ranks[0]) if ranks else "-"
            mark = "yes" if ranks else "**no**"
            print(f"| {case['fighter_id']} | {stat} | {case['phrase']} | {mark} | {rank} |")
    finally:
        connection.close()
    share = hits / len(cases)
    print(f"\nhit@5: {hits}/{len(cases)} = {share:.0%} (target {TARGET:.0%})")
    return share >= TARGET


# Ingest one fighter off the seed list on demand, report the time, and show its mass evidence.
async def on_demand(fighter_id: str, title: str) -> bool:
    parser, embedder = get_provider("doc_parser"), get_provider("embedder")
    connection = connect()
    try:
        apply_migrations(connection)
        # Always fetches and parses again; storing replaces any earlier copy of the article.
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_S) as client:
            start = time.perf_counter()
            stored = await ingest_on_demand(connection, client, parser, embedder, fighter_id, title)
            seconds = time.perf_counter() - start
        print(
            f"On-demand ingest of {title!r}: {'stored' if stored else 'FAILED'} in "
            f"{seconds:.1f} s (limit {ON_DEMAND_BUDGET_S:.0f} s)"
        )
        if stored:
            found = await evidence_for(
                connection, embedder, get_provider("reranker"), fighter_id, StatName.MASS
            )
            for rank, passage in enumerate(found, 1):
                print(f"{rank}. {passage.text[:160]!r}")
    finally:
        connection.close()
    return stored


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--on-demand", nargs=2, metavar=("FIGHTER_ID", "TITLE"))
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.on_demand:
        return 0 if asyncio.run(on_demand(*args.on_demand)) else 1
    return 0 if asyncio.run(score()) else 1


if __name__ == "__main__":
    sys.exit(main())
