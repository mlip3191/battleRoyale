"""The replay log keeps room for knock-outs, even in crowded fights (issue #90)."""

from app.models.simulation import EventType
from app.simulation import constants as c
from app.simulation.engine import _templates, run, run_once
from app.simulation.rng import run_rng
from tests.property.sim_helpers import make_sheet, matchup_of


def test_a_crowded_fight_still_shows_fighters_going_down():
    wolf = make_sheet("wolf", mass_kg=40, size_m=1.0, attack_force_n=700)
    result = run(matchup_of(150, 150), [wolf, wolf], runs=3)
    log = result.representative_log
    kinds = [e.type for e in log]
    assert len(log) <= c.MAX_LOG_EVENTS
    assert kinds[-1] == EventType.END
    assert kinds.count(EventType.KO) >= 140
    # Hits and misses stop early; knock-outs keep going after them.
    last_flow = max(i for i, k in enumerate(kinds) if k in (EventType.HIT, EventType.MISS))
    assert EventType.KO in kinds[last_flow:]


def test_the_same_seed_gives_the_same_log():
    wolf = make_sheet("wolf", mass_kg=40, size_m=1.0, attack_force_n=700)
    a = run(matchup_of(150, 150), [wolf, wolf], runs=3)
    b = run(matchup_of(150, 150), [wolf, wolf], runs=3)
    assert a.representative_log == b.representative_log


def test_every_death_is_logged_when_the_fight_is_small_enough_to_fit():
    wolf = make_sheet("wolf", mass_kg=40, size_m=1.0, attack_force_n=700)
    m = matchup_of(40, 40)
    for k in range(5):
        rng = run_rng(3, k)
        sides = _templates(m, [wolf, wolf], rng, (1.0, 1.0))
        outcome = run_once(sides, m.terrain, rng, record_events=True)
        kos = sum(e.type == EventType.KO for e in outcome.events)
        assert len(outcome.events) <= c.MAX_LOG_EVENTS - c.CLOSING_EVENTS  # never hit the cap
        assert kos == 80 - sum(outcome.survivors)


def test_knock_outs_that_do_not_fit_are_summed_so_every_death_is_counted():
    wolf = make_sheet("wolf", mass_kg=40, size_m=1.0, attack_force_n=700)
    m = matchup_of(150, 150)
    for k in range(5):
        rng = run_rng(4, k)
        sides = _templates(m, [wolf, wolf], rng, (1.0, 1.0))
        outcome = run_once(sides, m.terrain, rng, record_events=True)
        fell = 300 - sum(outcome.survivors)
        kos = [e for e in outcome.events if e.type == EventType.KO]
        assert sum(e.group_size or 1 for e in kos) == fell
        assert len(outcome.events) <= c.MAX_LOG_EVENTS
        assert outcome.events[-1].type == EventType.END
        summaries = [e for e in kos if e.text_hint == "more go down"]
        assert summaries and all(
            outcome.events.index(e) > outcome.events.index(kos[0]) for e in summaries
        )
        times = [e.t for e in outcome.events]
        assert times == sorted(times)
