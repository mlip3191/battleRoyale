"""The replay log keeps room for knock-outs, even in crowded fights (issue #90)."""

from app.models.simulation import EventType
from app.simulation import constants as c
from app.simulation.engine import run
from tests.property.sim_helpers import make_sheet, matchup_of


def test_a_crowded_fight_still_shows_fighters_going_down():
    wolf = make_sheet("wolf", mass_kg=40, size_m=1.0, attack_force_n=700)
    result = run(matchup_of(150, 150), [wolf, wolf], runs=3)
    log = result.representative_log
    kinds = [e.type for e in log]
    assert len(log) <= c.MAX_LOG_EVENTS
    assert kinds[-1] == EventType.END
    assert kinds.count(EventType.KO) >= 50
    # Hits and misses stop early; knock-outs keep going after them.
    last_flow = max(i for i, k in enumerate(kinds) if k in (EventType.HIT, EventType.MISS))
    assert EventType.KO in kinds[last_flow:]


def test_the_same_seed_gives_the_same_log():
    wolf = make_sheet("wolf", mass_kg=40, size_m=1.0, attack_force_n=700)
    a = run(matchup_of(150, 150), [wolf, wolf], runs=3)
    b = run(matchup_of(150, 150), [wolf, wolf], runs=3)
    assert a.representative_log == b.representative_log
