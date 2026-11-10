"""F03 hypothesis property: more fighters never make a side meaningfully worse."""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.simulation.engine import run
from tests.property.sim_helpers import lion, make_sheet, matchup_of

NOISE = 0.02


def win_share(count: int, foe_count: int) -> float:
    pack = make_sheet("pack", mass_kg=40, size_m=1.2)
    result = run(matchup_of(count, foe_count), [pack, lion()], runs=500, explain=False)
    return result.win_prob[0]


@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    st.integers(min_value=1, max_value=12),
    st.integers(min_value=2, max_value=10),
    st.integers(min_value=1, max_value=2),
)
def test_adding_fighters_never_lowers_win_probability_beyond_noise(base, extra, foes):
    assert win_share(base + extra, foes) >= win_share(base, foes) - NOISE
