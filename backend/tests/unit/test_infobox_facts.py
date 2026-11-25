"""#522 part 1: infobox rows are stored as facts that quote their row, and come first."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import get_settings
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.stats import StatName
from app.research.facts import Fact
from app.research.infobox import infobox_facts
from app.research.ingest import restore_saved_facts
from app.research.seed_fighters import SeedFighter
from app.research.sources import SourceDocument, save_raw
from app.research.statsheet import StoredFact, load_facts, stat_from_facts
from scripts import ingest_seed

URL = "https://en.wikipedia.org/w/index.php?title=Golden_Retriever&oldid=1"
WHEN = datetime(2026, 11, 25, tzinfo=UTC)
DOG = """<table class="infobox"><tbody>
<tr><th class="infobox-label">Height</th><td class="infobox-data">Males</td>
<td class="infobox-data">56–61 cm (22–24 in)</td></tr>
<tr><th class="infobox-label"></th><td class="infobox-data">Females</td>
<td class="infobox-data">51–56 cm (20–22 in)</td></tr>
<tr><th class="infobox-label">Weight</th><td class="infobox-data">25–34 kg (55–75 lb)</td></tr>
</tbody></table>"""
DOG_FIGHTER = SeedFighter(
    "golden-retriever", "Golden retriever", "Adult male", "mammal", "living", "land", "x"
)


# The saved article, as a past ingest left it under kb_dir.
def save_dog(kb_dir: Path) -> None:
    body = DOG.encode("utf-8")
    article = SourceDocument("Golden Retriever", URL, "CC BY-SA 4.0", WHEN, "text/html", body, True)
    save_raw(kb_dir, "golden-retriever", "wikipedia", article)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "app.db")
    apply_migrations(connection)
    yield connection
    connection.close()


def test_infobox_facts_come_first_and_cite_their_row() -> None:
    infobox = [StoredFact(f, "CC BY-SA 4.0", WHEN) for f in infobox_facts(DOG, URL)]
    wikidata = StoredFact(
        Fact("wikidata", "P2067", 30.0, "kg", "https://www.wikidata.org/wiki/Q38686#Q1"),
        "CC0 1.0",
        WHEN,
    )
    mass = stat_from_facts(StatName.MASS, [wikidata, *infobox])
    assert mass is not None and mass.value == 34.0 and mass.method == "extracted"
    assert mass.source is not None and mass.source.quote == "Weight: 25–34 kg (55–75 lb)"
    assert str(mass.source.url) == f"{URL}#infobox" and mass.source.title == "Wikipedia infobox"
    size = stat_from_facts(StatName.SIZE, infobox)
    assert size is not None and size.value == 0.61  # the middle of the two, the upper one
    wikidata_mass = stat_from_facts(StatName.MASS, [wikidata])
    assert wikidata_mass is not None and wikidata_mass.source is not None
    assert wikidata_mass.source.quote == "mass: 30 kg"  # facts without a quote: as before


def test_saved_articles_give_their_facts_again_without_a_download(
    database: sqlite3.Connection, tmp_path: Path
) -> None:
    save_dog(tmp_path)
    duck = SeedFighter("duck", "Duck", "Adult mallard", "bird", "living", "amphibious", "Mallard")
    assert restore_saved_facts(database, [DOG_FIGHTER, duck], tmp_path) == 1  # no duck files
    stored = load_facts(database, "golden-retriever")
    assert [(s.fact.source, s.fact.quote) for s in stored][-1] == (
        "infobox",
        "Weight: 25–34 kg (55–75 lb)",
    )
    assert all(s.retrieved_at == WHEN and s.license == "CC BY-SA 4.0" for s in stored)
    assert restore_saved_facts(database, [DOG_FIGHTER], tmp_path) == 1  # replaces, never adds
    assert len(load_facts(database, "golden-retriever")) == 3


async def test_the_facts_only_run_reads_saved_files_and_nothing_else(
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = get_settings().data_dir
    save_dog(data_dir / "kb")
    assert await ingest_seed.main(False, ["golden-retriever"], facts_only=True) == 0
    assert "Stored facts again from saved files for 1 of 1 fighters." in capsys.readouterr().out
    connection = connect(data_dir / "app.db")
    try:
        quotes = [s.fact.quote for s in load_facts(connection, "golden-retriever")]
    finally:
        connection.close()
    assert quotes == [
        "Height: Males 56–61 cm (22–24 in)",
        "Height: Females 51–56 cm (20–22 in)",
        "Weight: 25–34 kg (55–75 lb)",
    ]
