"""#81 / D-44: venom resolves after the fight, resistance cuts it, results stay explainable."""

from app.models.simulation import EventType
from app.models.stats import StatName
from app.simulation import constants as c
from app.simulation.engine import _foregone, _starts, _templates, run
from app.simulation.rng import run_rng
from tests.property.sim_helpers import make_sheet, matchup_of


def viper():
    """Tough enough to land a few bites before it falls, but a slow, weak biter."""
    return make_sheet(
        "viper", weapons=["venom"], mass_kg=40, size_m=1.0, top_speed_mps=4, attack_force_n=10,
        attacks_per_s=0.2, armor_0_1=0.9, aggression_0_1=1.0, spread=0.0,
    )  # fmt: skip


def target(fighter_id: str | None = None):
    return make_sheet(
        "target", fighter_id=fighter_id, mass_kg=10, size_m=0.7, top_speed_mps=8,
        attack_force_n=900, attacks_per_s=2.0, armor_0_1=0.5, aggression_0_1=1.0, spread=0.0,
    )  # fmt: skip


def draw_share(sheets, runs=200):
    return run(matchup_of(1, 1), sheets, runs=runs, explain=False)


def test_a_poisoned_survivor_dies_after_the_fight_and_it_is_a_draw():
    result = draw_share([viper(), target()])
    # The target kills the viper, but it carries a lethal dose from the bites it took.
    assert result.draw_prob > 0.9
    assert result.mean_survivors[0] == 0.0 and result.mean_survivors[1] < 0.1


def test_resistance_lets_the_survivor_live_and_win():
    resistant = draw_share([viper(), target("honey-badger")])
    assert c.VENOM_RESISTANCE["honey-badger"] >= 0.8
    assert resistant.draw_prob < 0.05
    assert resistant.win_prob[1] > 0.95


def test_without_venom_the_same_fight_is_a_plain_win_for_the_target():
    plain = make_sheet(
        "viper", weapons=["teeth"], mass_kg=40, size_m=1.0, top_speed_mps=4, attack_force_n=10,
        attacks_per_s=0.2, armor_0_1=0.9, aggression_0_1=1.0, spread=0.0,
    )  # fmt: skip
    result = draw_share([plain, target()])
    assert result.draw_prob == 0.0 and result.win_prob[1] > 0.95


def test_the_log_shows_the_survivor_succumbing_after_the_last_blow():
    result = run(matchup_of(1, 1), [viper(), target()], runs=50, explain=False)
    log = result.representative_log
    falls = [e for e in log if e.type == EventType.KO]
    assert [e.text_hint for e in falls][-1] == "succumbs to venom"
    assert falls[-1].t - falls[-2].t >= c.VENOM_ONSET_S - c.TICK_S  # minutes later
    assert log[-1].type == EventType.END and log[-1].t <= c.MAX_FIGHT_S
    assert [e.t for e in log] == sorted(e.t for e in log)


def test_the_shortcut_is_not_taken_when_venom_could_be_lethal():
    # A machine runs out of time, so the fight is otherwise "certain", but a few bites on the
    # other side could still leave a lethal dose: that has to be simulated.
    biter = make_sheet(
        "biter", weapons=["venom"], mass_kg=40, size_m=1.0, top_speed_mps=4, attack_force_n=1,
        attacks_per_s=3.0, spread=0.0,
    )  # fmt: skip
    machine = make_sheet(
        "machine", body="machine", weapons=["ramming"], mass_kg=3, endurance_s=60,
        attack_force_n=0, top_speed_mps=4, armor_0_1=0.9, spread=0.0,
    )  # fmt: skip
    m = matchup_of(1, 1)
    sides = _templates(m, [biter, machine], run_rng(1, 0), (1.0, 1.0))
    assert _foregone(sides, _starts(sides)) is None


def test_the_deciding_factor_names_venom_without_a_new_contract_value():
    result = run(matchup_of(1, 1), [viper(), target()], runs=400)
    assert result.deciding_factor == StatName.ATTACK_FORCE  # D-44: no `venom` value in the contract
    assert "venom" in result.deciding_factor_explainer.lower()
    assert "stalemate" not in result.deciding_factor_explainer.lower()  # a poisoned draw is not one


def test_a_resistant_fighter_is_not_described_as_a_stalemate():
    result = run(matchup_of(1, 1), [viper(), target("honey-badger")], runs=400)
    assert result.outcome == "win_1"
    assert "stalemate" not in result.deciding_factor_explainer.lower()


def test_every_resistance_entry_is_a_share_between_zero_and_one():
    assert all(0.0 < value <= 1.0 for value in c.VENOM_RESISTANCE.values())
