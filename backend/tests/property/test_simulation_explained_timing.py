"""#119: simulate plus the deciding-factor analysis fits the 3 s Simulate stage.

The 3 s budget is for a developer laptop. CI runners are 2 to 3 times slower, so a wall-clock
assert at 3 s would fail there for no reason. What made the explained showcase battle slow was
building a replay event for every hit of every run, so the strict test counts those instead (it
does not depend on the machine), and the timing test only catches a gross regression.
"""

import functools
import math
import time

from app.simulation import engine
from app.simulation.engine import _templates, run, run_once
from app.simulation.rng import run_rng
from tests.property.sim_helpers import duck, horse, matchup_of
from tests.property.test_simulation_swarm_parity import elephant, small_cat


def showcase_one():
    """100 duck-sized horses vs 1 horse-sized duck: the slowest showcase battle."""
    matchup = matchup_of(100, 1, ref_0="duck", ref_1="horse")
    return matchup, [horse(), duck()], [duck(), horse()]


# --- Wall-clock guards, calibrated on the same machine (#382, PM's choice: option 2) -------------
# A fixed limit (10 s) failed on a throttled laptop (12 to 15 s on battery) and on a clean main,
# while passing on CI. So each guard compares the fight with a quick reference run made just
# before it, on the same machine: 3 cats v 1 elephant at 3,000 runs without the explanation. It is a
# one-by-one fight with no replay events, so the two slowdowns guarded here (swarm mode lost, an
# event built per hit) do not touch it. A reference on the guarded path would slow down with the
# fight, and the ratio would hide the regression. Throttling slows both about equally.
# Measured on a laptop on engine 12: the reference takes about 0.56 s (within 5 % from run to run)
# and the guarded fights 4.4 to 5.1 s, a ratio of about 8 to 9. The limit is 20 times the
# reference: about 2.2 times the normal ratio, as sensitive as the old fixed 10 s on this laptop,
# but it grows on a slower machine. Falling back to one by one is about 9 times slower than the
# normal fight (41 s against 4.6 s here, 32 s against 2 s on the earlier laptop), far over it.
# The showcase guard is a coarse check. The strict test above (events built) is what pins the
# replay cost, and it does not depend on the machine.
# The absolute ceiling is a backstop: it is above the 12 to 15 s a throttled laptop took, and
# below the one-by-one fight, so a broken calibration cannot hide a real slowdown.
# If a guard still fails on your machine: plug in or switch to performance mode, close other
# programs, and run this file again (tests/property/test_simulation_explained_timing.py).
REFERENCE_RUNS = 3_000
LIMIT_MULTIPLE = 20
CEILING_S = 25.0


@functools.cache
def reference_seconds() -> float:
    """The fastest of three reference runs: the machine's speed right now, once per test file."""
    best = math.inf
    for _ in range(3):
        start = time.perf_counter()
        run(matchup_of(3, 1), [small_cat(), elephant()], runs=REFERENCE_RUNS, explain=False)
        best = min(best, time.perf_counter() - start)
    return best


def assert_not_grossly_slow(elapsed: float, reference: float, what: str):
    limit = min(LIMIT_MULTIPLE * reference, CEILING_S)
    assert elapsed < limit, (
        f"{what} took {elapsed:.1f} s; the limit is {limit:.1f} s "
        f"({LIMIT_MULTIPLE} x the {reference:.2f} s reference run, at most {CEILING_S:.0f} s). "
        "On a slow or throttled laptop, plug in or switch to performance mode and run it again."
    )


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
    reference = reference_seconds()  # measured before the fight, on this machine
    start = time.perf_counter()
    run(matchup, sheets, reference_sheets=references)
    elapsed = time.perf_counter() - start
    assert_not_grossly_slow(elapsed, reference, "simulate plus the explanation")


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


def test_150_cats_v_1_elephant_with_the_analysis_is_not_grossly_slow():
    # Swarm mode by work (D-50, #183): a few seconds with the analysis on a laptop, against about
    # 16 times that one by one. The calibrated limit above catches the fall back to one by one.
    reference = reference_seconds()
    start = time.perf_counter()
    run(matchup_of(150, 1), [small_cat(), elephant()])
    assert_not_grossly_slow(time.perf_counter() - start, reference, "150 cats v 1 elephant")
