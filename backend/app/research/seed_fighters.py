"""The 30 seed fighters, read from data/seed/fighters.yaml."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import REPO_ROOT

SEED_LIST_PATH = REPO_ROOT / "data" / "seed" / "fighters.yaml"


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
