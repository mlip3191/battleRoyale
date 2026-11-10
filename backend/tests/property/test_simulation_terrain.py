"""F04: terrain, habitat, retreat and flee behavior, and group tactics."""

import statistics

import pytest

from app.models.simulation import EventType
from app.models.stats import Habitat
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import _templates, run, run_once
from app.simulation.fighters import apply_terrain, sample_template
from app.simulation.rng import run_rng
from app.simulation.terrain import MODIFIERS, can_engage
from tests.property.sim_helpers import lion, make_sheet, matchup_of

SHARK = dict(
    habitat="water", mass_kg=500, size_m=4.0, top_speed_mps=10, attack_force_n=5000,
    attacks_per_s=1.0, reach_m=0.5,
)  # fmt: skip
EAGLE = dict(
    habitat="air", mass_kg=5, size_m=0.9, top_speed_mps=30, attack_force_n=300,
    attacks_per_s=1.0, reach_m=0.3,
)  # fmt: skip


def shark():
    return make_sheet("shark", **SHARK)


def eagle():
    return make_sheet("eagle", **EAGLE)


# --- The terrain table --------------------------------------------------------------------


def test_terrain_table_covers_every_terrain_and_habitat_pair():
    for terrain in Terrain:
        for habitat in Habitat:
            assert (terrain, habitat) in MODIFIERS, f"missing {terrain.value} x {habitat.value}"
    assert len(MODIFIERS) == len(Terrain) * len(Habitat)
    assert all(m.speed > 0 and m.attack > 0 and m.hit > 0 for m in MODIFIERS.values())


def test_stranded_and_deep_water_penalties_are_heavy():
    rng = run_rng(1, 0)
    fish = sample_template(shark(), 1, rng)
    cat = sample_template(lion(), 1, rng)
    assert apply_terrain(fish, Terrain.OPEN_FIELD).speed_mps < 0.2 * fish.speed_mps
    assert apply_terrain(cat, Terrain.WATER).speed_mps < 0.3 * cat.speed_mps
    shallow = apply_terrain(cat, Terrain.SHORELINE)
    assert 0.5 * cat.speed_mps < shallow.speed_mps < cat.speed_mps  # weak, not crippled


def test_shark_vs_lion_flips_the_favorite_between_land_and_water():
    on_land = run(matchup_of(1, 1, terrain=Terrain.OPEN_FIELD), [shark(), lion()], runs=300)
    in_water = run(matchup_of(1, 1, terrain=Terrain.WATER), [shark(), lion()], runs=300)
    assert on_land.win_prob[1] > 0.9  # the lion
    assert in_water.win_prob[0] > 0.9  # the shark


# --- no_contest ---------------------------------------------------------------------------


def test_eagle_vs_shark_in_water_is_no_contest():
    result = run(matchup_of(1, 1, terrain=Terrain.WATER), [eagle(), shark()], runs=100)
    assert result.outcome == "no_contest"
    assert result.win_prob == (0.0, 0.0) and result.draw_prob == 0.0
    assert result.mean_duration_s == 0.0
    last = result.representative_log[-1]
    assert last.type == EventType.END and "no contest" in last.text_hint
    assert "can't reach each other" in result.deciding_factor_explainer


def test_eagle_vs_shark_is_a_fight_where_the_shark_is_stranded_or_in_the_shallows():
    assert can_engage(Terrain.SHORELINE, Habitat.AIR, Habitat.WATER)
    result = run(matchup_of(1, 1, terrain=Terrain.OPEN_FIELD), [eagle(), shark()], runs=100)
    assert result.outcome != "no_contest"
    # The stranded penalty bites: the same shark kills the eagle more slowly out of the water
    # than it would if it were a land animal (it is still the favorite: it outweighs the eagle).
    landlubber = make_sheet("shark", **{**SHARK, "habitat": "land"})
    at_home = run(matchup_of(1, 1, terrain=Terrain.OPEN_FIELD), [eagle(), landlubber], runs=100)
    assert result.mean_duration_s > at_home.mean_duration_s * 1.5


# --- Behavior: morale, retreat, flee ---------------------------------------------------------


def retreat_times(aggression_0: float, aggression_1: float, n: int = 300) -> dict[int, list[float]]:
    """When each side retreats across many runs of an even fight."""
    a = make_sheet("a", aggression_0_1=aggression_0, mass_kg=100, attack_force_n=1500)
    b = make_sheet("b", aggression_0_1=aggression_1, mass_kg=100, attack_force_n=1500)
    m = matchup_of(1, 1)
    times: dict[int, list[float]] = {0: [], 1: []}
    for k in range(n):
        rng = run_rng(5, k)
        sides = _templates(m, [a, b], rng, (1.0, 1.0))
        outcome = run_once(sides, m.terrain, rng, record_events=True)
        for event in outcome.events:
            if event.type == EventType.RETREAT:
                times[event.side].append(event.t)
    return times


def test_timid_side_retreats_earlier_than_an_aggressive_one():
    times = retreat_times(0.1, 0.6)
    assert len(times[0]) >= 20 and len(times[1]) >= 5
    assert statistics.median(times[0]) < statistics.median(times[1])


def test_morale_threshold_rises_with_aggression():
    timid = sample_template(make_sheet("t", aggression_0_1=0.0, spread=0.0), 1, run_rng(1, 0))
    bold = sample_template(make_sheet("b", aggression_0_1=1.0, spread=0.0), 1, run_rng(1, 0))
    middle = sample_template(make_sheet("m", aggression_0_1=0.5, spread=0.0), 1, run_rng(1, 0))
    assert timid.morale == c.MORALE_FLOOR
    assert bold.morale == 1.0
    assert middle.morale == pytest.approx(c.MORALE_FLOOR + c.MORALE_SPAN * 0.5)


def test_fast_timid_fighter_escapes_with_retreat_and_flee_events():
    fast = make_sheet("fast", aggression_0_1=0.1, top_speed_mps=25, mass_kg=60, attack_force_n=500)
    slow = make_sheet("slow", top_speed_mps=8, mass_kg=300, attack_force_n=3000, aggression_0_1=0.9)
    result = run(matchup_of(1, 1), [fast, slow], runs=200)
    kinds = [e.type for e in result.representative_log]
    assert EventType.RETREAT in kinds and EventType.FLEE in kinds
    assert result.outcome == "win_1"  # fleeing counts as a loss for the runner
    assert result.mean_survivors[0] > 0  # ...but the runner survives


def test_slower_retreating_fighter_is_caught_and_never_flees():
    slow = make_sheet("slow", aggression_0_1=0.1, top_speed_mps=5, mass_kg=100, attack_force_n=700)
    fast = make_sheet("fast", top_speed_mps=20, mass_kg=100, attack_force_n=1500, aggression_0_1=1)
    m = matchup_of(1, 1)
    flees = retreats = 0
    for k in range(100):
        rng = run_rng(7, k)
        sides = _templates(m, [slow, fast], rng, (1.0, 1.0))
        outcome = run_once(sides, m.terrain, rng, record_events=True)
        flees += sum(e.type == EventType.FLEE for e in outcome.events)
        retreats += sum(e.type == EventType.RETREAT for e in outcome.events)
    assert retreats > 0 and flees == 0


# --- Morale in swarm mode (more than 200 per side) -------------------------------------------


def swarm_vs_boss(top_speed_mps: float):
    swarm = make_sheet(
        "swarm", aggression_0_1=0.0, mass_kg=20, size_m=0.6, attack_force_n=100,
        top_speed_mps=top_speed_mps,
    )  # fmt: skip
    boss = make_sheet(
        "boss", aggression_0_1=1.0, mass_kg=600, size_m=2.5, attack_force_n=9000,
        attacks_per_s=2.0, top_speed_mps=10, armor_0_1=0.5,
    )  # fmt: skip
    return run(matchup_of(300, 1), [swarm, boss], runs=50)


def test_a_timid_swarm_breaks_and_runs():
    result = swarm_vs_boss(top_speed_mps=6)  # slower than the boss: it breaks but is caught
    kinds = {e.type for e in result.representative_log}
    assert EventType.RETREAT in kinds and EventType.FLEE not in kinds
    assert result.outcome == "win_1"


def test_a_fast_timid_swarm_escapes_and_survives():
    result = swarm_vs_boss(top_speed_mps=25)  # faster than the boss: it gets away
    kinds = [e.type for e in result.representative_log]
    assert EventType.RETREAT in kinds and EventType.FLEE in kinds
    assert kinds.index(EventType.RETREAT) < kinds.index(EventType.FLEE)
    assert result.outcome == "win_1"  # fleeing counts as a loss for the runners
    assert result.mean_survivors[0] > 0  # ...but they are alive


# --- Group tactics ---------------------------------------------------------------------------


def test_group_tactics_raise_a_packs_win_probability():
    big = make_sheet(
        "big", mass_kg=300, size_m=2.2, attack_force_n=1500, attacks_per_s=1.0,
        top_speed_mps=14, aggression_0_1=1.0,
    )  # fmt: skip

    def pack_wins(tactics: float) -> float:
        pack = make_sheet(
            "pack", group_tactics_0_1=tactics, mass_kg=40, size_m=1.0, top_speed_mps=7,
            attack_force_n=700, aggression_0_1=1.0, spread=0.0,
        )  # fmt: skip
        return run(matchup_of(4, 1), [pack, big], runs=500).win_prob[0]

    assert pack_wins(0.9) > pack_wins(0.0) + 0.1
