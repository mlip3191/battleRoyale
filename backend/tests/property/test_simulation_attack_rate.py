"""#84: a fighter's long-run attack rate matches its sheet rate (the tick no longer slows it)."""

import pytest

from app.models.terrain import Terrain
from app.simulation.engine import _templates, run_once
from app.simulation.rng import run_rng
from tests.property.sim_helpers import make_sheet, matchup_of


@pytest.mark.parametrize("rate", [1, 3, 7, 9])
def test_attacks_over_a_long_fight_match_the_sheet_rate(rate):
    """One attacker against a target that cannot be hurt, for the whole 600 s."""
    attacker = make_sheet("attacker", attack_force_n=50, attacks_per_s=rate, spread=0.0, mass_kg=10)
    wall = make_sheet("wall", mass_kg=5e9, size_m=50, attack_force_n=0, attacks_per_s=0,
                      top_speed_mps=0, spread=0.0)  # fmt: skip
    matchup = matchup_of(1, 1, terrain=Terrain.ARENA)
    for k in range(5):
        stream = run_rng(3, k)
        sides = _templates(matchup, [attacker, wall], stream, (1.0, 1.0))
        outcome = run_once(sides, matchup.terrain, stream, record_events=True)  # full simulation
        seconds = 600 - 0.5  # the fight starts within the first half second
        assert abs(outcome.attacks - rate * seconds) <= rate * 0.5 + 2, (rate, outcome.attacks)
