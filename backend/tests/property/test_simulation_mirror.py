"""F02: hypothesis property test for mirror matches (kept apart from the other engine tests)."""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models.stats import StatName
from app.simulation.engine import run
from tests.property.sim_helpers import load_sheet, matchup, with_stat


@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.floats(min_value=20.0, max_value=500.0))
def test_probabilities_sum_to_one_and_mirror_match_is_fair(mass):
    sheet = with_stat(load_sheet("stat-sheet.json"), StatName.MASS, mass)
    result = run(matchup(), [sheet, sheet], runs=1000)
    assert abs(result.win_prob[0] + result.win_prob[1] + result.draw_prob - 1.0) < 1e-9
    assert 0.45 <= result.win_prob[0] <= 0.55
