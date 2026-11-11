"""Swarm mode (groups) must tell the same story as the one-by-one engine (issue #76).

Each fight is run twice with the same sheets, once forced through each engine by moving
SWARM_THRESHOLD. The tolerances are loose enough to hold at these run counts and tight enough to
catch the old problems: crowds overrated by 0.06-0.22, fights twice as long, a third fewer
survivors. The full table is `scripts/validate_swarm.py`.
"""

import pytest

from app.simulation import constants as c
from app.simulation.engine import run
from tests.property.sim_helpers import load_sheet, make_sheet, matchup_of

ALWAYS_INDIVIDUAL = 10**9
ALWAYS_SWARM = 0
RUNS = 300


def both(monkeypatch, sheets, na, nb, runs=RUNS):
    results = []
    for threshold in (ALWAYS_INDIVIDUAL, ALWAYS_SWARM):
        monkeypatch.setattr(c, "SWARM_THRESHOLD", threshold)
        results.append(run(matchup_of(na, nb), sheets, runs=runs, explain=False))
    return results


def wolf():
    return load_sheet("stat-sheet-gray-wolf.json")


def test_killing_targets_that_cannot_fight_back_takes_the_same_time(monkeypatch):
    # The tail of a fight: once a side breaks, the winners hunt the runners down. Swarm mode used
    # to take about 2.5x as long because dead fronts still counted in the group's hit points.
    dummy = make_sheet(
        "dummy", mass_kg=40, size_m=1.0, attack_force_n=0, attacks_per_s=0, top_speed_mps=0,
        armor_0_1=0.15, spread=0.0, body="inert", weapons=["none"],
    )  # fmt: skip
    one, swarm = both(monkeypatch, [wolf(), dummy], 50, 43, runs=100)
    assert swarm.mean_duration_s == pytest.approx(one.mean_duration_s, rel=0.2)


def test_matched_groups_last_as_long_and_leave_as_many_alive(monkeypatch):
    one, swarm = both(monkeypatch, [wolf(), wolf()], 40, 40)
    assert swarm.mean_duration_s == pytest.approx(one.mean_duration_s, rel=0.2)
    assert sum(swarm.mean_survivors) == pytest.approx(sum(one.mean_survivors), rel=0.1)


@pytest.mark.parametrize(("cats", "wolves"), [(50, 10), (100, 20)])
def test_a_crowd_of_weak_fighters_is_not_overrated(monkeypatch, cats, wolves):
    """Swarm mode used to overrate the crowd by +0.06 to +0.22. It now underrates it a little
    (about -0.04 to -0.06, see docs/swarm-validation.md), so this pins both sides of that."""
    cat = make_sheet(
        "cat", mass_kg=4.5, size_m=0.46, top_speed_mps=13, attack_force_n=200,
        attacks_per_s=2.0, reach_m=0.2, armor_0_1=0.05, aggression_0_1=1.0,
    )  # fmt: skip
    one, swarm = both(monkeypatch, [cat, wolf()], cats, wolves)
    assert abs(swarm.win_prob[0] - one.win_prob[0]) <= 0.08


def test_a_pack_around_one_big_target_gives_the_same_win_share(monkeypatch):
    bear = load_sheet("stat-sheet.json")
    one, swarm = both(monkeypatch, [wolf(), bear], 12, 1)
    assert abs(swarm.win_prob[0] - one.win_prob[0]) <= 0.08  # was -0.09 (damage carried over)
