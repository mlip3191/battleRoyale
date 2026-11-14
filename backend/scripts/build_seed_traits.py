"""Write data/seed/seed-traits.csv: the team trait dataset to upload to Hugging Face (G02).

It holds the PanTHERIA and AnimalTraits rows for the seed fighters only, matched by the
scientific name in each fighter's saved Wikidata entity. Run the seed ingest first, so the trait
files and Wikidata entities are saved in data/kb/. From the backend folder:
  uv run python -m scripts.build_seed_traits
Then upload the file to the team dataset on Hugging Face (see docs/research.md).
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import REPO_ROOT, get_settings  # noqa: E402
from app.research.seed_fighters import load_seed_fighters  # noqa: E402
from app.research.traits import load_original_tables, taxon_name, team_csv, team_rows  # noqa: E402

OUT_PATH = REPO_ROOT / "data" / "seed" / "seed-traits.csv"


# Each seed fighter's scientific name, from its saved Wikidata entity (None if not saved).
def scientific_names(kb_dir: Path) -> dict[str, str | None]:
    names: dict[str, str | None] = {}
    for fighter in load_seed_fighters():
        path = kb_dir / fighter.id / "wikidata.json"
        entity = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        names[fighter.id] = taxon_name(entity)
    return names


async def main() -> int:
    kb_dir = get_settings().data_dir / "kb"
    async with httpx.AsyncClient(timeout=60.0) as client:
        tables, failures = await load_original_tables(client, kb_dir)
    if failures:
        print("Could not load:", *failures, sep="\n  ")
        return 1
    names = scientific_names(kb_dir)
    rows = team_rows(tables, {name for name in names.values() if name})
    OUT_PATH.write_text(team_csv(rows), encoding="utf-8", newline="\n")
    matched = {row["scientific_name"] for row in rows}
    print(f"Wrote {len(rows)} rows for {len(matched)} species to {OUT_PATH}.")
    for fighter_id, name in names.items():
        if name not in matched:
            print(f"No trait rows: {fighter_id} ({name or 'no scientific name saved'})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
