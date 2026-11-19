"""#364: the README's headline example reads, fights, and ends with a verdict on mocks.

The example is read from README.md itself, so changing it there without this test fails here.
It goes through the same two routes the page uses (POST /api/intake, then POST /api/battles)
and the whole pipeline. Speed is not checked: test_simulate_budget.py pins the Simulate limit.
"""

import re
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.battles import get_store
from app.config import REPO_ROOT, Settings, use_settings
from app.main import create_app
from app.models.battle import BattleRecord
from app.models.matchup import IntakeResult
from app.pipeline.store import BattleStore
from tests.conftest import mock_settings

SIM_RUNS = 20  # enough for a verdict; the full 1,000 runs would only add time
WAIT_SECONDS = 60.0
# The italic quoted example on README's first paragraph: *"... vs ..."*.
EXAMPLE = re.compile(r'\*"([^"]+ vs [^"]+)"\*')


# The example matchup exactly as README shows it.
def readme_example() -> str:
    first_paragraph = (REPO_ROOT / "README.md").read_text(encoding="utf-8").split("\n\n")[1]
    match = EXAMPLE.search(first_paragraph)
    assert match, "README's first paragraph no longer has an italic quoted example"
    return match.group(1)


# Few simulation runs, as in the other pipeline tests, so the battle finishes quickly.
@pytest.fixture(autouse=True)
def _quick_simulation(tmp_path: Path) -> None:
    use_settings(mock_settings(sim_runs=SIM_RUNS, data_dir=tmp_path / "data"))


# A running app with the real mock intake model and a fresh, empty battle store.
@pytest.fixture
def client(settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    store = BattleStore()
    app = create_app(settings, frontend_dist=tmp_path / "missing")
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client


# Poll GET until the battle stops running (a stuck battle fails the test, not the clock).
def wait_until_finished(client: TestClient, battle_id: str) -> BattleRecord:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        record = BattleRecord.model_validate(client.get(f"/api/battles/{battle_id}").json())
        if record.status != "running":
            return record
        time.sleep(0.02)
    raise AssertionError(f"battle {battle_id} never finished")


def test_readme_example_finishes_with_the_duck_winning(client: TestClient) -> None:
    text = readme_example()
    assert text == "100 duck-sized horses vs 1 horse-sized duck"  # update both together
    response = client.post("/api/intake", json={"text": text})
    assert response.status_code == 200, response.text
    intake = IntakeResult.model_validate(response.json())
    assert intake.status == "ok" and intake.matchup is not None
    sides = [(f.entity, f.count, f.size_reference) for f in intake.matchup.fighters]
    assert sides == [("horse", 100, "duck"), ("duck", 1, "horse")]

    started = client.post("/api/battles", json=intake.matchup.model_dump(mode="json"))
    assert started.status_code == 202, started.text
    record = wait_until_finished(client, started.json()["battle_id"])
    simulate = next(stage for stage in record.stages if stage.stage == "simulate")
    # Under the old 3 s limit this stage could end "failed": "too big to simulate quickly".
    assert (record.status, simulate.status) == ("done", "done"), simulate.detail
    assert record.result is not None and record.result.outcome == "win_1"
    assert record.stat_sheets[1].display_name == "Duck"
