"""Print a coverage table for G09 (#39): how each stat on a fighter's sheet was set.

A hand-verified seed sheet is used when one exists; a creature in data/seed/mythical.yaml is
built from its analogs; another seed-list fighter is built from stored facts and model
extraction (G04); any other name is modeled as a legend from its Wikipedia article (live mode
only). Each is built exactly as a battle would, but not saved. From the backend folder (run the
seed ingest first, so the knowledge base exists):
  uv run python -m scripts.coverage_table                   # uses PROVIDER_MODE from .env
  uv run python -m scripts.coverage_table toaster bulldozer dragon hydra
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
from app.research.lore import lore_for  # noqa: E402
from app.research.mythical import build_mythical_sheet, find_creature  # noqa: E402
from app.research.seed_fighters import (  # noqa: E402
    fighter_slug,
    find_seed_sheet,
    load_seed_fighters,
)
from app.research.sheet_store import LEGEND_BUDGET_S, legend_client  # noqa: E402
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


# The sheet a battle would use for a name, without saving it, and how it was made; or no
# sheet and the reason.
async def sheet_for(name: str) -> tuple[StatSheet | None, str]:
    seed = find_seed_sheet(name)
    if seed is not None:
        return seed, "hand-verified seed sheet"
    creature = find_creature(name)
    if creature is not None:
        return build_mythical_sheet(creature), "built from its analogs in mythical.yaml"
    slug = fighter_slug(name)
    fighter = next((f for f in load_seed_fighters() if f.id == slug), None)
    if fighter is None:
        return await legend_sheet(name)
    providers = (get_provider("chat"), get_provider("embedder"), get_provider("reranker"))
    connection = connect()
    try:
        apply_migrations(connection)
        sheet = await build_sheet_with_evidence(connection, providers, profile_from_seed(fighter))
    finally:
        connection.close()
    return sheet, "built from stored facts and extraction"


# A legend that isn't in mythical.yaml, modeled from its Wikipedia article (live mode only).
async def legend_sheet(name: str) -> tuple[StatSheet | None, str]:
    client = legend_client()
    if client is None:
        return None, "not a seed fighter or a creature in the file; legends need live mode"
    try:
        async with client:
            lore = lore_for(name, client, get_provider("chat"))
            outcome = await asyncio.wait_for(lore, LEGEND_BUDGET_S)
    except TimeoutError:
        return None, f"ran past the {LEGEND_BUDGET_S:.0f} s legend limit"
    if outcome.creature is None:
        return None, "blocked as nonsense" if outcome.blocked else "a service was unavailable"
    try:
        return build_mythical_sheet(outcome.creature), "modeled as a legend from its article"
    except ValueError as error:
        return None, f"its sheet could not be built ({error})"


# Print one sheet's table, the count per label, and a legend's analogs and quote.
def print_sheet(sheet: StatSheet, how: str) -> None:
    counts = {label: 0 for label in dict.fromkeys(LABELS.values())}
    print(f"\n**{sheet.display_name}** ({sheet.category} / {sheet.body}, {how})\n")
    print("| stat | value | method | label |\n|---|---|---|---|")
    for name, stat in sheet.stats.items():
        print(row(str(name), stat))
        counts[LABELS[stat.method]] += 1
    print("\n" + ", ".join(f"{label}: {n}" for label, n in counts.items()))
    if sheet.lore is not None:
        lore = sheet.lore
        abilities = ", ".join(str(a) for a in lore.abilities) or "none"
        print(
            f"\nLore: body {lore.body_analog}, size {lore.size_analog or 'same as body'}, "
            f'abilities {abilities}, heads {lore.heads or 1}. Quote: "{lore.source.quote}"'
        )


async def main(names: list[str]) -> int:
    missed = 0
    for name in names:
        sheet, how = await sheet_for(name)
        if sheet is None:
            print(f"\n**{name}**: no sheet ({how}).")
            missed += 1
        else:
            print_sheet(sheet, how)
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:] or list(DEFAULT_FIGHTERS))))
