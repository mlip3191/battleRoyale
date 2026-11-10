"""Tournament bracket engine: 8 fighters, single elimination, 3 rounds (4, 2 and 1 matches).

Every match is an ordinary 1 v 1 `run(...)` with its own seed from `make_seed`, so the bracket adds
no randomness of its own: the same eight sheets, terrain and number of runs always give the same
bracket and champion.
"""

import hashlib
from dataclasses import dataclass
from typing import Literal

from app.models.matchup import FighterRequest, Matchup
from app.models.simulation import SimulationResult
from app.models.stats import StatSheet
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import run

BRACKET_SIZE = 8

# Seeding: the caller's order is the seeding (first = top seed). Round 1 pairs 1v8, 4v5, 2v7, 3v6,
# so the top seeds can only meet late and the winners of matches 1+2 and 3+4 meet in the semis.
ROUND_ONE_PAIRS = ((0, 7), (3, 4), (1, 6), (2, 5))

DecidedBy = Literal["simulation", "better_odds", "seed"]


@dataclass(frozen=True)
class Match:
    """One match: who met, the 1 v 1 verdict, and who goes through."""

    round: int  # 1 = quarterfinals, 2 = semifinals, 3 = final
    number: int  # 1-based position within the round
    fighters: tuple[StatSheet, StatSheet]  # (higher seed, lower seed) of the two entrants
    seeds: tuple[int, int]  # 1-based tournament seeds of those two
    result: SimulationResult
    winner: StatSheet
    decided_by: DecidedBy
    """"simulation" = the verdict named a winner; "better_odds" = a draw or no contest, so the
    higher win share goes through; "seed" = still level, so the higher seed goes through."""


@dataclass(frozen=True)
class Tournament:
    """The whole bracket: rounds of matches in order, and the champion."""

    seed: int  # fingerprint of the entrants, terrain and engine version; same inputs, same seed
    terrain: Terrain
    rounds: tuple[tuple[Match, ...], ...]  # (4 matches, 2 matches, 1 match)
    champion: StatSheet


def run_tournament(
    stat_sheets: list[StatSheet],
    terrain: Terrain = Terrain.ARENA,
    runs: int | None = None,
    explain: bool = True,
) -> Tournament:
    """Run an 8-fighter single-elimination bracket; `stat_sheets` are in seed order.

    `explain=False` skips the deciding-factor analysis in every match (faster; the results then
    carry a placeholder factor that must not be shown).
    """
    if len(stat_sheets) != BRACKET_SIZE:
        raise ValueError(
            f"A tournament needs exactly {BRACKET_SIZE} fighters, but got {len(stat_sheets)}."
        )
    hashes = [sheet.sheet_hash for sheet in stat_sheets]
    if len(set(hashes)) != len(hashes):
        raise ValueError("Each fighter can enter the tournament only once.")

    entrants = [(index + 1, sheet) for index, sheet in enumerate(stat_sheets)]
    rounds: list[tuple[Match, ...]] = []
    pairs = [(entrants[a], entrants[b]) for a, b in ROUND_ONE_PAIRS]
    round_number = 1
    while True:
        matches = tuple(
            _play(round_number, number, first, second, terrain, runs, explain)
            for number, (first, second) in enumerate(pairs, start=1)
        )
        rounds.append(matches)
        survivors = [(m.seeds[m.fighters.index(m.winner)], m.winner) for m in matches]
        if len(survivors) == 1:
            break
        pairs = [(survivors[i], survivors[i + 1]) for i in range(0, len(survivors), 2)]
        round_number += 1
    return Tournament(
        seed=_tournament_seed(hashes, terrain),
        terrain=terrain,
        rounds=tuple(rounds),
        champion=survivors[0][1],
    )


def _play(
    round_number: int,
    number: int,
    first: tuple[int, StatSheet],
    second: tuple[int, StatSheet],
    terrain: Terrain,
    runs: int | None,
    explain: bool,
) -> Match:
    (seed_a, sheet_a), (seed_b, sheet_b) = sorted((first, second), key=lambda entrant: entrant[0])
    matchup = Matchup(
        fighters=[
            FighterRequest(entity=sheet.fighter_id, count=1, raw=sheet.display_name)
            for sheet in (sheet_a, sheet_b)
        ],
        terrain=terrain,
        raw_text=f"{sheet_a.display_name} vs {sheet_b.display_name}",
    )
    result = run(matchup, [sheet_a, sheet_b], runs=runs, explain=explain)
    side, decided_by = _winning_side(result)
    return Match(
        round=round_number,
        number=number,
        fighters=(sheet_a, sheet_b),
        seeds=(seed_a, seed_b),
        result=result,
        winner=(sheet_a, sheet_b)[side],
        decided_by=decided_by,
    )


def _winning_side(result: SimulationResult) -> tuple[int, DecidedBy]:
    """Side 0 is the higher seed. A draw or no contest still has to send one fighter through."""
    if result.outcome == "win_0":
        return 0, "simulation"
    if result.outcome == "win_1":
        return 1, "simulation"
    if result.win_prob[0] != result.win_prob[1]:
        return (0 if result.win_prob[0] > result.win_prob[1] else 1), "better_odds"
    return 0, "seed"


def _tournament_seed(sheet_hashes: list[str], terrain: Terrain) -> int:
    parts = [f"engine={c.ENGINE_VERSION}", f"terrain={terrain.value}", *sheet_hashes]
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") >> 1
