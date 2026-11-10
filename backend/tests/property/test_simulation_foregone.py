"""Certain results are shortcut exactly, and long hopeless fights stay cheap."""

import random
import time

from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import (
    DRAW,
    _foregone,
    _starts,
    _templates,
    run,
    run_once,
)
from app.simulation.fair import fair_fight
from app.simulation.rng import run_rng
from tests.property.sim_helpers import make_dragon, make_sheet, matchup_of

WEAPONS = [["teeth"], ["claws"], ["weapon_ranged"], ["ramming"], ["crushing"], ["spines"], ["none"]]


def random_sheet(rng: random.Random, tag: str):
    """A fighter that is often feeble, huge, or stopped, so many fights are foregone."""
    if rng.random() < 0.2:  # mythical abilities: regeneration and breath take their own paths
        return make_dragon(
            rng.choice([["regeneration"], ["breath_weapon"], ["regeneration", "breath_weapon"]]),
            name=tag,
            mass_kg=rng.choice([5.0, 800.0, 5000.0]),
            attack_force_n=rng.choice([2.0, 3000.0, 20000.0]),
        )
    return make_sheet(
        tag,
        spread=rng.choice([0.0, 0.2, 0.5]),
        habitat=rng.choice(["land", "land", "water", "air"]),
        body=rng.choice(["living", "machine", "inert"]),
        weapons=rng.choice(WEAPONS),
        mass_kg=rng.choice([0.2, 5, 80, 5000, 600_000]),
        size_m=rng.choice([0.05, 0.5, 2.0, 12.0]),
        top_speed_mps=rng.choice([0.0, 3.0, 15.0]),
        attack_force_n=rng.choice([0.0, 2.0, 80.0, 3000.0]),
        attacks_per_s=rng.choice([0.0, 0.5, 3.0]),
        reach_m=rng.choice([0.0, 0.5, 2.0]),
        armor_0_1=rng.choice([0.0, 0.5, 0.9]),
        endurance_s=rng.choice([5.0, 90.0, 400.0, 5000.0]),
        aggression_0_1=rng.choice([0.0, 0.5, 1.0]),
        group_tactics_0_1=rng.choice([0.0, 0.8]),
    )


def test_a_foregone_result_matches_the_full_simulation_exactly():
    """The bound is exact: when it says 'certain', simulating gives the identical result."""
    rng = random.Random(2026)
    checked = 0
    for i in range(400):
        a, b = random_sheet(rng, f"a{i}"), random_sheet(rng, f"b{i}")
        matchup = matchup_of(
            rng.choice([1, 2, 6, 250, 1000]),
            rng.choice([1, 3, 12, 300]),
            terrain=rng.choice(list(Terrain)),
        )
        stream = run_rng(7, i)
        sides = _templates(matchup, [a, b], stream, (1.0, 1.0))
        if max(s.count for s in sides) > c.SWARM_THRESHOLD:
            assert _foregone(sides, _starts(sides)) is None  # swarm mode is never shortcut
            continue
        if _foregone(sides, _starts(sides)) is None:
            continue
        checked += 1
        fast = run_once(sides, matchup.terrain, run_rng(7, i + 10_000))  # shortcut allowed
        full = run_once(sides, matchup.terrain, run_rng(7, i + 10_000), record_events=True)
        assert (fast.winner, fast.survivors, fast.duration_s) == (
            full.winner,
            full.survivors,
            full.duration_s,
        ), f"case {i}: the shortcut and the full simulation disagree"
    assert checked >= 40  # the generator really does produce foregone fights


def test_a_machine_that_stops_in_a_hopeless_fight_loses_at_its_operating_time():
    tank = make_sheet(
        "tank",
        body="machine",
        weapons=["ramming"],
        mass_kg=3,
        endurance_s=100,
        attack_force_n=0,
        spread=0.0,
    )
    boulder = make_sheet(
        "boulder",
        body="inert",
        weapons=["none"],
        mass_kg=1_000_000,
        attack_force_n=0,
        attacks_per_s=0,
        top_speed_mps=0,
        spread=0.0,
    )
    matchup = matchup_of(5, 5)
    sides = _templates(matchup, [tank, boulder], run_rng(1, 0), (1.0, 1.0))
    assert _foregone(sides, _starts(sides)) == (1, 100.0)
    result = run(matchup, [tank, boulder], runs=50, explain=False)
    assert result.outcome == "win_1" and result.mean_duration_s == 100.0


def test_spines_that_really_hurt_are_always_simulated():
    cactus = make_sheet(
        "cactus",
        body="inert",
        weapons=["spines"],
        mass_kg=1_000_000,
        attack_force_n=300,
        attacks_per_s=0.0,
        top_speed_mps=0,
        spread=0.0,
    )
    wolf = make_sheet("wolf", mass_kg=40, attack_force_n=2.0)
    sides = _templates(matchup_of(1, 1), [wolf, cactus], run_rng(1, 0), (1.0, 1.0))
    assert _foregone(sides, _starts(sides)) is None


def test_a_hopeless_stalemate_is_cheap_even_with_many_fast_attackers():
    """150 feeble attackers hitting a huge object for 600 s used to cost millions of events."""
    gnat = make_sheet("gnat", mass_kg=0.001, attack_force_n=1.0, attacks_per_s=10.0, spread=0.0)
    mountain = make_sheet(
        "mountain",
        body="inert",
        weapons=["none"],
        mass_kg=5e9,
        size_m=500,
        attack_force_n=0,
        attacks_per_s=0,
        top_speed_mps=0,
        spread=0.0,
    )
    start = time.perf_counter()
    result = run(matchup_of(150, 5), [gnat, mountain], runs=1000, explain=False)
    assert (
        time.perf_counter() - start < 10.0
    )  # about 0.5 s with the shortcut, minutes without; slack for slow CI
    assert result.outcome == "draw" and result.mean_duration_s == c.MAX_FIGHT_S


def test_the_fair_fight_search_stays_cheap_when_attackers_just_run_out_of_time():
    """Machines that never dent an object used to make each probe cost tens of seconds."""
    machine = make_sheet(
        "drone",
        body="machine",
        weapons=["crushing"],
        mass_kg=0.2,
        size_m=0.01,
        top_speed_mps=0.1,
        attack_force_n=800,
        endurance_s=589,
        spread=0.3,
    )
    rock = make_sheet(
        "rock",
        body="inert",
        weapons=["spines"],
        mass_kg=500_000,
        size_m=13,
        top_speed_mps=0,
        attack_force_n=0,
        attacks_per_s=3.4,
        spread=0.3,
    )
    matchup = matchup_of(10, 50, terrain=Terrain.WATER)
    start = time.perf_counter()
    result = run(matchup, [machine, rock], runs=100)
    found = fair_fight(matchup, [machine, rock], result)
    assert time.perf_counter() - start < 6.0
    assert found.count is None  # a stalemate or no fair count; the point is the speed


def test_draw_constant_is_used_for_certain_stalemates():
    gnat = make_sheet("gnat", mass_kg=0.001, attack_force_n=1.0, spread=0.0)
    mountain = make_sheet(
        "mountain",
        body="inert",
        weapons=["none"],
        mass_kg=5e9,
        attack_force_n=0,
        attacks_per_s=0,
        top_speed_mps=0,
        spread=0.0,
    )
    sides = _templates(matchup_of(1, 1), [gnat, mountain], run_rng(1, 0), (1.0, 1.0))
    assert _foregone(sides, _starts(sides)) == (DRAW, c.MAX_FIGHT_S)


def test_the_shortcut_is_never_taken_when_a_side_is_above_the_swarm_threshold():
    # Swarm mode acts in coarse steps, so the per-interval bound is not exact there: 300 archers
    # against a wall at the edge of the bound used to be called a draw but won in the full run.
    archer = make_sheet("archer", weapons=["weapon_ranged"], reach_m=8, attack_force_n=2.0)
    wall = make_sheet(
        "wall", body="inert", weapons=["none"], mass_kg=5e6, size_m=10, attack_force_n=0,
        attacks_per_s=0, top_speed_mps=0, spread=0.0,
    )  # fmt: skip
    matchup = matchup_of(300, 1)
    sides = _templates(matchup, [archer, wall], run_rng(1, 0), (1.0, 1.0))
    assert _foregone(sides, _starts(sides)) is None


def test_two_machines_that_both_stop_en_route_in_swarm_mode_the_first_to_stop_loses():
    # 250 machines with 5 s of operating time against one with 7 s: one by one, the 5 s side loses
    # at its exact endurance. Swarm mode used to zero both at the same step (a mutual wipe-out).
    slow = make_sheet(
        "slow", body="machine", weapons=["ramming"], mass_kg=3, endurance_s=5,
        attack_force_n=0, top_speed_mps=0.4, spread=0.0,
    )  # fmt: skip
    lasting = make_sheet(
        "lasting", body="machine", weapons=["ramming"], mass_kg=3, endurance_s=7,
        attack_force_n=0, top_speed_mps=0.4, spread=0.0,
    )  # fmt: skip
    m = matchup_of(250, 1)
    for k in range(5):
        rng = run_rng(8, k)
        sides = _templates(m, [slow, lasting], rng, (1.0, 1.0))
        # Recording events runs the real swarm simulation (the shortcut would also get this right).
        outcome = run_once(sides, m.terrain, rng, record_events=True)
        assert outcome.winner == 1 and outcome.survivors == (0, 1)
        assert outcome.duration_s <= 5.0 + c.TICK_S  # at its operating time, not a step later
        stops = [e for e in outcome.events if e.text_hint.startswith("out of action")]
        assert [(e.side, e.group_size) for e in stops] == [(0, 250)]


def test_machines_with_the_same_operating_time_in_swarm_mode_are_a_coin_flip():
    twin = make_sheet(
        "twin", body="machine", weapons=["ramming"], mass_kg=3, endurance_s=5,
        attack_force_n=0, top_speed_mps=0.4, spread=0.0,
    )  # fmt: skip
    m = matchup_of(250, 250)
    winners = set()
    for k in range(12):
        rng = run_rng(9, k)
        sides = _templates(m, [twin, twin], rng, (1.0, 1.0))
        winners.add(run_once(sides, m.terrain, rng, record_events=True).winner)
    assert winners == {0, 1}


def test_an_inert_fighter_never_moves_even_if_its_sheet_lists_a_speed():
    def boulder(speed: float):
        return make_sheet(
            "boulder", body="inert", weapons=["crushing"], mass_kg=500, size_m=1.0,
            top_speed_mps=speed, attack_force_n=5000, attacks_per_s=1.0, reach_m=1.0, spread=0.0,
        )  # fmt: skip

    goose = make_sheet(
        "goose", mass_kg=4, size_m=0.8, top_speed_mps=0, attack_force_n=40, spread=0.0,
        aggression_0_1=0.0,
    )  # fmt: skip
    moving = run(matchup_of(1, 1), [boulder(5), goose], runs=50, explain=False)
    still = run(matchup_of(1, 1), [boulder(0), goose], runs=50, explain=False)
    assert still.win_prob[0] == 0.0  # a boulder that stays put never reaches the goose
    assert moving.win_prob == still.win_prob
