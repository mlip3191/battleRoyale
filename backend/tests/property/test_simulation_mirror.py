"""F02: hypothesis property test for mirror matches (kept apart from the other engine tests)."""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models.stats import StatName
from app.models.terrain import Terrain
from app.simulation.engine import run
from tests.property.sim_helpers import load_sheet, matchup, with_stat


@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.floats(min_value=20.0, max_value=500.0))
def test_probabilities_sum_to_one_and_mirror_match_is_fair(mass):
    """A mirror match is a coin flip, so its win share is pure sampling noise.

    One 1,000-run draw has a standard deviation of about 0.016, which makes the 0.45-0.55 band
    only 3.2 sigma wide: roughly 1 example in 600 would fail by chance. So each example runs the
    fight in two neutral terrains (different random seeds, identical physics) and averages them.
    """
    sheet = with_stat(load_sheet("stat-sheet.json"), StatName.MASS, mass)
    shares = []
    for terrain in (Terrain.ARENA, Terrain.OPEN_FIELD):
        result = run(
            matchup().model_copy(update={"terrain": terrain}),
            [sheet, sheet],
            runs=1000,
            explain=False,
        )
        assert abs(result.win_prob[0] + result.win_prob[1] + result.draw_prob - 1.0) < 1e-9
        shares.append(result.win_prob[0])
    assert 0.45 <= sum(shares) / len(shares) <= 0.55
