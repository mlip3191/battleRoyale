"""#575: every logged event carries each side's hit points, so a health bar can drain per hit."""

from app.models.matchup import FighterRequest, Matchup
from app.models.simulation import EventType, FightEvent, SimulationResult
from app.models.terrain import Terrain
from app.research.seed_fighters import find_seed_sheet
from app.simulation.engine import OUT_OF_ACTION, run
from tests.property.sim_helpers import (
    ant,
    duck,
    horse,
    lion,
    load_sheet,
    make_dragon,
    make_sheet,
    matchup_of,
)
from tests.property.test_simulation_venom import target, viper

CLOSING = (EventType.END, EventType.STALEMATE)
# Hit points and damage are each logged to 0.1, so a drop can read up to 0.15 off its damage.
ROUNDING = 0.15 + 1e-9


# The live bug: "a grizzly bear vs 6 gray wolves in a forest", from the seed sheets.
def bear_vs_wolves() -> SimulationResult:
    fighters = [
        FighterRequest(entity="grizzly bear", raw="a grizzly bear"),
        FighterRequest(entity="gray wolf", count=6, raw="6 gray wolves"),
    ]
    sheets = [find_seed_sheet("grizzly bear"), find_seed_sheet("gray wolf")]
    assert all(sheets)
    fight = Matchup(fighters=fighters, terrain=Terrain.FOREST, raw_text="bear vs wolves")
    return run(fight, sheets, runs=50)


# The hit side of a HIT is the other side: the striker's foe (spines report the defender).
def hurt_side(event: FightEvent) -> int:
    return 1 - event.side


def check_log(result: SimulationResult, heals: bool = False) -> None:
    log = result.representative_log
    assert result.start_hp is not None and min(result.start_hp) > 0
    first = log[0].hp_left
    assert first == result.start_hp  # nobody is hurt as the sides close in
    previous = first
    for event in log:
        if event.hp_left is None:
            # Only closing events and the "more go down" summaries are added after the fight.
            assert event.type in CLOSING or event.text_hint == "more go down"
            continue
        for side in (0, 1):
            assert 0.0 <= event.hp_left[side] <= result.start_hp[side]
            if heals:
                continue  # a regenerating side's total can rise between events
            assert event.hp_left[side] <= previous[side]
        if event.type == EventType.HIT and not heals:
            side = hurt_side(event)
            assert event.hp_left[side] < previous[side]  # the hit is already counted
            assert previous[side] - event.hp_left[side] <= event.damage + ROUNDING  # never more
        previous = event.hp_left
    loser = {"win_0": 1, "win_1": 0}.get(result.outcome)
    if loser is not None and not any(e.type == EventType.FLEE for e in log):
        assert previous[loser] == 0.0  # a side wiped out has no hit points left


def test_the_bears_hit_points_drop_with_the_first_bite_long_before_anyone_falls():
    result = bear_vs_wolves()
    log = result.representative_log
    first_bite = next(e for e in log if e.type == EventType.HIT and e.side == 1)
    first_fall = next(i for i, e in enumerate(log) if e.type == EventType.KO)
    assert log.index(first_bite) < first_fall
    assert first_bite.hp_left[0] < result.start_hp[0]  # the bar would drain right here
    drop = result.start_hp[0] - first_bite.hp_left[0]
    assert abs(drop - first_bite.damage) <= ROUNDING
    check_log(result)


def test_a_one_by_one_log_tracks_hit_points_event_by_event():
    check_log(run(matchup_of(100, 5), [duck(), lion()], runs=20))


def test_a_swarm_log_counts_each_group_hit_before_it_is_logged():
    check_log(run(matchup_of(1000, 1), [duck(), lion()], runs=20))


def cactus():
    return make_sheet(
        "cactus", body="inert", mass_kg=100, size_m=1.5, top_speed_mps=0, attack_force_n=300,
        attacks_per_s=0.0, weapons=["spines"], armor_0_1=0.3,
    )  # fmt: skip


def test_spines_that_jab_back_are_counted_one_by_one_and_in_a_swarm():
    wolf = load_sheet("stat-sheet-gray-wolf.json")
    for count in (1, 300):  # 300 runs in swarm mode
        result = run(matchup_of(count, 1), [wolf, cactus()], runs=20, explain=False)
        assert any(e.text_hint == "spines jab back" for e in result.representative_log)
        check_log(result)


def test_a_machine_swarm_that_stops_has_no_hit_points_left():
    drones = make_sheet(
        "drones", body="machine", mass_kg=2, size_m=0.5, top_speed_mps=10, attack_force_n=1,
        attacks_per_s=1.0, endurance_s=2, spread=0.0,
    )  # fmt: skip
    rock = make_sheet(
        "rock", body="inert", mass_kg=1_000_000, size_m=5, top_speed_mps=0, attack_force_n=0,
        attacks_per_s=0, weapons=["none"],
    )  # fmt: skip
    result = run(matchup_of(250, 1), [drones, rock], runs=20, explain=False)
    stop = [e for e in result.representative_log if e.text_hint == OUT_OF_ACTION][-1]
    assert stop.hp_left[0] == 0.0
    check_log(result)


def test_a_venom_death_takes_the_victims_hit_points():
    result = run(matchup_of(1, 1), [viper(), target()], runs=50, explain=False)
    last_fall = [e for e in result.representative_log if e.type == EventType.KO][-1]
    assert last_fall.text_hint == "succumbs to venom" and last_fall.hp_left == (0.0, 0.0)


def test_a_no_contest_has_no_hit_points():
    rock = make_sheet("rock", body="inert", mass_kg=50, size_m=0.4, top_speed_mps=0,
                      attack_force_n=0, attacks_per_s=0, weapons=["none"])  # fmt: skip
    sword = make_sheet("sword", body="inert", mass_kg=1.5, size_m=1.0, top_speed_mps=0,
                       attack_force_n=0, attacks_per_s=0, weapons=["none"])  # fmt: skip
    result = run(matchup_of(1, 1), [rock, sword], runs=20)
    assert result.outcome == "no_contest" and result.start_hp is None
    assert [e.hp_left for e in result.representative_log] == [None]


def test_a_crowd_of_tiny_fighters_still_drains_visibly():
    # 10,000 ants hold about 0.3 hit points in all; rounding to 0.1 showed only 0.3 or 0.2.
    result = run(matchup_of(10_000, 1), [ant(), horse()], runs=20, explain=False)
    assert result.start_hp[0] > 0
    ants = {e.hp_left[0] for e in result.representative_log if e.hp_left}
    assert len(ants) > 2
    check_log(result)


def test_a_regenerating_fighter_stays_within_its_hit_points():
    troll = make_dragon(["regeneration"], name="troll")
    result = run(matchup_of(1, 3), [troll, lion()], runs=20, explain=False)
    check_log(result, heals=True)
