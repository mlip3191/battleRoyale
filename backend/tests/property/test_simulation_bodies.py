"""F08: machines, inert objects, and mythical abilities."""

import pytest

from app.models.simulation import EventType
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import OUT_OF_ACTION, _starts, _templates, run, run_once
from app.simulation.fighters import apply_terrain, sample_template
from app.simulation.rng import run_rng
from tests.property.sim_helpers import (
    load_sheet,
    make_dragon,
    make_sheet,
    matchup_of,
)

FOE = dict(mass_kg=300, size_m=2.2, attack_force_n=5000, attacks_per_s=1.0)


def toaster():
    return load_sheet("stat-sheet-toaster.json")


def goose():
    return make_sheet(
        "goose", mass_kg=4.0, size_m=0.8, top_speed_mps=7, attack_force_n=100,
        attacks_per_s=1.0, reach_m=0.3,
    )  # fmt: skip


def boulder(**extra):
    return make_sheet(
        "boulder", body="inert", mass_kg=1_000_000, size_m=5, top_speed_mps=0,
        attack_force_n=0, attacks_per_s=0, weapons=["none"], **extra,
    )  # fmt: skip


def truck(**extra):
    kw = dict(
        body="machine", mass_kg=8000, size_m=6.0, top_speed_mps=20, attack_force_n=0,
        weapons=["ramming"], endurance_s=600, armor_0_1=0.5,
    )  # fmt: skip
    kw.update(extra)
    return make_sheet("truck", **kw)


def events_of(sheets, matchup=None, runs=1, seed=3, terrain=Terrain.OPEN_FIELD):
    """Event logs of `runs` single fights (random streams are fixed by seed and run number)."""
    m = matchup or matchup_of(1, 1, terrain=terrain)
    logs = []
    for k in range(runs):
        rng = run_rng(seed, k)
        sides = _templates(m, sheets, rng, (1.0, 1.0))
        logs.append(run_once(sides, m.terrain, rng, record_events=True))
    return logs


# --- Inert objects and machines ---------------------------------------------------------------


def test_toaster_vs_goose_is_never_a_toaster_win():
    result = run(matchup_of(1, 1), [toaster(), goose()], runs=500, explain=False)
    assert result.win_prob[0] == 0.0
    assert result.win_prob[1] > 0.9 or result.draw_prob > 0.0


def test_a_toaster_never_acts():
    for outcome in events_of([toaster(), goose()], runs=20):
        assert not [
            e for e in outcome.events if e.side == 0 and e.type in (EventType.HIT, EventType.MISS)
        ]


def test_rock_vs_sword_is_a_no_contest():
    rock = make_sheet("rock", body="inert", mass_kg=50, size_m=0.4, top_speed_mps=0,
                      attack_force_n=0, attacks_per_s=0, weapons=["none"])  # fmt: skip
    sword = make_sheet("sword", body="inert", mass_kg=1.5, size_m=1.0, top_speed_mps=0,
                       attack_force_n=0, attacks_per_s=0, weapons=["none"])  # fmt: skip
    result = run(matchup_of(1, 1), [rock, sword], runs=100)
    assert result.outcome == "no_contest"
    assert "hurt" in result.representative_log[-1].text_hint
    assert "can hurt the other" in result.deciding_factor_explainer


def test_two_fixed_objects_with_attacks_but_no_reach_are_a_no_contest():
    spiky = dict(body="inert", top_speed_mps=0, attack_force_n=500, attacks_per_s=1.0, reach_m=0.5)
    result = run(matchup_of(1, 1), [make_sheet("a", **spiky), make_sheet("b", **spiky)], runs=50)
    assert result.outcome == "no_contest"


def test_a_side_that_cannot_finish_the_other_in_600_seconds_draws():
    result = run(matchup_of(1, 1), [goose(), boulder()], runs=50, explain=False)
    assert result.outcome == "draw" and result.draw_prob == 1.0
    assert result.mean_duration_s == c.MAX_FIGHT_S


def test_a_machine_never_retreats_or_flees_but_the_same_stats_as_a_living_fighter_do():
    stats = dict(mass_kg=100, attack_force_n=300, aggression_0_1=0.0, top_speed_mps=20)

    def retreats(body):
        sheet = make_sheet("x", body=body, endurance_s=600, **stats)
        foe = make_sheet("foe", **FOE)
        total = 0
        for outcome in events_of([sheet, foe], runs=1000):
            total += sum(
                e.side == 0 and e.type in (EventType.RETREAT, EventType.FLEE)
                for e in outcome.events
            )
        return total

    assert retreats("machine") == 0
    assert retreats("living") > 0  # control: without the machine body it does run away


def test_a_machine_is_out_of_action_when_its_operating_time_runs_out():
    tank = truck(endurance_s=20)
    result = run(matchup_of(1, 1), [tank, boulder()], runs=100)
    assert result.outcome == "win_1"
    knock_outs = [e for e in result.representative_log if e.type == EventType.KO]
    assert [e.text_hint for e in knock_outs] == [OUT_OF_ACTION]
    assert 16 <= knock_outs[0].t <= 24 + c.TICK_S  # endurance is sampled from its 20 s range
    assert result.mean_survivors[0] == 0.0


def test_a_machine_is_not_tired_before_its_time_is_up():
    result = run(matchup_of(1, 1), [truck(endurance_s=600), goose()], runs=50, explain=False)
    assert result.win_prob[0] == 1.0
    assert result.mean_duration_s < 60


def test_machine_swarm_goes_out_of_action_together():
    drones = make_sheet("drones", body="machine", mass_kg=2, size_m=0.5, top_speed_mps=10,
                        attack_force_n=1, attacks_per_s=1.0, endurance_s=2, spread=0.0)  # fmt: skip
    result = run(matchup_of(250, 1), [drones, boulder()], runs=20, explain=False)
    assert result.outcome == "win_1"
    stop = [e for e in result.representative_log if e.type == EventType.KO]
    assert stop and stop[-1].text_hint == OUT_OF_ACTION and stop[-1].group_size == 250


def test_ramming_damage_comes_from_momentum_and_a_fixed_rate():
    sheet = truck(mass_kg=8000, top_speed_mps=20, spread=0.0, attacks_per_s=5.0)
    t = sample_template(sheet, 1, run_rng(1, 0))
    assert t.damage == pytest.approx(c.RAM_DAMAGE_PER_MOMENTUM * 8000 * 20)
    assert t.attacks_per_s == c.RAM_ATTACKS_PER_S  # the sheet's rate is replaced


def test_crushing_uses_a_minimum_speed():
    roller = truck(weapons=["crushing"], mass_kg=10000, top_speed_mps=0.2, spread=0.0)
    t = sample_template(roller, 1, run_rng(1, 0))
    assert t.damage == pytest.approx(c.RAM_DAMAGE_PER_MOMENTUM * 10000 * c.CRUSH_MIN_SPEED_MPS)


def test_spines_hurt_whoever_hits_the_object():
    wolf = load_sheet("stat-sheet-gray-wolf.json")

    def cactus(weapons):
        return make_sheet("cactus", body="inert", mass_kg=100, size_m=1.5, top_speed_mps=0,
                          attack_force_n=300, attacks_per_s=0.0, weapons=weapons,
                          armor_0_1=0.3)  # fmt: skip

    spiny = run(matchup_of(1, 1), [wolf, cactus(["spines"])], runs=300, explain=False)
    smooth = run(matchup_of(1, 1), [wolf, cactus(["none"])], runs=300, explain=False)
    assert spiny.win_prob[0] < smooth.win_prob[0] - 0.1
    hints = [e.text_hint for e in spiny.representative_log]
    assert "spines jab back" in hints


# --- Abilities ------------------------------------------------------------------------------------


def small_dragon(abilities, **stats):
    return make_dragon(abilities, name="dragon-" + "-".join(abilities), mass_kg=3000,
                       attack_force_n=20000, **stats)  # fmt: skip


def test_breath_weapon_raises_win_probability_against_the_same_opponent():
    with_breath = run(
        matchup_of(1, 1), [small_dragon(["breath_weapon"]), truck()], runs=300, explain=False
    )
    without = run(matchup_of(1, 1), [small_dragon([]), truck()], runs=300, explain=False)
    assert with_breath.win_prob[0] > without.win_prob[0] + 0.3


def test_breath_weapon_fires_from_a_distance():
    breathing = sample_template(small_dragon(["breath_weapon"]), 1, run_rng(1, 0))
    clawing = sample_template(small_dragon([]), 1, run_rng(1, 0))
    assert breathing.ranged and breathing.reach_m >= c.BREATH_RANGE_M
    assert not clawing.ranged
    foe = sample_template(truck(), 1, run_rng(1, 1))
    assert _starts([breathing, foe])[0] == 0.0 < _starts([clawing, foe])[0]


def test_regeneration_raises_mean_survival_time():
    foe = make_sheet("foe", **{**FOE, "attack_force_n": 5000})
    regenerating = make_dragon(
        ["regeneration"], name="r", mass_kg=3000, attack_force_n=500, armor_0_1=0.3
    )
    plain = make_dragon([], name="p", mass_kg=3000, attack_force_n=500, armor_0_1=0.3)
    with_regen = run(matchup_of(1, 1), [regenerating, foe], runs=300, explain=False)
    without = run(matchup_of(1, 1), [plain, foe], runs=300, explain=False)
    assert with_regen.mean_duration_s > without.mean_duration_s + 30
    assert with_regen.win_prob[0] > without.win_prob[0]


def test_extra_heads_multiply_the_attack_rate():
    base = sample_template(make_dragon([], name="h0"), 1, run_rng(1, 0), central=True)
    four = sample_template(
        make_dragon(["extra_heads"], heads=4, name="h4"), 1, run_rng(1, 0), central=True
    )
    default = sample_template(
        make_dragon(["extra_heads"], name="hd"), 1, run_rng(1, 0), central=True
    )
    assert four.attacks_per_s == pytest.approx(4 * base.attacks_per_s)
    assert default.attacks_per_s == pytest.approx(c.DEFAULT_HEADS * base.attacks_per_s)


def test_flight_gives_air_rules_and_lets_a_flier_engage_land_fighters():
    walker = make_dragon([], name="walker")
    flier = make_dragon(["flight"], name="flier")
    # Make both land-based on paper so only the ability differs.
    data = walker.model_dump(mode="json") | {"habitat": "land"}
    land_dragon = type(walker).model_validate(data)
    data = flier.model_dump(mode="json") | {"habitat": "land"}
    flying_land_dragon = type(flier).model_validate(data)
    plain = apply_terrain(sample_template(land_dragon, 1, run_rng(1, 0)), Terrain.FOREST)
    flying = apply_terrain(sample_template(flying_land_dragon, 1, run_rng(1, 0)), Terrain.FOREST)
    assert flying.habitat.value == "air" and plain.habitat.value == "land"
    assert flying.speed_mps < plain.speed_mps  # forest hinders fliers more (assumption table)
    # An air fighter fights a land fighter in the open field.
    result = run(matchup_of(1, 1), [flier, truck()], runs=50, explain=False)
    assert result.win_prob[0] + result.win_prob[1] + result.draw_prob == pytest.approx(1.0)
    assert any(e.side == 0 and e.type == EventType.HIT for e in result.representative_log)


def test_a_creature_with_flight_cannot_reach_a_swimmer_in_open_water():
    shark = make_sheet("shark", habitat="water", mass_kg=300)
    result = run(
        matchup_of(1, 1, terrain=Terrain.WATER), [make_dragon(["flight"], name="f"), shark], runs=20
    )
    assert result.outcome == "no_contest"


def test_abilities_can_be_the_deciding_factor():
    result = run(matchup_of(1, 1), [small_dragon(["breath_weapon"]), truck()], runs=1000)
    assert result.deciding_factor == "abilities"
    assert "according to legend" in result.deciding_factor_explainer
    assert "breath weapon" in result.deciding_factor_explainer


def test_a_lopsided_fight_with_no_single_cause_is_called_comfortable_not_close():
    result = run(matchup_of(1, 1), [goose(), toaster()], runs=300)
    assert "too close" not in result.deciding_factor_explainer.lower()
