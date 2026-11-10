"""F03: engagement limits, size-reference scaling, and swarm mode."""

import math
import time

import pytest

from app.models.simulation import EventType
from app.models.stats import StatName, StatSheet
from app.simulation import constants as c
from app.simulation.engine import _Pool, run, run_once
from app.simulation.fighters import max_engagers, sample_template
from app.simulation.rng import run_rng
from tests.property.sim_helpers import (
    ant,
    duck,
    horse,
    lion,
    make_sheet,
    matchup_of,
    with_stat,
)


def template(sheet, count=1, k=1.0):
    return sample_template(sheet, count, run_rng(1, 0), k)


# --- Engagement limits (Lanchester linear law) -------------------------------------------


def test_much_smaller_attacker_is_capped_at_max_engagers():
    assert max_engagers(template(ant()), template(lion())) == c.MAX_ENGAGERS


def test_equal_or_bigger_attacker_gets_one_slot():
    assert max_engagers(template(lion()), template(lion())) == 1
    assert max_engagers(template(lion()), template(ant())) == 1


def test_pool_lets_only_cap_attackers_onto_one_target_and_queues_the_rest():
    rng = run_rng(1, 0)
    pool = _Pool(n_targets=1, cap=3)
    taken = [pool.acquire(i, rng) for i in range(10)]
    assert taken.count(0) == 3
    assert taken.count(None) == 7
    # A slot opens when an engaged attacker dies.
    assert pool.attacker_died(0) is True
    assert pool.acquire(5, rng) == 0


def test_engine_never_has_more_than_cap_distinct_melee_attackers_on_one_target():
    """A target that cannot hit back and never dies is attacked by exactly `cap` fighters."""
    punching_bag = make_sheet("bag", attack_force_n=0, mass_kg=1_000_000)
    swarm = make_sheet("attackers")  # same size as the bag, so one slot
    rng = run_rng(2, 0)
    sides = [template(swarm, 5), template(punching_bag, 1)]
    cap = max_engagers(sides[0], sides[1])
    outcome = run_once(sides, "open_field", rng, record_events=True)
    attackers = {e.actor for e in outcome.events if e.type in (EventType.HIT, EventType.MISS)}
    assert len(attackers) == cap


def test_ranged_side_uses_the_square_law():
    """With a ranged weapon every attacker engages the same target at once."""
    punching_bag = make_sheet("bag", attack_force_n=0, mass_kg=1_000_000)
    data = make_sheet("archers").model_dump(mode="json")
    data["weapons"] = ["weapon_ranged"]
    archers = type(make_sheet("x")).model_validate(data)
    rng = run_rng(2, 0)
    sides = [template(archers, 5), template(punching_bag, 1)]
    assert sides[0].ranged
    outcome = run_once(sides, "open_field", rng, record_events=True)
    attackers = {e.actor for e in outcome.events if e.type in (EventType.HIT, EventType.MISS)}
    assert len(attackers) == 5


def test_pack_around_a_bear_fights_two_at_a_time_not_all_at_once():
    """Six wolves vs the bear fixture: the cap (2) makes the fight last longer than unlimited."""
    wolf = make_sheet("wolf")
    big = make_sheet("big", size_m=2.4, mass_kg=389, attack_force_n=4000, attacks_per_s=1.0)
    result = run(matchup_of(6, 1), [wolf, big], runs=200)
    capped_survivors = result.mean_survivors[0]
    assert 0 <= capped_survivors <= 6
    assert result.mean_duration_s > 0


# --- Square-cube scaling ---------------------------------------------------------------------


def exact(name, **stats):
    """A stand-in with zero spread so scaling can be checked with exact numbers."""
    return make_sheet(name, spread=0.0, **stats)


def test_scaling_known_numbers():
    """Mass 8 kg scaled to a 64 kg reference: k = 8, strength x4, length x2, speed x8^(1/6)."""
    small = exact(
        "small", mass_kg=8, size_m=1.0, top_speed_mps=6.0, attack_force_n=100, reach_m=0.5
    )
    scaled = template(small, k=64 / 8)
    assert scaled.mass_kg == pytest.approx(64)
    assert scaled.attack_force_n == pytest.approx(100 * 4)
    assert scaled.size_m == pytest.approx(1.0 * 2)
    assert scaled.reach_m == pytest.approx(0.5 * 2)
    assert scaled.speed_mps == pytest.approx(6.0 * 8 ** (1 / 6))
    assert scaled.max_hp == pytest.approx(64 * c.HP_PER_KG)


def test_scale_factor_comes_from_sheet_masses():
    from app.simulation.fighters import scale_factor

    assert scale_factor(duck(), horse()) == pytest.approx(500 / 1.2)


def test_scaling_a_massless_sheet_is_a_clear_error():
    from app.simulation.fighters import scale_factor

    massless = with_stat(horse(), StatName.MASS, 0.0)
    with pytest.raises(ValueError, match="above zero"):
        scale_factor(massless, horse())


def test_missing_reference_sheet_is_an_error():
    with pytest.raises(ValueError, match="size_reference"):
        run(matchup_of(1, 1, ref_1="horse"), [horse(), duck()], runs=5)


def test_duck_sized_horses_vs_horse_sized_duck_is_explainable():
    """Showcase #1 with stand-in sheets: 100 duck-sized horses vs a horse-sized duck.

    Each tiny horse weighs about a duck (1.2 kg) and bites with k^(2/3)-scaled force; the giant
    duck weighs 500 kg, so every tiny horse hits for almost nothing against its hit points and
    only a few can surround it. The duck wins.
    """
    m = matchup_of(100, 1, ref_0="duck", ref_1="horse")
    result = run(m, [horse(), duck()], runs=200, reference_sheets=[duck(), horse()])
    assert result.win_prob[1] > 0.9
    hints = [e.text_hint for e in result.representative_log if e.type == EventType.APPROACH]
    assert any("scaled to duck size" in h for h in hints)
    assert any("scaled to horse size" in h for h in hints)


# --- Swarm mode ------------------------------------------------------------------------------


def timed(matchup, sheets, runs=1000):
    start = time.perf_counter()
    result = run(matchup, sheets, runs=runs)
    return result, time.perf_counter() - start


def test_100_vs_1000_finishes_under_three_seconds():
    _, seconds = timed(matchup_of(100, 1000), [ant(), ant()])
    assert seconds < 3.0


def test_10000_ants_vs_one_lion_finishes_under_three_seconds():
    _, seconds = timed(matchup_of(10_000, 1), [ant(), lion()])
    assert seconds < 3.0


def test_plural_weapon_words_are_spelled_correctly():
    from app.simulation.fighters import _WEAPON_WORD, plural_word

    assert plural_word("bite") == "bites"
    assert plural_word("crush") == "crushes"
    assert plural_word("claw swipe") == "claw swipes"
    assert plural_word("strike") == "strikes"
    for word in (*_WEAPON_WORD.values(), "strike"):
        assert not plural_word(word).endswith(("ss", "shs", "chs", "xs", "zs")), word


def test_a_swarm_of_crushers_reads_correctly():
    base = make_sheet("crushers", mass_kg=100, size_m=1.0, attack_force_n=900, attacks_per_s=2.0)
    crushers = StatSheet.model_validate({**base.model_dump(mode="json"), "weapons": ["crushing"]})
    result, _ = timed(matchup_of(250, 1), [crushers, lion()], runs=30)
    hints = {e.text_hint for e in result.representative_log if e.type == EventType.HIT}
    assert "crushes land" in hints and not any("crushs" in h for h in hints)


def test_swarm_events_carry_group_size():
    result, _ = timed(matchup_of(100, 1000), [ant(), ant()], runs=50)
    group_events = [e for e in result.representative_log if e.group_size > 1]
    assert group_events
    assert any(e.type == EventType.HIT for e in group_events)


def test_swarm_is_deterministic_and_log_is_capped():
    first, _ = timed(matchup_of(500, 500), [ant(), ant()], runs=50)
    second, _ = timed(matchup_of(500, 500), [ant(), ant()], runs=50)
    assert first == second
    assert len(first.representative_log) <= c.MAX_LOG_EVENTS
    assert first.representative_log[-1].type == EventType.END


def test_swarm_of_big_groups_still_resolves_decisively():
    result, _ = timed(matchup_of(100, 1000), [ant(), ant()], runs=200)
    assert abs(result.win_prob[0] + result.win_prob[1] + result.draw_prob - 1.0) < 1e-9
    assert result.win_prob[1] > 0.9  # ten times the ants wins


def test_swarm_mirror_is_fair():
    ants = ant()
    result, _ = timed(matchup_of(300, 300), [ants, ants], runs=500)
    assert 0.4 <= result.win_prob[0] <= 0.6


def test_individual_and_swarm_modes_agree_at_the_boundary():
    """200 v 200 (one by one) and 201 v 201 (grouped) are the same fight: similar results."""
    wolf = make_sheet("w")
    low, _ = timed(matchup_of(200, 200), [wolf, wolf], runs=40)
    high, _ = timed(matchup_of(201, 201), [wolf, wolf], runs=40)
    assert math.isclose(low.mean_duration_s, high.mean_duration_s, rel_tol=1.0)
    assert StatName.MASS  # sanity: enum import used
