"""Body mass and length from the PanTHERIA and AnimalTraits datasets, matched by scientific name."""

import asyncio
import csv
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.research.facts import Fact
from app.research.sources import Sleep, SourceError, fetch_file

logger = logging.getLogger(__name__)

PANTHERIA_URL = "https://esapubs.org/archive/ecol/E090/184/PanTHERIA_1-0_WR05_Aug2008.txt"
PANTHERIA_LICENSE = "No copyright restrictions; cite Jones et al. 2009, Ecology 90:2648"
# PanTHERIA columns we read, with the unit each one is recorded in.
PANTHERIA_FIELDS = {"5-1_AdultBodyMass_g": "g", "13-1_AdultHeadBodyLen_mm": "mm"}
PANTHERIA_MISSING = -999.0
ANIMALTRAITS_URL = "https://zenodo.org/records/6468938/files/observations.csv"
ANIMALTRAITS_LICENSE = (
    "CC0 1.0 (database), CC BY 4.0 (paper); cite Herberstein et al. 2022, Scientific Data 9:265"
)
TAXON_NAME = "P225"
TRAIT_LICENSES = {"pantheria": PANTHERIA_LICENSE, "animaltraits": ANIMALTRAITS_LICENSE}
# The team dataset on Hugging Face (G02): the PanTHERIA and AnimalTraits rows for the seed
# fighters only, built by scripts/build_seed_traits.py and uploaded by a teammate. Each row keeps
# its original source, reference, and license; Hugging Face only hosts the file.
HF_TRAITS_DATASET = "MBAX6418Bros/battle-royale-seed-traits"
HF_TRAITS_URL = f"https://huggingface.co/datasets/{HF_TRAITS_DATASET}/resolve/main/seed-traits.csv"
TEAM_COLUMNS = ("scientific_name", "source", "field", "value", "unit", "reference")


@dataclass
class TraitTables:
    """Each dataset's facts, keyed by scientific name."""

    by_source: dict[str, dict[str, list[Fact]]] = field(default_factory=dict)
    licenses: dict[str, str] = field(default_factory=dict)
    origin: str = "the original dataset downloads"
    """Where the rows came from, for the ingest summary."""


# The fighter's scientific name from its Wikidata entity: a preferred claim first, never a
# deprecated one, so a name Wikidata marks as wrong can't become an exact dataset match.
def taxon_name(entity: dict[str, Any]) -> str | None:
    claims = [
        claim
        for claim in entity.get("claims", {}).get(TAXON_NAME, [])
        if claim.get("rank") != "deprecated"
    ]
    claims.sort(key=lambda claim: claim.get("rank") != "preferred")  # stable: keeps order
    for claim in claims:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


# One row per mammal species; -999 means the value was not recorded.
def pantheria_facts(text: str) -> dict[str, list[Fact]]:
    table: dict[str, list[Fact]] = {}
    for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
        name = row.get("MSW05_Binomial", "").strip()
        for column, unit in PANTHERIA_FIELDS.items():
            value = _number(row.get(column))
            if name and value is not None and value != PANTHERIA_MISSING and value > 0:
                reference = f"{PANTHERIA_URL}#{name.replace(' ', '_')}"
                fact = Fact(
                    source="pantheria", field=column, value=value, unit=unit, reference=reference
                )
                table.setdefault(name, []).append(fact)
    return table


# One row per observation; each fact points at its row and names the study it came from.
def animaltraits_facts(text: str) -> dict[str, list[Fact]]:
    table: dict[str, list[Fact]] = {}
    for row_number, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        name = (row.get("species") or "").strip()
        value = _number(row.get("body mass"))
        unit = (row.get("body mass - units") or "").strip()
        if name and unit and value is not None and value > 0:
            study = (row.get("inTextReference") or "").strip() or "study not named"
            sex = (row.get("sex") or "").strip()
            note = f"{study}; {sex}" if sex else study
            reference = f"{ANIMALTRAITS_URL}#row-{row_number} ({note})"
            fact = Fact(
                source="animaltraits",
                field="body mass",
                value=value,
                unit=unit,
                reference=reference,
            )
            table.setdefault(name, []).append(fact)
    return table


# Read a number, treating blanks and text as missing.
def _number(raw: str | None) -> float | None:
    try:
        return float(raw) if raw not in (None, "") else None
    except ValueError:
        return None


# Download a dataset once into data/kb/traits/, so later runs read the saved copy.
async def _dataset_text(client: httpx.AsyncClient, url: str, path: Path, sleep: Sleep) -> str:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(path.suffix + ".part")  # a cut-off download never looks done
        partial.write_bytes(await fetch_file(client, url, sleep=sleep))
        partial.replace(path)
    return path.read_bytes().decode("utf-8", errors="replace")


# The team dataset's rows: every stored fact for the given scientific names, in a fixed order.
def team_rows(tables: TraitTables, names: set[str]) -> list[dict[str, str]]:
    rows = [
        {
            "scientific_name": name,
            "source": source,
            "field": fact.field,
            "value": f"{fact.value:.15g}",
            "unit": fact.unit,
            "reference": fact.reference,
        }
        for source, table in sorted(tables.by_source.items())
        for name in sorted(names)
        for fact in table.get(name, [])
    ]
    return rows


# The rows as CSV text, ready to upload.
def team_csv(rows: list[dict[str, str]]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=TEAM_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


# Read the team CSV back into tables; rows with an unknown source or a bad number are skipped.
def team_tables(text: str) -> TraitTables:
    tables = TraitTables(origin=f"the Hugging Face team dataset ({HF_TRAITS_DATASET})")
    for row in csv.DictReader(io.StringIO(text)):
        source, name = (row.get("source") or "").strip(), (row.get("scientific_name") or "").strip()
        value = _number(row.get("value"))
        if source not in TRAIT_LICENSES or not name or value is None or value <= 0:
            continue
        fact = Fact(
            source=source,
            field=(row.get("field") or "").strip(),
            value=value,
            unit=(row.get("unit") or "").strip(),
            reference=f"{(row.get('reference') or '').strip()} (via {HF_TRAITS_URL})",
        )
        tables.by_source.setdefault(source, {}).setdefault(name, []).append(fact)
        tables.licenses[source] = TRAIT_LICENSES[source]
    return tables


# The team dataset from Hugging Face, or None when it can't be downloaded or has no rows.
# The token is optional (the dataset is public) and only ever goes in the request header.
async def load_team_dataset(
    client: httpx.AsyncClient, token: str | None, sleep: Sleep = asyncio.sleep
) -> TraitTables | None:
    headers = {"Authorization": f"Bearer {token}"} if token else None
    try:
        body = await fetch_file(client, HF_TRAITS_URL, sleep=sleep, headers=headers)
    except (SourceError, httpx.HTTPError) as error:
        logger.warning("Hugging Face team dataset unavailable (%s); using the originals.", error)
        return None
    tables = team_tables(body.decode("utf-8", errors="replace"))
    if not tables.by_source:
        logger.warning("Hugging Face team dataset had no usable rows; using the originals.")
        return None
    return tables


# Load the trait rows: the Hugging Face team dataset first, else both original datasets.
async def load_trait_tables(
    client: httpx.AsyncClient,
    kb_dir: Path,
    sleep: Sleep = asyncio.sleep,
    hf_token: str | None = None,
) -> tuple[TraitTables, list[str]]:
    team = await load_team_dataset(client, hf_token, sleep)
    if team is not None:
        return team, []
    return await load_original_tables(client, kb_dir, sleep)


# Load both original datasets; one that fails to download is logged and skipped, never fatal.
async def load_original_tables(
    client: httpx.AsyncClient, kb_dir: Path, sleep: Sleep = asyncio.sleep
) -> tuple[TraitTables, list[str]]:
    datasets = [
        ("pantheria", PANTHERIA_URL, "pantheria.txt", pantheria_facts, PANTHERIA_LICENSE),
        (
            "animaltraits",
            ANIMALTRAITS_URL,
            "animaltraits.csv",
            animaltraits_facts,
            ANIMALTRAITS_LICENSE,
        ),
    ]
    tables, failures = TraitTables(), []
    for source, url, filename, read, license_name in datasets:
        try:
            text = await _dataset_text(client, url, kb_dir / "traits" / filename, sleep)
        except (SourceError, httpx.HTTPError, OSError) as error:  # only means fewer facts
            logger.warning("Could not load %s: %s", source, error)
            failures.append(f"{source}: {error}")
            continue
        table = read(text)
        # A changed format or a saved error page would otherwise look like "no matches". Delete
        # the saved copy so the next run downloads it again instead of reusing it.
        if not table:
            (kb_dir / "traits" / filename).unlink(missing_ok=True)
            logger.warning(
                "%s had no usable rows, so its saved file was deleted; the next run downloads "
                "it again. If this repeats, the file format may have changed.",
                source,
            )
            failures.append(f"{source}: no usable rows in {filename}")
            continue
        tables.by_source[source] = table
        tables.licenses[source] = license_name
    return tables, failures
