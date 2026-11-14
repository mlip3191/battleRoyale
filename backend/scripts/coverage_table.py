"""Print a coverage table for G09 (#39): how each stat on a fighter's sheet was set.

A hand-verified seed sheet is used when one exists; otherwise the sheet is built from stored
facts and model extraction (G04), exactly as a battle would, but not saved. From the backend
folder (run the seed ingest first, so the knowledge base exists):
  uv run python -m scripts.coverage_table                   # uses PROVIDER_MODE from .env
  uv run python -m scripts.coverage_table toaster bulldozer
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.connection import connect  # noqa: E402
from app.db.migrate import apply_migrations  # noqa: E402
from app.models.stats import StatSheet, StatValue  # noqa: E402
from app.providers.registry import get_provider  # noqa: E402
from app.research.extract import build_sheet_with_evidence  # noqa: E402
from app.research.seed_fighters import find_seed_sheet, load_seed_fighters  # noqa: E402
from app.research.statsheet import profile_from_seed  # noqa: E402

DEFAULT_FIGHTERS = ("toaster", "bulldozer")
LABELS = {
    "hand_verified": "sourced",
    "extracted": "sourced",
    "derived": "derived",
    "category_default": "estimate",
    "assumption": "assumption",
}


# One stat as a table row: the value, how it was set, and the plain-English label.
def row(name: str, stat: StatValue) -> str:
    return f"| {name} | {stat.value:g} {stat.unit} | {stat.method} | {LABELS[stat.method]} |"


# The sheet a battle would use for a seed-list fighter, without saving it.
async def sheet_for(fighter_id: str) -> tuple[StatSheet, str]:
    seed = find_seed_sheet(fighter_id)
    if seed is not None:
        return seed, "hand-verified seed sheet"
    fighter = next(f for f in load_seed_fighters() if f.id == fighter_id)
    providers = (get_provider("chat"), get_provider("embedder"), get_provider("reranker"))
    connection = connect()
    try:
        apply_migrations(connection)
        sheet = await build_sheet_with_evidence(connection, providers, profile_from_seed(fighter))
    finally:
        connection.close()
    return sheet, "built from stored facts and extraction"


async def main(fighter_ids: list[str]) -> int:
    for fighter_id in fighter_ids:
        sheet, how = await sheet_for(fighter_id)
        counts = {label: 0 for label in dict.fromkeys(LABELS.values())}
        print(f"\n**{sheet.display_name}** ({sheet.category} / {sheet.body}, {how})\n")
        print("| stat | value | method | label |\n|---|---|---|---|")
        for name, stat in sheet.stats.items():
            print(row(str(name), stat))
            counts[LABELS[stat.method]] += 1
        print("\n" + ", ".join(f"{label}: {n}" for label, n in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:] or list(DEFAULT_FIGHTERS))))
