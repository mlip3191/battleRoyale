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
    budget = c.SWARM_WORK_BUDGET  # read before the loop: the first pass changes it
    for threshold in (ALWAYS_INDIVIDUAL, ALWAYS_SWARM):
        monkeypatch.setattr(c, "SWARM_THRESHOLD", threshold)
        monkeypatch.setattr(c, "SWARM_WORK_BUDGET", float("inf") if threshold else budget)
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


# --- D-50: swarm mode is chosen by expected work, not only by head count (#183) -------------------


def _fight(sheets, na, nb):
    from app.simulation.engine import _swarm_for

    return _swarm_for(matchup_of(na, nb), sheets, (1.0, 1.0))


def elephant():
    return make_sheet(
        "elephant", mass_kg=5000, size_m=3.2, top_speed_mps=11, attack_force_n=20000,
        attacks_per_s=0.5, reach_m=2.0, armor_0_1=0.5,
    )  # fmt: skip


def small_cat():
    return make_sheet(
        "cat", mass_kg=4.5, size_m=0.46, top_speed_mps=13, attack_force_n=80,
        attacks_per_s=2.0, reach_m=0.2, armor_0_1=0.05, aggression_0_1=1.0,
    )  # fmt: skip


def test_cheap_fights_stay_one_by_one():
    assert not _fight([wolf(), load_sheet("stat-sheet.json")], 1, 1)
    assert not _fight([wolf(), wolf()], 50, 50)
    assert not _fight([wolf(), wolf()], 100, 100)


def test_a_crowd_against_one_huge_target_goes_to_swarm_mode_below_200():
    assert _fight([small_cat(), elephant()], 150, 1)  # 32 s one by one, with the analysis
    assert _fight([small_cat(), elephant()], 50, 1)
    assert _fight([wolf(), wolf()], 150, 150)  # even, but too much work


def test_the_head_count_ceiling_still_applies():
    assert _fight([wolf(), wolf()], c.SWARM_THRESHOLD + 1, 1)


def test_the_choice_depends_only_on_the_inputs():
    """The mode takes no seed and uses no clock: nothing outside the inputs can change it."""
    results = set()
    for seed in range(5):
        random.seed(seed)  # the global generator must not matter
        results.add(_fight([small_cat(), elephant()], 150, 1))
    assert results == {True}
    assert _fight([small_cat(), elephant()], 5, 1) is False  # a small fight is not swapped


def test_the_expected_work_tracks_the_real_cost():
    """The estimate is only useful if it grows with the fight's real cost."""
    from app.simulation.engine import expected_work
    from app.simulation.fighters import apply_terrain, sample_template

    def work(sheets, na, nb):
        m = matchup_of(na, nb)
        sides = [
            apply_terrain(
                sample_template(
                    sheets[s], m.fighters[s].count, random.Random(0), 1.0, central=True
                ),
                m.terrain,
            )
            for s in (0, 1)
        ]
        return expected_work(sides)

    small = work([wolf(), wolf()], 50, 50)
    big = work([wolf(), wolf()], 200, 200)
    assert small < c.SWARM_WORK_BUDGET < big
    # Three times the cats means more than 1.5 times the work, not a flat estimate.
    assert work([small_cat(), elephant()], 150, 1) > 1.5 * work([small_cat(), elephant()], 50, 1)


def test_a_fight_sent_to_swarm_mode_by_its_work_agrees_with_one_by_one(monkeypatch):
    """The accuracy bar of D-45 for the fights that newly switch (150 cats v 1 elephant)."""
    one, swarm = both(monkeypatch, [small_cat(), elephant()], 150, 1, runs=200)
    assert abs(swarm.win_prob[0] - one.win_prob[0]) <= 0.08  # 200 runs: noise about 0.07
    assert swarm.mean_duration_s == pytest.approx(one.mean_duration_s, rel=0.2)


def test_swarm_steps_never_get_longer_than_the_cap_however_long_the_fight(monkeypatch):
    """Without the cap a 500 s fight takes 50 s steps and overrates the crowd by +0.13 (#183)."""
    from app.simulation.engine import _templates, run_once
    from app.simulation.rng import run_rng

    matchup = matchup_of(150, 1)
    sides = _templates(matchup, [small_cat(), elephant()], run_rng(1, 0), (1.0, 1.0))
    steps = []
    real = engine._spread_tracked

    def counting(hits, dmg, n, hurt, full_hp, g, rng):
        if full_hp == sides[1].max_hp:  # the cats' hits on the elephant: one call per step
            steps.append(1)
        return real(hits, dmg, n, hurt, full_hp, g, rng)

    monkeypatch.setattr(engine, "_spread_tracked", counting)
    out = run_once(sides, matchup.terrain, run_rng(2, 0), swarm=True)
    assert c.SWARM_STEP_MAX_S <= 5.0  # 5 s already overrated 150 v 1 by +0.03 (docs)
    assert out.duration_s > 200  # a long fight, where the old steps were longest
    # The first 30 s use finer steps; after that no step is longer than the cap.
    assert len(steps) >= (out.duration_s - 40) / c.SWARM_STEP_MAX_S


def test_a_fight_that_hits_the_time_limit_gets_no_extra_combat_in_swarm_mode(monkeypatch):
    # The closing step at 600 s used to be a full combat step (up to 60 s of extra fighting),
    # so swarm survivors came out about 10% low in a draw. Now it is about 4% low.
    from tests.property.sim_helpers import ant, lion

    one, swarm = both(monkeypatch, [ant(), lion()], 1500, 1, runs=20)
    assert one.draw_prob == swarm.draw_prob == 1.0
    assert swarm.mean_survivors[0] >= 0.93 * one.mean_survivors[0]  # 0.96 now, 0.89 without the fix


# The fights the work rule newly sends to swarm mode (D-50). 200 runs each keeps them cheap; the
# 600-run table in docs/swarm-validation.md is the real +/-0.03 evidence, this pins a gross break.
@pytest.mark.parametrize(
    ("label", "attacker", "defender", "na", "nb"),
    [
        ("150 v 150 wolves", "wolf", "wolf", 150, 150),
        ("200 v 200 wolves", "wolf", "wolf", 200, 200),
        ("50 cats v 1 elephant", "cat", "elephant", 50, 1),
        ("100 cats v 1 elephant", "cat", "elephant", 100, 1),
    ],
)
def test_other_fights_sent_to_swarm_mode_by_their_work_agree_too(
    monkeypatch, label, attacker, defender, na, nb
):
    sheets = {
        "wolf": wolf(),
        "cat": small_cat(),
        "elephant": elephant(),
    }
    pair = [sheets[attacker], sheets[defender]]
    assert _fight(pair, na, nb), label  # they really are sent to swarm mode
    one, swarm = both(monkeypatch, pair, na, nb, runs=200)
    assert abs(swarm.win_prob[0] - one.win_prob[0]) <= 0.08, label  # 200 runs: noise about 0.07
