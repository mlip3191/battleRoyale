"""The two crowd replay logs in frontend/src/game/fixtures must match what the engine makes today.

The front end tests and the Phaser stage use these files, so a change to the engine (a new
ENGINE_VERSION, or any change that moves the random draws) must come with regenerated files.
"""

import json
from pathlib import Path

import pytest

from app.simulation.engine import run
from tests.property.sim_helpers import duck, lion, matchup_of

FIXTURES = Path(__file__).resolve().parents[3] / "frontend" / "src" / "game" / "fixtures"


@pytest.mark.parametrize(
    ("name", "ducks", "lions"),
    [("thousand-vs-one", 1000, 1), ("two-hundred-vs-five", 200, 5)],
)
def test_the_committed_crowd_fixture_matches_the_engine(name, ducks, lions):
    committed = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    made = json.loads(run(matchup_of(ducks, lions), [duck(), lion()]).model_dump_json())
    assert made == committed, "regenerate the crowd fixtures (see the README)"
