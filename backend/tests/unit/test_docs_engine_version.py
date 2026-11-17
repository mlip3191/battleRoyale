"""The ENGINE_VERSION in docs/simulation-model.md's constants table matches the code (QA of swarm
mode, Nov 15: the table said 9 for a while after #281 moved it to 10)."""

import re
from pathlib import Path

from app.simulation import constants as c

DOC = Path(__file__).resolve().parents[3] / "docs" / "simulation-model.md"


def test_the_constants_table_names_the_current_engine_version() -> None:
    rows = re.findall(r"^\| `ENGINE_VERSION` \| (\d+) \|", DOC.read_text("utf-8"), re.MULTILINE)
    assert rows == [str(c.ENGINE_VERSION)]
