"""#119: simulate plus the deciding-factor analysis fits the 3 s Simulate stage.

The 3 s budget is for a developer laptop. CI runners are 2 to 3 times slower, so a wall-clock
assert at 3 s would fail there for no reason. What made the explained showcase battle slow was
building a replay event for every hit of every run, so the strict test counts those instead (it
does not depend on the machine), and the timing test only catches a gross regression.
"""

import time

from app.simulation import engine
from app.simulation.engine import _templates, run, run_once
from app.simulation.rng import run_rng
from tests.property.sim_helpers import duck, horse, matchup_of


def showcase_one():
    """100 duck-sized horses vs 1 horse-sized duck: the slowest showcase battle."""
    matchup = matchup_of(100, 1, ref_0="duck", ref_1="horse")
    return matchup, [horse(), duck()], [duck(), horse()]


def count_events_built(monkeypatch):
    built = []

    class Counting(engine.FightEvent):
        def __init__(self, **data):
            built.append(1)
            super().__init__(**data)

    monkeypatch.setattr(engine, "FightEvent", Counting)
    return built


def test_an_explained_run_builds_only_the_one_replay_it_records(monkeypatch):
    matchup, sheets, references = showcase_one()
    built = count_events_built(monkeypatch)
    result = run(matchup, sheets, reference_sheets=references)  # 1,000 runs, with the explanation
    assert result.deciding_factor_explainer  # the explanation really ran
    # One representative fight is recorded (at most 300 events); the thousands of other fights and
    # the deciding-factor runs build none. Before this was fixed it was over a million.
    assert 0 < len(built) < 2_000


def test_the_explained_showcase_battle_is_not_grossly_slow():
    matchup, sheets, references = showcase_one()
    start = time.perf_counter()
    run(matchup, sheets, reference_sheets=references)
    elapsed = time.perf_counter() - start
    # About 2 s on a laptop (3.2 s before the fix); 10 s catches a regression even on a slow runner.
    assert elapsed < 10.0, f"simulate plus the explanation took {elapsed:.1f} s"


def test_recording_the_replay_does_not_change_how_a_fight_plays_out():
    """Events are only built when someone records them; the fight itself must not depend on that."""
    matchup, sheets, references = showcase_one()
    for index in range(5):
        sides = _templates(matchup, sheets, run_rng(1, index), (1.0, 1.0))
        quiet = run_once(sides, matchup.terrain, run_rng(2, index))
        recorded = run_once(sides, matchup.terrain, run_rng(2, index), record_events=True)
        assert (quiet.winner, quiet.survivors, quiet.duration_s) == (
            recorded.winner,
            recorded.survivors,
            recorded.duration_s,
        )
        assert recorded.events and not quiet.events


def test_recording_does_not_change_a_swarm_sized_fight_either():
    matchup = matchup_of(250, 250)
    sheets = [horse(), duck()]
    for index in range(3):
        sides = _templates(matchup, sheets, run_rng(3, index), (1.0, 1.0))
        quiet = run_once(sides, matchup.terrain, run_rng(4, index))
        recorded = run_once(sides, matchup.terrain, run_rng(4, index), record_events=True)
        assert (quiet.winner, quiet.survivors, quiet.duration_s) == (
            recorded.winner,
            recorded.survivors,
            recorded.duration_s,
        )
