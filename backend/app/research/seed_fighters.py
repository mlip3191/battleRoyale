"""The 30 seed fighters, read from data/seed/fighters.yaml, and their hand-verified sheets."""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import REPO_ROOT
from app.models.stats import StatSheet

SEED_LIST_PATH = REPO_ROOT / "data" / "seed" / "fighters.yaml"
SEED_SHEETS_DIR = REPO_ROOT / "data" / "seed" / "fighters"


@dataclass(frozen=True)
class SeedFighter:
    """One row of the seed list in docs/research.md."""

    id: str
    display_name: str
    variant: str
    category: str
    body: str
    habitat: str
    article: str


# Read the seed list.
def load_seed_fighters(path: Path = SEED_LIST_PATH) -> list[SeedFighter]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [SeedFighter(**row) for row in data["fighters"]]


# Turn a fighter name into its id: "Grizzly Bear" -> "grizzly-bear".
def fighter_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# The hand-verified sheet for a fighter name, or None when there is no seed sheet for it.
# Gunnar's G04 get_stat_sheet will wrap or replace this lookup.
def find_seed_sheet(entity: str, sheets_dir: Path = SEED_SHEETS_DIR) -> StatSheet | None:
    slug = fighter_slug(entity)
    path = sheets_dir / f"{slug}.json"
    if not slug or not path.is_file():
        return None
    return StatSheet.model_validate_json(path.read_text(encoding="utf-8"))
