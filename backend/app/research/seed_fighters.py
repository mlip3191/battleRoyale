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


# Other spellings and word forms the seed lookup should treat as the sheet's word.
_ALIASES = {
    "grey": "gray",
    "wolves": "wolf",
    "ducks": "duck",
}


def _canonical_slug(name: str) -> str:
    """Slug a name, then map known alternate spellings to the sheet's word."""
    parts = [_ALIASES.get(part, part) for part in fighter_slug(name).split("-") if part]
    return "-".join(parts)


# The hand-verified sheet for a fighter, or None when there is no seed sheet for it.
# Live intake may put a descriptive word in variant ("grizzly" + "bear"), or drop it
# from both fields and leave it only in raw ("a grizzly bear" + entity "bear").
# Mock intake keeps the full name as entity and a label like "adult male" as variant.
# Try variant plus entity first, then the entity alone, then a unique seed sheet
# whose last slug part is the entity and whose other parts all appear in raw, so a
# variant-specific sheet wins when one exists and raw-only descriptors still match.
# Gunnar's G04 get_stat_sheet will wrap or replace this lookup.
# Only slugs of [a-z0-9-] are used, so this can only read files in sheets_dir.
def find_seed_sheet(
    entity: str,
    variant: str | None = None,
    raw: str | None = None,
    *,
    sheets_dir: Path = SEED_SHEETS_DIR,
) -> StatSheet | None:
    names: list[str] = []
    kind = (variant or "").strip()
    if kind:
        names.append(f"{kind} {entity}")
    names.append(entity)
    for name in names:
        sheet = _sheet_at(_canonical_slug(name), sheets_dir)
        if sheet is not None:
            return sheet
    return _sheet_from_raw(entity, raw, sheets_dir)


def _sheet_at(slug: str, sheets_dir: Path) -> StatSheet | None:
    if not slug or re.search(r"[^a-z0-9-]", slug):
        return None
    path = sheets_dir / f"{slug}.json"
    if not path.is_file():
        return None
    return StatSheet.model_validate_json(path.read_text(encoding="utf-8"))


# Unique seed sheet for a live-style raw phrase: "6 gray wolves" + entity "wolf"
# finds gray-wolf, even though "wolves" does not slug to "wolf". A vague phrase
# like "a bear" matches no unique sheet (the prefix is not in the phrase).
def _sheet_from_raw(entity: str, raw: str | None, sheets_dir: Path) -> StatSheet | None:
    if not raw or not raw.strip():
        return None
    entity_slug = _canonical_slug(entity)
    if not entity_slug:
        return None
    raw_tokens = {part for part in _canonical_slug(raw).split("-") if part and not part.isdigit()}
    matches: list[Path] = []
    try:
        entries = sheets_dir.iterdir()
    except OSError:
        return None
    for path in entries:
        if path.suffix != ".json" or not path.is_file():
            continue
        slug = path.stem
        if not slug or re.search(r"[^a-z0-9-]", slug):
            continue
        parts = slug.split("-")
        if len(parts) < 2 or parts[-1] != entity_slug:
            continue
        if all(part in raw_tokens for part in parts[:-1]):
            matches.append(path)
            if len(matches) > 1:
                return None
    if len(matches) != 1:
        return None
    return _sheet_at(matches[0].stem, sheets_dir)
