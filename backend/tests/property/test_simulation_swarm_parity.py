"""Swarm mode (groups) must tell the same story as the one-by-one engine (issue #76).

Each fight is run twice with the same sheets, once forced through each engine by moving
SWARM_THRESHOLD. The tolerances are loose enough to hold at these run counts and tight enough to
catch the old problems: crowds overrated by 0.06-0.22, fights twice as long, a third fewer
survivors. The full table is `scripts/validate_swarm.py`.
"""

import random

import pytest

from app.simulation import constants as c
from app.simulation import engine
from app.simulation.engine import _spread_tracked, run
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
    """Swarm mode used to overrate the crowd by +0.06 to +0.22, then underrated it by 0.04 to 0.06
    (it forgot which defenders were already wounded). It now agrees within noise (see
    docs/swarm-validation.md), so this pins both directions."""
    cat = make_sheet(
        "cat", mass_kg=4.5, size_m=0.46, top_speed_mps=13, attack_force_n=200,
        attacks_per_s=2.0, reach_m=0.2, armor_0_1=0.05, aggression_0_1=1.0,
    )  # fmt: skip
    # 300 runs per engine have noise of about 0.08, so this passes thanks to the fixed seeds, not
    # statistical power: it catches the old +0.06 to +0.22 error, but a version bump (which
    # reshuffles every seed) may need the run count raised.
    one, swarm = both(monkeypatch, [cat, wolf()], cats, wolves)
    assert abs(swarm.win_prob[0] - one.win_prob[0]) <= 0.05


def test_a_pack_around_one_big_target_gives_the_same_win_share(monkeypatch):
    bear = load_sheet("stat-sheet.json")
    one, swarm = both(monkeypatch, [wolf(), bear], 12, 1)
    assert abs(swarm.win_prob[0] - one.win_prob[0]) <= 0.08  # was -0.09 (damage carried over)


# --- _spread_tracked: wounded defenders are remembered between steps (#76) ------------------------


def test_a_wounded_front_keeps_taking_damage_step_after_step():
    rng = random.Random(1)
    state = ([], [])
    for _ in range(3):  # one front, one hit of 10 per step on a 100-hit-point fighter
        kills, n_left, state = _spread_tracked(1, 10.0, 5, state, 100.0, 1, rng)
        assert kills == 0 and n_left == 5
    assert state == ([70.0], [])


def test_attackers_share_the_hits_evenly_across_the_fronts():
    rng = random.Random(2)
    kills, _, (fronts, reserve) = _spread_tracked(12, 10.0, 20, ([], []), 100.0, 4, rng)
    assert kills == 0 and reserve == [] and fronts == [70.0] * 4  # 3 hits each, no luck involved


def test_the_leftover_hits_go_to_random_fronts():
    rng = random.Random(3)
    _, _, (fronts, _) = _spread_tracked(6, 10.0, 20, ([], []), 100.0, 4, rng)
    assert sorted(fronts) == [80.0, 80.0, 90.0, 90.0]  # 1 hit each, plus 2 extra on two fronts


def test_wounds_never_heal_when_fewer_fronts_are_fought():
    rng = random.Random(4)
    _, _, state = _spread_tracked(4, 10.0, 20, ([], []), 100.0, 4, rng)  # 4 fronts, 90 hp each
    _, _, (fronts, reserve) = _spread_tracked(0, 10.0, 20, state, 100.0, 2, rng)
    assert len(fronts) + len(reserve) == 4 and sorted(fronts + reserve) == [90.0] * 4
    assert len(fronts) == 2  # only two are being fought now; the other two wait, still wounded


def test_a_front_that_kills_moves_on_to_a_fresh_fighter_only_if_one_is_waiting():
    rng = random.Random(5)
    kills, n_left, (fronts, _) = _spread_tracked(10, 10.0, 2, ([], []), 10.0, 2, rng)
    assert kills == 2 and n_left == 0 and fronts == []  # nobody left to move on to
    kills, n_left, (fronts, _) = _spread_tracked(2, 10.0, 3, ([], []), 10.0, 2, rng)
    assert kills == 2 and n_left == 1 and len(fronts) == 1  # one waiting fighter, one front left


@pytest.mark.parametrize("seed", range(20))
def test_the_bookkeeping_always_adds_up(seed):
    rng = random.Random(seed)
    n, full = rng.randint(2, 60), 100.0
    state = ([], [])
    for _ in range(25):
        hits, g = rng.randint(0, 80), rng.randint(1, 30)
        kills, n_left, state = _spread_tracked(hits, rng.uniform(5, 60), n, state, full, g, rng)
        fronts, reserve = state
        assert 0 <= kills <= n and n_left == n - kills
        assert len(fronts) + len(reserve) <= n_left
        assert all(0 < hp <= full for hp in fronts + reserve)
        n = n_left
        if n == 0:
            break


def test_the_hits_are_all_applied_however_the_fronts_are_grouped():
    """Fronts with the same hit points are handled together; no hit may be lost or doubled."""
    for seed in range(30):
        rng = random.Random(seed)
        g, hits = rng.randint(2, 40), rng.randint(0, 300)
        full, dmg = 1000.0, 1.0  # nobody can die, so every hit is a point of damage on a front
        state = ([], [])
        _, _, (fronts, reserve) = _spread_tracked(hits, dmg, 500, state, full, g, rng)
        assert len(fronts) == g and reserve == []
        assert round(sum(full - hp for hp in fronts)) == hits  # exactly the hits that were dealt
        share, extra = divmod(hits, g)
        assert sorted(full - hp for hp in fronts) == [share] * (g - extra) + [share + 1] * extra


def test_identical_fronts_are_processed_as_one_group(monkeypatch):
    """The speedup: 400 fronts at the same hit points cost two hit calculations, not 400."""
    calls = []
    real = engine._apply_hits

    def counting(*args):
        calls.append(args)
        return real(*args)

    monkeypatch.setattr(engine, "_apply_hits", counting)
    rng = random.Random(0)
    _spread_tracked(1000, 1.0, 5000, ([], []), 100.0, 400, rng)  # 2.5 hits each: 400 fronts
    assert len(calls) <= 2
