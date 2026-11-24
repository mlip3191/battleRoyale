"""#575: every logged event carries each side's hit points, so a health bar can drain per hit."""

from app.models.matchup import FighterRequest, Matchup
from app.models.simulation import EventType, FightEvent, SimulationResult
from app.models.terrain import Terrain
from app.research.seed_fighters import find_seed_sheet
from app.simulation.engine import run
from tests.property.sim_helpers import duck, lion, matchup_of

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


def check_log(result: SimulationResult) -> None:
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
            assert event.hp_left[side] <= previous[side]  # these fighters never heal
        if event.type == EventType.HIT:
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
