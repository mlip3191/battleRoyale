"""#301: the deciding-factor analysis runs every variant in the baseline's swarm mode, so a variant
differs from the baseline in one factor only. The "numbers" variant changes the head counts on
purpose and chooses its own mode."""

import pytest

from app.models.stats import StatName
from app.simulation import engine
from app.simulation.decide import decide
from app.simulation.engine import run
from tests.property.sim_helpers import load_sheet, make_sheet, matchup_of


def elephant():
    return make_sheet(
        "elephant", mass_kg=5000, size_m=3.2, top_speed_mps=11, attack_force_n=20000,
        attacks_per_s=0.5, reach_m=2.0, armor_0_1=0.5,
    )  # fmt: skip


def small_cat():
    return make_sheet(
        "cat", mass_kg=4.5, size_m=0.46, top_speed_mps=13, attack_force_n=80,
        attacks_per_s=2.0, reach_m=0.2, armor_0_1=0.05, aggression_0_1=1.0,
    )  # fmt: skip


def modes_used(monkeypatch, sheets, na, nb):
    """(baseline's mode, mode forced on each variant run, in order) for one explained run."""
    calls = []
    real = engine._simulate

    def spy(matchup, sh, ks, seed, runs, use_terrain=True, swarm=None):
        counts = tuple(f.count for f in matchup.fighters)
        calls.append((counts, swarm))
        return real(matchup, sh, ks, seed, runs, use_terrain, swarm)

    monkeypatch.setattr(engine, "_simulate", spy)
    run(matchup_of(na, nb), sheets, runs=40, explain=True)
    baseline = calls[0]
    return (
        baseline[1],
        [swarm for counts, swarm in calls[1:] if counts == baseline[0]],
        [swarm for counts, swarm in calls[1:] if counts != baseline[0]],
    )


@pytest.mark.parametrize(
    ("sheets", "na", "nb", "expected_mode"),
    [
        ([small_cat(), elephant()], 150, 1, True),  # swarm by the work rule (D-50)
        ([load_sheet("stat-sheet-gray-wolf.json"), elephant()], 30, 2, False),  # one by one
    ],
)
def test_every_variant_but_numbers_runs_in_the_baselines_mode(
    monkeypatch, sheets, na, nb, expected_mode
):
    baseline, variants, numbers = modes_used(monkeypatch, sheets, na, nb)
    assert baseline is expected_mode
    assert variants and all(mode is expected_mode for mode in variants)
    assert numbers == [None]  # the numbers variant chooses its own mode


def test_a_variant_that_would_cross_the_work_budget_stays_in_the_baselines_mode(monkeypatch):
    """Equalizing the stats of 150 cats and an elephant moves the fight across SWARM_WORK_BUDGET
    on its own, which used to put the variant in a different engine from the baseline."""
    calls = []
    real = engine._simulate

    def spy(matchup, sh, ks, seed, runs, use_terrain=True, swarm=None):
        decided = swarm if swarm is not None else engine._swarm_for(matchup, sh, ks, use_terrain)
        calls.append((tuple(f.count for f in matchup.fighters), decided))
        return real(matchup, sh, ks, seed, runs, use_terrain, swarm)

    monkeypatch.setattr(engine, "_simulate", spy)
    run(matchup_of(150, 1), [small_cat(), elephant()], runs=40, explain=True)
    same_counts = [mode for counts, mode in calls if counts == (150, 1)]
    assert len(same_counts) > 2 and len(set(same_counts)) == 1


def eagle():
    return make_sheet(
        "eagle", mass_kg=5.0, size_m=0.9, top_speed_mps=30, attack_force_n=300,
        attacks_per_s=1.0, reach_m=0.3, armor_0_1=0.05, aggression_0_1=1.0,
    )  # fmt: skip


def test_a_variant_far_over_the_work_budget_is_skipped_not_run_one_by_one(monkeypatch):
    """#341: 50 eagles v 2 elephants is one by one (work about 2,000), but giving the eagles an
    elephant's mass makes a fight with about 6,000. At the real cutoff the worst real case ran 30 s
    one by one; here the cutoff is lowered so a stand-in fight shows the same thing."""
    monkeypatch.setattr(engine.c, "VARIANT_WORK_CUTOFF", 2.0, raising=False)
    cutoff = 2.0 * engine.c.SWARM_WORK_BUDGET
    ran = []
    real = engine._simulate

    def spy(matchup, sh, ks, seed, runs, use_terrain=True, swarm=None):
        if swarm is False:
            ran.append(engine.expected_work(engine._central_sides(matchup, sh, ks, use_terrain)))
        return real(matchup, sh, ks, seed, runs, use_terrain, swarm)

    monkeypatch.setattr(engine, "_simulate", spy)
    result = run(matchup_of(50, 2), [eagle(), elephant()], runs=40, explain=True)
    assert len(ran) > 3 and max(ran) <= cutoff  # no one-by-one run is far past the budget
    assert result.deciding_factor_explainer


def test_the_baselines_mode_still_applies_to_every_variant_that_is_run(monkeypatch):
    monkeypatch.setattr(engine.c, "VARIANT_WORK_CUTOFF", 2.0, raising=False)
    baseline, variants, numbers = modes_used(monkeypatch, [eagle(), elephant()], 50, 2)
    assert baseline is False and variants and all(mode is False for mode in variants)


def test_nothing_measured_because_every_factor_was_skipped_says_so_without_naming_one():
    sheets = [eagle(), elephant()]
    matchup = matchup_of(5, 5)
    base = engine._simulate(matchup, sheets, (1.0, 1.0), 1, 40, swarm=False)
    decision = decide(matchup, sheets, base, lambda *args, **kwargs: None)
    assert decision.explainer == "Not every factor could be tested for a fight this big."


def test_a_variant_exactly_at_the_cutoff_runs_and_just_above_it_is_skipped(monkeypatch):
    sheets, matchup = [eagle(), elephant()], matchup_of(50, 2)
    monkeypatch.setattr(engine, "expected_work", lambda sides: 8000.0)
    assert not engine._variant_too_slow(matchup, sheets, (1.0, 1.0), True)
    monkeypatch.setattr(engine, "expected_work", lambda sides: 8000.1)
    assert engine._variant_too_slow(matchup, sheets, (1.0, 1.0), True)


def test_a_partly_skipped_analysis_does_not_claim_nothing_mattered():
    """#348 review: if the skipped factor was the decisive one and every measured factor is
    small, the text must not say "no single stat was decisive" or "wins comfortably"."""
    sheets = [elephant(), eagle()]
    matchup = matchup_of(1, 30)
    base = engine._simulate(matchup, sheets, (1.0, 1.0), 1, 40, swarm=False)
    mass = sheets[0].stats[StatName.MASS].value

    def simulate(m, sh, terrain, n, scaled=True, **kwargs):
        return None if sh[0].stats[StatName.MASS].value != mass else base[:n]

    unmeasured = "Not every factor could be tested for a fight this big."
    assert decide(matchup, sheets, base, simulate).explainer == unmeasured
    measured_all = decide(matchup, sheets, base, lambda m, sh, t, n, scaled=True, **k: base[:n])
    assert measured_all.explainer != unmeasured
