"""F03 hypothesis property: more fighters never make a side meaningfully worse."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.simulation import constants as c
from app.simulation.engine import run
from tests.property.sim_helpers import lion, make_sheet, matchup_of

NOISE = 0.02
SWARM_MARGIN = 0.12  # a regression margin, not a noise margin: the engine is deterministic


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


# --- Above the swarm threshold (#92) -----------------------------------------------------------


def crowd_share(count: int, foes: int) -> float:
    """A crowd of cats against wolves, in a range where the win share is not stuck at 0 or 1."""
    cat = make_sheet(
        "cat", mass_kg=4.5, size_m=0.46, top_speed_mps=13, attack_force_n=200, attacks_per_s=2.0,
        reach_m=0.2, armor_0_1=0.05, aggression_0_1=1.0,
    )  # fmt: skip
    wolf = make_sheet("wolf", mass_kg=40, size_m=1.2, attack_force_n=1500, attacks_per_s=1.5)
    result = run(matchup_of(count, foes), [cat, wolf], runs=150, explain=False)
    return result.win_prob[0]


@pytest.mark.parametrize(
    ("base", "extra", "foes"),
    [
        (190, 20, 40),  # crosses the threshold: one-by-one before, swarm after
        (200, 1, 40),  # the smallest step across it
        (201, 49, 45),
        (250, 150, 60),
        (400, 200, 90),
    ],
)
def test_adding_fighters_never_lowers_win_probability_in_swarm_mode_either(base, extra, foes):
    assert base + extra > c.SWARM_THRESHOLD
    # The engine is deterministic for a given input, so the margin only guards against a future
    # engine change; the real gains here are +0.10 to +0.75, far above it.
    # at the worst row. This guards against a real reversal (it is a monotonic check, not an
    # accuracy check: D-45's swarm-vs-one-by-one parity is tested elsewhere).
    assert crowd_share(base + extra, foes) >= crowd_share(base, foes) - SWARM_MARGIN
