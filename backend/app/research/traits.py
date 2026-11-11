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
ANIMALTRAITS_LICENSE = "CC0 1.0; cite Herberstein et al. 2022, Scientific Data 9:265"
TAXON_NAME = "P225"


@dataclass
class TraitTables:
    """Each dataset's facts, keyed by scientific name."""

    by_source: dict[str, dict[str, list[Fact]]] = field(default_factory=dict)
    licenses: dict[str, str] = field(default_factory=dict)


# The fighter's scientific name from its Wikidata entity, if it has one.
def taxon_name(entity: dict[str, Any]) -> str | None:
    for claim in entity.get("claims", {}).get(TAXON_NAME, []):
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
        path.write_bytes(await fetch_file(client, url, sleep=sleep))
    return path.read_bytes().decode("utf-8", errors="replace")


# Load both datasets; one that fails to download is logged and skipped, never fatal.
async def load_trait_tables(
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
        tables.by_source[source] = read(text)
        tables.licenses[source] = license_name
    return tables, failures
