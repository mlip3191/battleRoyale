"""#113: an 8-fighter single-elimination bracket built from ordinary, seeded 1 v 1 fights."""

import pytest

from app.models.matchup import FighterRequest, Matchup
from app.models.terrain import Terrain
from app.simulation.engine import run
from app.simulation.tournament import ROUND_ONE_PAIRS, run_tournament
from tests.property.sim_helpers import make_sheet

RUNS = 40


def field():
    """Eight distinct fighters, strongest first, so the top seeds should do well."""
    return [
        make_sheet(
            f"fighter{n}",
            mass_kg=80 - n * 8,
            attack_force_n=900 - n * 90,
            attacks_per_s=2.0,
        )  # fmt: skip
        for n in range(8)
    ]


def tournament(sheets=None, **kwargs):
    return run_tournament(sheets or field(), runs=RUNS, explain=False, **kwargs)


def test_eight_fighters_make_three_rounds_of_4_2_1_matches_and_one_champion():
    t = tournament()
    assert [len(r) for r in t.rounds] == [4, 2, 1]
    assert [m.round for r in t.rounds for m in r] == [1] * 4 + [2] * 2 + [3]
    assert t.champion == t.rounds[-1][0].winner


def test_every_winner_is_one_of_its_two_fighters_and_advances_to_the_next_round():
    t = tournament()
    for matches in t.rounds:
        for m in matches:
            assert m.winner in m.fighters
    for earlier, later in zip(t.rounds, t.rounds[1:], strict=False):
        advancing = [m.winner for m in earlier]
        entrants = [f for m in later for f in m.fighters]
        assert sorted(f.sheet_hash for f in advancing) == sorted(f.sheet_hash for f in entrants)
        # winners of matches 1+2 meet, and 3+4 meet
        for pair, match in enumerate(later):
            expected = {
                earlier[2 * pair].winner.sheet_hash,
                earlier[2 * pair + 1].winner.sheet_hash,
            }
            assert {f.sheet_hash for f in match.fighters} == expected


def test_round_one_is_seeded_1v8_4v5_2v7_3v6_by_the_callers_order():
    sheets = field()
    t = tournament(sheets)
    assert ROUND_ONE_PAIRS == ((0, 7), (3, 4), (1, 6), (2, 5))
    assert [m.seeds for m in t.rounds[0]] == [(1, 8), (4, 5), (2, 7), (3, 6)]
    expected = [(0, 7), (3, 4), (1, 6), (2, 5)]
    assert [m.fighters for m in t.rounds[0]] == [(sheets[i], sheets[j]) for i, j in expected]


def test_the_same_fighters_give_the_identical_bracket_and_champion():
    first, second = tournament(), tournament()
    assert first == second
    assert first.seed == second.seed


def test_the_tournament_seed_changes_with_the_terrain_and_the_fighters():
    base = tournament()
    assert tournament(terrain=Terrain.OPEN_FIELD).seed != base.seed
    other = field()
    other[7] = make_sheet("outsider", mass_kg=10)
    assert tournament(other).seed != base.seed


def test_each_match_is_the_ordinary_one_v_one_simulation():
    sheets = field()
    t = tournament(sheets)
    m = t.rounds[0][0]
    matchup = Matchup(
        fighters=[
            FighterRequest(entity=s.fighter_id, count=1, raw=s.display_name) for s in m.fighters
        ],
        terrain=t.terrain,
        raw_text=f"{m.fighters[0].display_name} vs {m.fighters[1].display_name}",
    )
    assert run(matchup, list(m.fighters), runs=RUNS, explain=False) == m.result


def test_a_clear_favorite_is_decided_by_the_simulation():
    t = tournament()
    top_seed_match = t.rounds[0][0]
    assert top_seed_match.winner == top_seed_match.fighters[0]
    assert top_seed_match.decided_by == "simulation"


def test_a_stalemate_still_sends_someone_through_and_says_how():
    # Nobody here can hurt anybody, so every match is a no contest: the higher seed goes through.
    harmless = [
        make_sheet(f"soft{n}", mass_kg=50, attack_force_n=0, attacks_per_s=0) for n in range(8)
    ]
    t = tournament(harmless)
    assert all(m.decided_by == "seed" for r in t.rounds for m in r)
    assert t.champion == harmless[0]


@pytest.mark.parametrize("count", [0, 1, 7, 9, 16])
def test_other_than_eight_fighters_is_rejected_with_a_clear_error(count):
    sheets = [make_sheet(f"extra{n}") for n in range(count)]
    with pytest.raises(ValueError, match="exactly 8 fighters"):
        run_tournament(sheets, runs=RUNS, explain=False)


def test_the_same_fighter_twice_is_rejected():
    sheets = field()
    sheets[5] = sheets[2]
    with pytest.raises(ValueError, match="only once"):
        run_tournament(sheets, runs=RUNS, explain=False)
