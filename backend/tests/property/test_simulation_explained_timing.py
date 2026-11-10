"""#119: simulate plus the deciding-factor analysis fits the 3 s Simulate stage."""

import time

from app.simulation.engine import _templates, run, run_once
from app.simulation.rng import run_rng
from tests.property.sim_helpers import duck, horse, matchup_of


def showcase_one():
    """100 duck-sized horses vs 1 horse-sized duck: the slowest showcase battle."""
    matchup = matchup_of(100, 1, ref_0="duck", ref_1="horse")
    return matchup, [horse(), duck()], [duck(), horse()]


def test_the_explained_showcase_battle_finishes_under_three_seconds():
    matchup, sheets, references = showcase_one()
    start = time.perf_counter()
    result = run(matchup, sheets, reference_sheets=references)  # 1,000 runs, with the explanation
    elapsed = time.perf_counter() - start
    assert result.deciding_factor_explainer  # the explanation really ran
    assert elapsed < 3.0, f"simulate plus the explanation took {elapsed:.1f} s"


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
