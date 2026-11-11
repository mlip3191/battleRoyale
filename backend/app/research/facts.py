"""Pull structured facts out of a Wikidata entity and store them with their references."""

import sqlite3
from dataclasses import dataclass
from typing import Any

# The Wikidata properties we read, and the unit names units.py understands for each unit item.
PROPERTIES = {"P2067": "mass", "P2043": "length", "P2048": "height", "P2052": "speed"}
UNIT_ITEMS = {
    "Q11570": "kg",
    "Q41803": "g",
    "Q191118": "t",
    "Q100995": "lb",
    "Q11573": "m",
    "Q174728": "cm",
    "Q174789": "mm",
    "Q3710": "ft",
    "Q218593": "in",
    "Q182429": "m/s",
    "Q180154": "km/h",
    "Q211256": "mph",
}


@dataclass(frozen=True)
class Fact:
    """One structured value and where it came from."""

    source: str
    field: str
    value: float
    unit: str
    reference: str


# Read one statement into a fact; None if it has no usable number or a unit we don't know.
def _fact_from_claim(entity_id: str, prop: str, claim: dict[str, Any]) -> Fact | None:
    if claim.get("rank") == "deprecated":
        return None
    try:
        data = claim["mainsnak"]["datavalue"]["value"]
        value = float(data["amount"])
        unit = UNIT_ITEMS.get(data["unit"].rsplit("/", 1)[-1])
        statement = claim["id"]
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if unit is None:
        return None
    reference = f"https://www.wikidata.org/wiki/{entity_id}#{statement}"
    return Fact(source="wikidata", field=prop, value=value, unit=unit, reference=reference)


# Every mass, length, height, and speed statement on a Wikidata entity.
def wikidata_facts(entity: dict[str, Any]) -> list[Fact]:
    entity_id = str(entity.get("id", ""))
    claims = entity.get("claims", {})
    found = [
        _fact_from_claim(entity_id, prop, claim)
        for prop in PROPERTIES
        for claim in claims.get(prop, [])
    ]
    return [fact for fact in found if fact is not None]


# Replace a fighter's facts from one source, so a re-run leaves the same rows.
def store_facts(
    connection: sqlite3.Connection,
    fighter_id: str,
    source: str,
    facts: list[Fact],
    license_name: str,
    retrieved_at: str,
) -> None:
    with connection:
        connection.execute(
            "DELETE FROM facts WHERE fighter_id = ? AND source = ?", (fighter_id, source)
        )
        connection.executemany(
            "INSERT INTO facts (fighter_id, source, field, value, unit, reference, license, "
            "retrieved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    fighter_id,
                    f.source,
                    f.field,
                    f.value,
                    f.unit,
                    f.reference,
                    license_name,
                    retrieved_at,
                )
                for f in facts
            ],
        )
