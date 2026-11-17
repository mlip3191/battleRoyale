"""#359 (D-63): showcase battle 1 fits the Simulate stage limit, checked without a clock.

Wall-clock timing can't be checked reliably in CI, so this pins what decides the cost instead:
battle 1 runs one by one with its analysis intact, and the stage limit keeps about 2x headroom
over the slowest laptop time measured for it.
"""

from app.models.matchup import Matchup
from app.models.stats import StatSheet
from app.models.terrain import Terrain
from app.pipeline.stages import STAGE_BUDGETS_S
from app.simulation import constants as c
from app.simulation import engine
from scripts.showcase_dry_run import seed_sheet
from tests.property.sim_helpers import matchup_of

# engine.run for battle 1 on a slower Windows laptop at ENGINE_VERSION 12 (Gunnar, #359).
SLOWEST_LAPTOP_S = 3.7


# Battle 1 exactly as scripts/showcase_dry_run.py builds it.
def battle_one() -> tuple[Matchup, list[StatSheet], tuple[float, float]]:
    horse, duck = seed_sheet("horse"), seed_sheet("duck")
    matchup = matchup_of(100, 1, ref_0="duck", ref_1="horse", terrain=Terrain.OPEN_FIELD)
    sheets = [horse, duck]
    return matchup, sheets, engine.scale_factors(matchup, sheets, [duck, horse])


def test_battle_one_runs_one_by_one_with_its_analysis_intact() -> None:
    matchup, sheets, ks = battle_one()
    central = engine._central_sides(matchup, sheets, ks)
    work = engine.expected_work(central)
    assert not engine.use_swarm(central)  # one by one: the costly mode
    assert 900 < work < 1200  # about 1,000, the size of fight the limit was measured on
    assert work <= c.VARIANT_WORK_CUTOFF * c.SWARM_WORK_BUDGET  # no analysis variant is skipped


def test_the_simulate_limit_keeps_2x_headroom_over_the_slowest_laptop() -> None:
    # Was 3 s, under the 3.7 s measured, so battle 1 failed at Simulate (#359).
    assert STAGE_BUDGETS_S["simulate"] >= 2 * SLOWEST_LAPTOP_S
