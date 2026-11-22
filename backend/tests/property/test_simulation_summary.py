"""F05: the deciding factor, its explainer, and summary()."""

import json
import re
import time

import pytest

from app.models.matchup import Matchup
from app.models.stats import StatName, StatSheet
from app.models.terrain import Terrain
from app.simulation.engine import run
from app.simulation.summary import summary
from tests.property.sim_helpers import (
    FIXTURES,
    ant,
    duck,
    horse,
    lion,
    load_sheet,
    make_sheet,
    matchup_of,
)

NUMBER = re.compile(r"\d+(?:\.\d+)?")


def inputs_of(matchup: Matchup, sheets: list[StatSheet]) -> list[float]:
    """Every number the explainer is allowed to quote: stat values and fighter counts."""
    numbers = [float(f.count) for f in matchup.fighters]
    for sheet in sheets:
        numbers += [stat.value for stat in sheet.stats.values()]
    return numbers


def numbers_in(text: str, sheets: list[StatSheet]) -> list[float]:
    for sheet in sheets:  # names may contain digits; they are inputs too
        text = text.replace(sheet.display_name, "")
    return [float(n) for n in NUMBER.findall(text)]


def assert_only_input_numbers(result, matchup, sheets):
    allowed = inputs_of(matchup, sheets)
    for number in numbers_in(result.deciding_factor_explainer, sheets):
        assert any(abs(number - a) <= 0.005 * max(abs(a), 1e-12) + 1e-12 for a in allowed), (
            f"{number} is not an input (explainer: {result.deciding_factor_explainer})"
        )


def test_every_result_has_a_deciding_factor_and_explainer():
    w = make_sheet("w")
    cases = [
        (matchup_of(1, 1), [w, w]),  # mirror: too close to call
        (matchup_of(1, 1), [make_sheet("big", mass_kg=400), w]),
        (matchup_of(10_000, 1), [ant(), lion()]),  # stalemate
        (
            matchup_of(1, 1, terrain=Terrain.WATER),
            [make_sheet("e", habitat="air"), make_sheet("s", habitat="water")],
        ),
    ]
    for matchup, sheets in cases:
        result = run(matchup, sheets, runs=300)
        assert result.deciding_factor
        assert result.deciding_factor_explainer.strip()


def test_size_dominated_matchup_reports_mass_or_size():
    big = make_sheet("big", mass_kg=400, size_m=2.4)
    small = make_sheet("small", mass_kg=40, size_m=1.0)
    matchup = matchup_of(1, 1)
    result = run(matchup, [big, small])
    assert result.deciding_factor in (StatName.MASS, StatName.SIZE)
    assert_only_input_numbers(result, matchup, [big, small])


def test_swarm_matchup_reports_numbers():
    w = make_sheet("w")
    matchup = matchup_of(300, 1)
    result = run(matchup, [w, w])
    assert result.deciding_factor == "numbers"
    assert "Numbers decided it" in result.deciding_factor_explainer
    assert_only_input_numbers(result, matchup, [w, w])


def test_small_group_numbers_advantage_reports_numbers():
    w = make_sheet("w")
    result = run(matchup_of(6, 1), [w, w])
    assert result.deciding_factor == "numbers"


def test_behavioral_deciding_factor_says_it_rests_on_an_assumption():
    bold = make_sheet("bold", aggression_0_1=1.0)
    timid = make_sheet("timid", aggression_0_1=0.05)
    matchup = matchup_of(1, 1)
    result = run(matchup, [bold, timid])
    assert result.deciding_factor == StatName.AGGRESSION
    assert "rests on an assumption" in result.deciding_factor_explainer
    assert_only_input_numbers(result, matchup, [bold, timid])


def test_measured_stat_does_not_claim_an_assumption():
    big = make_sheet("big", mass_kg=400, size_m=2.4)
    small = make_sheet("small", mass_kg=40, size_m=1.0)
    result = run(matchup_of(1, 1), [big, small])
    assert "assumption" not in result.deciding_factor_explainer


def test_terrain_can_be_the_deciding_factor():
    shark = make_sheet("shark", habitat="water", mass_kg=300, attack_force_n=3000)
    cat = lion()
    result = run(matchup_of(1, 1, terrain=Terrain.WATER), [shark, cat], runs=300)
    assert result.deciding_factor == "terrain"
    assert "water" in result.deciding_factor_explainer


def test_a_size_reference_battle_credits_the_scaling_not_a_raw_stat():
    """100 duck-sized horses vs a horse-sized duck: size decided it, because of the scaling."""
    matchup = matchup_of(100, 1, ref_0="duck", ref_1="horse", terrain=Terrain.OPEN_FIELD)
    sheets = [horse(), duck()]
    result = run(matchup, sheets, runs=300, reference_sheets=[duck(), horse()])
    text = result.deciding_factor_explainer
    assert result.deciding_factor == StatName.MASS
    assert "after scaling" in text
    assert "scaled to duck size" in text and "scaled to horse size" in text
    assert_only_input_numbers(result, matchup, sheets)


def test_a_nearly_irrelevant_scaling_is_still_reported_as_a_valid_factor():
    """Whatever wins the sensitivity check, the result must hold a displayable factor."""
    from app.simulation.decide import decide
    from app.simulation.engine import DRAW, RunOutcome

    def outcomes(draws):
        return [RunOutcome(DRAW if k < draws else 0, (1, 0), 10.0, []) for k in range(100)]

    matchup = matchup_of(1, 1, ref_0="horse")
    sheets = [duck(), horse()]

    def simulate(m, sh, terrain, n, scaled=True):
        return outcomes(0 if scaled else 1)  # only dropping the scaling changes anything, barely

    decision = decide(matchup, sheets, outcomes(0), simulate, (2.0, 1.0))
    assert decision.factor in set(StatName) | {"numbers", "terrain", "habitat", "abilities"}
    assert decision.factor == StatName.MASS


def test_a_battle_without_size_references_never_mentions_scaling():
    big = make_sheet("big", mass_kg=400, size_m=2.4)
    small = make_sheet("small", mass_kg=40, size_m=1.0)
    result = run(matchup_of(1, 1), [big, small], runs=300)
    assert "scaling" not in result.deciding_factor_explainer.lower()


def test_mirror_match_is_too_close_to_call():
    w = make_sheet("w")
    result = run(matchup_of(1, 1), [w, w], runs=300)
    assert "Too close to call" in result.deciding_factor_explainer


def test_stalemate_is_explained_as_a_stalemate():
    result = run(matchup_of(10_000, 1), [ant(), lion()], runs=100)
    assert result.outcome == "draw"
    assert "stalemate" in result.deciding_factor_explainer.lower()


def test_explainer_quotes_only_input_numbers_for_the_contract_fixtures():
    bear = load_sheet("stat-sheet.json")
    wolf = load_sheet("stat-sheet-gray-wolf.json")
    matchup = Matchup.model_validate(json.loads((FIXTURES / "matchup.json").read_text("utf-8")))
    result = run(matchup, [bear, wolf])
    assert_only_input_numbers(result, matchup, [bear, wolf])


def test_deciding_factor_is_reproducible():
    big = make_sheet("big", mass_kg=400, size_m=2.4)
    small = make_sheet("small", mass_kg=40, size_m=1.0)
    first = run(matchup_of(1, 1), [big, small], runs=300)
    second = run(matchup_of(1, 1), [big, small], runs=300)
    assert first == second


def test_simulate_plus_deciding_factor_finishes_under_five_seconds_for_one_v_one():
    bear = load_sheet("stat-sheet.json")
    wolf = load_sheet("stat-sheet-gray-wolf.json")
    start = time.perf_counter()
    run(matchup_of(1, 1), [bear, wolf], runs=1000)
    assert time.perf_counter() - start < 5.0


def test_explain_false_skips_the_analysis():
    w = make_sheet("w")
    result = run(matchup_of(1, 1), [w, w], runs=50, explain=False)
    assert result.deciding_factor_explainer == "Deciding factor not computed."


# --- summary() ---------------------------------------------------------------------------------


def test_summary_gives_the_numbers_the_ui_and_announcer_need():
    big = make_sheet("big", mass_kg=400, size_m=2.4)
    small = make_sheet("small", mass_kg=40, size_m=1.0)
    result = run(matchup_of(1, 1), [big, small], runs=300)
    s = summary(result, ("Big", "Small"))
    assert s.favorite == 0 and s.favorite_name == "Big"
    assert s.win_pct[0] > 90 and s.win_pct[0] + s.win_pct[1] + s.draw_pct == pytest.approx(
        100, abs=0.2
    )
    assert s.duration_s == round(result.mean_duration_s, 1)
    assert s.survivors == (round(result.mean_survivors[0], 1), round(result.mean_survivors[1], 1))
    assert s.deciding_factor_text == result.deciding_factor_explainer
    assert s.outcome == "win_0"


def test_summary_has_no_favorite_for_a_draw_or_no_contest():
    draw = run(matchup_of(10_000, 1), [ant(), lion()], runs=50)
    assert summary(draw, ("Ant", "Lion")).favorite is None
    contest = run(
        matchup_of(1, 1, terrain=Terrain.WATER),
        [make_sheet("e", habitat="air"), make_sheet("s", habitat="water")],
        runs=10,
    )
    s = summary(contest, ("E", "S"))
    assert s.outcome == "no_contest" and s.favorite is None
    assert s.deciding_factor == "habitat"


# --- #120: the numbers and terrain explainers say who they helped ---------------------------------


def _explained(key, helped, matchup, sheets):
    from app.simulation.decide import _explain

    return _explain(key, matchup, sheets, 0, helped)


def test_numbers_explainer_has_a_variant_for_when_the_crowd_did_not_help_the_favorite():
    cats, wolf = make_sheet("cats"), make_sheet("wolf")
    matchup = matchup_of(1, 30)  # the favorite (side 0) is the one outnumbered
    helped = _explained("numbers", True, matchup, [cats, wolf])
    against = _explained("numbers", False, matchup, [cats, wolf])
    assert "Numbers decided it" in helped and "in spite of" not in helped
    assert "in spite of the head count" in against and "decided it" not in against
    for text in (helped, against):  # same numbers, both inputs
        assert sorted(numbers_in(text, [cats, wolf])) == [1.0, 30.0]


def test_terrain_explainer_has_a_variant_for_when_the_ground_did_not_help_the_favorite():
    shark, cat = make_sheet("shark", habitat="water"), make_sheet("cat")
    matchup = matchup_of(1, 1, terrain=Terrain.WATER)
    helped = _explained("terrain", True, matchup, [shark, cat])
    against = _explained("terrain", False, matchup, [shark, cat])
    assert "The ground decided it" in helped and "suits the Shark" in helped
    assert "in spite of the ground" in against and "suits the Cat" in against
    assert "decided it" not in against
    for text in (helped, against):
        assert numbers_in(text, [shark, cat]) == []


def test_a_favorite_that_wins_against_the_ground_is_not_said_to_be_helped_by_it():
    from app.simulation.decide import _explain

    shark, cat = make_sheet("shark", habitat="water"), make_sheet("cat")
    matchup = matchup_of(1, 1, terrain=Terrain.WATER)
    # the cat is side 0 here, so the water favors side 1 (the shark) and not the favorite
    text = _explain("terrain", matchup, [cat, shark], 0, False)
    assert text.startswith("Cat came out ahead in spite of the ground")


# --- #458: a side with a count above 1 reads as a plural in every deciding-factor sentence ------


def test_a_crowd_reads_as_a_plural_in_the_numbers_sentence_and_a_single_one_is_unchanged():
    wolf, bear = make_sheet("Gray wolf"), make_sheet("Grizzly bear")
    text = _explained("numbers", True, matchup_of(6, 1), [wolf, bear])
    assert "6 gray wolves against 1 Grizzly bear" in text
    alone = _explained("numbers", True, matchup_of(1, 1), [wolf, bear])
    assert "1 Gray wolf against 1 Grizzly bear" in alone  # a count of 1 is unchanged


def test_a_crowd_reads_as_a_plural_in_the_scaling_sentence() -> None:
    from app.simulation.decide import _explain_scaling

    wolf, bear = make_sheet("Gray wolf"), make_sheet("Grizzly bear")
    fight = matchup_of(6, 1)
    fight.fighters[0].size_reference = "bear"
    text = _explain_scaling(fight, [wolf, bear], 0, True)
    assert "6 gray wolves (" in text and "6 Gray wolf" not in text


# --- #365: size that helps the smaller side says so, and how ------------------------------------


def test_size_that_helps_a_smaller_crowd_says_the_smaller_side_and_how():
    wolf = make_sheet("gray wolf", size_m=1.6)
    bear = make_sheet("grizzly bear", size_m=2.4)
    matchup = matchup_of(6, 1)  # the favorite (side 0) is the smaller side, and a crowd
    text = _explained(StatName.SIZE, True, matchup, [wolf, bear])
    assert text.startswith("Size decided it, in the smaller side's favor:")
    # #458: a crowd is plural. make_sheet marks every stat an estimate, so both carry the label.
    assert "6 gray wolves (1.6 m, estimate) against 1 Grizzly bear (2.4 m, estimate)" in text
    assert "easier target" in text and "fit around it" in text
    assert sorted(numbers_in(text, [wolf, bear])) == [1.0, 1.6, 2.4, 6.0]


def test_size_that_helps_a_lone_smaller_fighter_skips_the_crowd_reason():
    small, big = make_sheet("small", size_m=1.0), make_sheet("big", size_m=2.4)
    text = _explained(StatName.SIZE, True, matchup_of(1, 1), [small, big])
    assert text == (
        "Size decided it, in the smaller side's favor: "
        "Small (1 m, estimate) against Big (2.4 m, estimate). "
        "A bigger body is an easier target."
    )


def test_size_that_helps_the_bigger_side_keeps_the_plain_sentence():
    big, small = make_sheet("big", size_m=2.4), make_sheet("small", size_m=1.0)
    text = _explained(StatName.SIZE, True, matchup_of(1, 6), [big, small])
    assert text == "Size decided it: Big (2.4 m, estimate) against Small (1 m, estimate)."


def test_weight_that_helps_the_lighter_side_says_the_lighter_side():
    light, heavy = make_sheet("light", mass_kg=40), make_sheet("heavy", mass_kg=400)
    text = _explained(StatName.MASS, True, matchup_of(1, 1), [light, heavy])
    assert text == (
        "Size decided it, in the lighter side's favor: "
        "Light (40 kg, estimate) against Heavy (400 kg, estimate)."
    )


def test_a_crowd_against_a_slightly_bigger_foe_does_not_claim_more_attackers_fit():
    # (2.0 / 1.6) ** 2 = 1.56: max_engagers still lets only one attacker in (#390 review).
    small, big = make_sheet("small", size_m=1.6), make_sheet("big", size_m=2.0)
    text = _explained(StatName.SIZE, True, matchup_of(6, 1), [small, big])
    assert text == (
        "Size decided it, in the smaller side's favor: "
        "6 smalls (1.6 m, estimate) against 1 Big (2 m, estimate). "
        "A bigger body is an easier target."
    )


def test_a_size_reference_keeps_the_plain_sentence():
    # A scaled fighter's sheet size isn't the size it fought at, so "smaller" could be wrong.
    small, big = make_sheet("small", size_m=1.0), make_sheet("big", size_m=2.4)
    text = _explained(StatName.SIZE, True, matchup_of(1, 1, ref_0="horse"), [small, big])
    assert text == "Size decided it: Small (1 m, estimate) against Big (2.4 m, estimate)."


# --- #552: an estimated number is labeled in the deciding-factor sentence ----------------------


def _with_estimate(sheet, key, is_estimate):
    """The same sheet with one stat marked as an estimate (or as sourced)."""
    stats = dict(sheet.stats)
    stats[key] = stats[key].model_copy(update={"is_estimate": is_estimate})
    return sheet.model_copy(update={"stats": stats})


def _strength_pair(seal_estimate, gorilla_estimate, seal_force=7000):
    key = StatName.ATTACK_FORCE
    seal = _with_estimate(make_sheet("navy seal", attack_force_n=seal_force), key, seal_estimate)
    gorilla = _with_estimate(make_sheet("gorilla", attack_force_n=1020), key, gorilla_estimate)
    return [seal, gorilla]


def test_a_strength_that_is_an_estimate_is_labeled_in_the_sentence():
    text = _explained(StatName.ATTACK_FORCE, True, matchup_of(1, 1), _strength_pair(True, False))
    assert text == "Strength decided it: Navy seal (7000 N, estimate) against Gorilla (1020 N)."


def test_an_estimate_is_labeled_when_the_favorite_won_in_spite_of_the_stat():
    sheets = _strength_pair(True, False, seal_force=700)
    text = _explained(StatName.ATTACK_FORCE, False, matchup_of(1, 1), sheets)
    assert "Navy seal (700 N, estimate) against Gorilla (1020 N)" in text


def test_an_estimate_on_the_other_side_is_labeled_too():
    text = _explained(StatName.ATTACK_FORCE, True, matchup_of(1, 1), _strength_pair(False, True))
    assert text == "Strength decided it: Navy seal (7000 N) against Gorilla (1020 N, estimate)."


def test_a_sourced_number_stays_plain():
    text = _explained(StatName.ATTACK_FORCE, True, matchup_of(1, 1), _strength_pair(False, False))
    assert text == "Strength decided it: Navy seal (7000 N) against Gorilla (1020 N)."


# --- #474: the deciding-factor sentence names the verdict's favorite, not the sample's ----------


def _outcomes(wins_0: int, wins_1: int):
    from app.simulation.engine import RunOutcome

    out = [RunOutcome(0, (1, 0), 10.0, []) for _ in range(wins_0)]
    return out + [RunOutcome(1, (0, 1), 10.0, []) for _ in range(wins_1)]


def test_the_sentence_names_the_full_run_favorite_when_the_first_runs_disagree() -> None:
    from app.simulation.decide import decide

    alpha = make_sheet("Alpha", size_m=1.0)
    bravo = make_sheet("Bravo", size_m=3.0)
    # 1,000 runs: side 0 wins 520 and side 1 wins 480, so the verdict is Alpha. But the first 200
    # (the sample the factor analysis re-runs) go 80 to 120 for Bravo.
    base = _outcomes(80, 120) + _outcomes(440, 360)
    assert sum(o.winner == 0 for o in base) > sum(o.winner == 1 for o in base)
    assert sum(o.winner == 0 for o in base[:200]) < sum(o.winner == 1 for o in base[:200])

    def simulate(variant, sheets, terrain, n, scaled, **extra):
        return _outcomes(0, n)  # whatever is changed, Bravo takes every fight

    decision = decide(matchup_of(1, 1), [alpha, bravo], base, simulate)
    assert "Bravo came out ahead" not in decision.explainer
    assert "Alpha" in decision.explainer


def test_an_agreeing_sample_gives_the_same_sentence_as_before() -> None:
    from app.simulation.decide import decide

    alpha = make_sheet("Alpha", size_m=1.0)
    bravo = make_sheet("Bravo", size_m=3.0)
    base = _outcomes(150, 50) + _outcomes(600, 200)  # the sample and the full run both favor Alpha

    def simulate(variant, sheets, terrain, n, scaled, **extra):
        return _outcomes(0, n)

    decision = decide(matchup_of(1, 1), [alpha, bravo], base, simulate)
    assert "Alpha" in decision.explainer and "Bravo came out ahead" not in decision.explainer


# --- #479: the stalemate and "wins comfortably" checks read the full run, not the sample ---------


def _mixed(side0: int, side1: int, draws: int):
    from app.simulation.engine import DRAW, RunOutcome

    out = [RunOutcome(0, (1, 0), 10.0, []) for _ in range(side0)]
    out += [RunOutcome(1, (0, 1), 10.0, []) for _ in range(side1)]
    return out + [RunOutcome(DRAW, (1, 1), 10.0, []) for _ in range(draws)]


def _same_as_base(base):
    """A factor re-run that changes nothing, so no factor 'decides' and the fallback text shows."""

    def simulate(variant, sheets, terrain, n, scaled, **extra):
        return base[:n]

    return simulate


def _decide_text(base) -> str:
    from app.simulation.decide import decide

    alpha, bravo = make_sheet("Alpha", size_m=1.0), make_sheet("Bravo", size_m=3.0)
    return decide(matchup_of(1, 1), [alpha, bravo], base, _same_as_base(base)).explainer


def test_a_draw_heavy_sample_does_not_make_a_stalemate_when_the_full_run_has_a_winner() -> None:
    # The first 200 runs are all draws, the other 800 go to Alpha: the full run is not a stalemate.
    base = _mixed(0, 0, 200) + _mixed(800, 0, 0)
    assert "stalemate" not in _decide_text(base).lower()


def test_a_real_stalemate_is_still_called_one() -> None:
    base = _mixed(50, 50, 900)  # mostly draws over every run
    assert "stalemate" in _decide_text(base).lower()


def test_wins_comfortably_follows_the_full_run_not_the_sample() -> None:
    # The sample is Alpha 195 of 200 (0.975) but the full run is Alpha 850 of 1,000 (0.85).
    base = _mixed(195, 5, 0) + _mixed(655, 145, 0)
    assert "comfortably" not in _decide_text(base)
    # And the reverse: a 0.85 sample (170 of 200) inside a 0.95 full run (950 of 1,000).
    base = _mixed(170, 30, 0) + _mixed(780, 20, 0)
    assert "comfortably" in _decide_text(base)


# --- #552 review: the label also shows in the smaller-side, lighter-side and scaling sentences ---


def test_the_smaller_side_sentence_labels_only_the_estimated_size():
    key = StatName.SIZE
    small = _with_estimate(make_sheet("small", size_m=1.0), key, True)
    big = _with_estimate(make_sheet("big", size_m=2.4), key, False)
    text = _explained(key, True, matchup_of(1, 1), [small, big])
    assert "Small (1 m, estimate) against Big (2.4 m)." in text


def test_the_lighter_side_sentence_labels_only_the_estimated_mass():
    key = StatName.MASS
    light = _with_estimate(make_sheet("light", mass_kg=40), key, False)
    heavy = _with_estimate(make_sheet("heavy", mass_kg=400), key, True)
    text = _explained(key, True, matchup_of(1, 1), [light, heavy])
    assert text.endswith("Light (40 kg) against Heavy (400 kg, estimate).")


def test_the_scaling_sentence_labels_an_estimated_mass():
    from app.simulation.decide import _explain_scaling

    key = StatName.MASS
    duck_ = _with_estimate(make_sheet("duck", mass_kg=2), key, False)
    horse_ = _with_estimate(make_sheet("horse", mass_kg=500), key, True)
    matchup = matchup_of(1, 1, ref_0="horse")
    text = _explain_scaling(matchup, [duck_, horse_], 0, True)
    assert "Duck (2 kg normally, scaled to horse size)" in text
    assert "Horse (500 kg, estimate)" in text
    sized = _explain_scaling(matchup, [horse_, duck_], 1, True)  # the scaled side, estimated
    assert "Horse (500 kg normally, scaled to horse size, estimate)" in sized


def test_a_strength_estimated_on_both_sides_is_labeled_on_both():
    text = _explained(StatName.ATTACK_FORCE, True, matchup_of(1, 1), _strength_pair(True, True))
    assert text == (
        "Strength decided it: Navy seal (7000 N, estimate) against Gorilla (1020 N, estimate)."
    )
