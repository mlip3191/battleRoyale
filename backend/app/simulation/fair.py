"""Fair-fight search ("a fair fight needs 37 house cats") and next-challenger testing."""

import logging
from dataclasses import dataclass

from app.models.matchup import FighterRequest, Matchup
from app.models.simulation import ChallengerSuggestion, FairFight, SimulationResult
from app.models.stats import StatSheet
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import run
from app.text import counted_name

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FairFightSearch:
    """A FairFight plus how many probes the search used."""

    result: FairFight
    probes: int


# "House cat", 37 -> "house cats"; "African elephant", 2 -> "African elephants". The shared
# helper replaced a local copy that lower-cased every name ("african elephants", "tVs") and had
# weaker plural rules ("bisons", "mans") (#258). Kept under this name for existing callers.
plural = counted_name


def _with_count(matchup: Matchup, side: int, count: int) -> Matchup:
    probe = matchup.model_copy(deep=True)
    probe.fighters[side].count = count
    return probe


def fair_fight_search(
    matchup: Matchup,
    stat_sheets: list[StatSheet],
    result: SimulationResult | None = None,
    reference_sheets: list[StatSheet | None] | None = None,
) -> FairFightSearch:
    """Vary the losing side's count (doubling, then integer binary search) until it is ~50/50.

    Each probe is a 200-run simulation of the varied side's win share; at most 20 probes; counts
    are capped at 10,000. `result` is the main simulation (computed quickly if not given).
    """
    if result is None:
        result = run(
            matchup, stat_sheets, runs=c.FAIR_RUNS, reference_sheets=reference_sheets, explain=False
        )
    if result.outcome in ("draw", "no_contest"):
        why = (
            "Neither side can reach the other, so there is nothing to balance."
            if result.outcome == "no_contest"
            else "The main fight ended in a stalemate, so there is no loser to even things up for."
        )
        return FairFightSearch(
            FairFight(varied_side=0, count=None, win_prob_at_count=None, message=why), 0
        )

    side = 0 if result.win_prob[0] < result.win_prob[1] else 1  # the losing side
    other = 1 - side
    name = stat_sheets[side].display_name
    other_count = matchup.fighters[other].count
    fixed_text = f"{other_count} {counted_name(stat_sheets[other].display_name, other_count)}"
    probes: list[tuple[int, float]] = []

    def probe(count: int) -> float:
        out = run(
            _with_count(matchup, side, count),
            stat_sheets,
            runs=c.FAIR_RUNS,
            reference_sheets=reference_sheets,
            explain=False,
        )
        probes.append((count, out.win_prob[side]))
        return out.win_prob[side]

    def close(p: float) -> bool:
        return abs(p - 0.5) <= c.FAIR_TOLERANCE

    def done(count: int, p: float, rough: bool = False) -> FairFightSearch:
        lead = "A fair fight needs about" if rough else "A fair fight needs"
        message = f"{lead} {count} {counted_name(name, count)} against {fixed_text}."
        return FairFightSearch(
            FairFight(varied_side=side, count=count, win_prob_at_count=p, message=message),
            len(probes),
        )

    def best() -> FairFightSearch:
        count, p = min(probes, key=lambda cp: (abs(cp[1] - 0.5), cp[0]))
        return done(count, p, rough=not close(p))

    lo_edge, hi_edge = 0.5 - c.FAIR_TOLERANCE, 0.5 + c.FAIR_TOLERANCE
    count = matchup.fighters[side].count
    p = probe(count)
    if close(p):
        return done(count, p)

    lo = hi = None
    if p < lo_edge:
        lo = count
        while len(probes) < c.FAIR_MAX_PROBES:
            if count >= c.FAIR_MAX_COUNT:
                most = c.FAIR_MAX_COUNT
                message = f"No fair fight within {most:,} {counted_name(name, most)}."
                return FairFightSearch(
                    FairFight(
                        varied_side=side, count=None, win_prob_at_count=None, message=message
                    ),
                    len(probes),
                )
            count = min(count * 2, c.FAIR_MAX_COUNT)
            p = probe(count)
            if close(p):
                return done(count, p)
            if p > hi_edge:
                hi = count
                break
            lo = count
    else:
        hi = count
        while len(probes) < c.FAIR_MAX_PROBES and count > 1:
            count = max(count // 2, 1)
            p = probe(count)
            if close(p):
                return done(count, p)
            if p < lo_edge:
                lo = count
                break
            hi = count
        if lo is None:
            return best()

    while lo is not None and hi is not None and hi - lo > 1 and len(probes) < c.FAIR_MAX_PROBES:
        mid = (lo + hi) // 2
        p = probe(mid)
        if close(p):
            return done(mid, p)
        if p < 0.5:
            lo = mid
        else:
            hi = mid
    return best()


def fair_fight(
    matchup: Matchup,
    stat_sheets: list[StatSheet],
    result: SimulationResult | None = None,
    reference_sheets: list[StatSheet | None] | None = None,
) -> FairFight:
    """How many of the losing side make the fight about 50/50 (see `fair_fight_search`)."""
    return fair_fight_search(matchup, stat_sheets, result, reference_sheets).result


def _how_even(p: float) -> str:
    gap = abs(p - 0.5)
    if gap <= c.FAIR_TOLERANCE:
        return "a coin flip"
    side = "a slight" if gap <= c.CHALLENGER_SLIGHT_GAP else "a clear"
    return f"{side} {'favorite' if p > 0.5 else 'underdog'}"


def _winner_text(winner_sheet: StatSheet, request: FighterRequest | None, scaled: bool) -> str:
    """How the reason names the winner: "Gray wolf", or "6 gray wolves (horse-sized)"."""
    if request is None:
        return winner_sheet.display_name
    text = winner_sheet.display_name
    if request.count > 1:
        text = f"{request.count:,} {counted_name(winner_sheet.display_name, request.count)}"
    if scaled and request.size_reference:
        text += f" ({request.size_reference}-sized)"
    return text


def test_challengers(
    winner_sheet: StatSheet,
    candidates: list[StatSheet],
    terrain: Terrain,
    winner_request: FighterRequest | None = None,
    winner_reference: StatSheet | None = None,
) -> list[ChallengerSuggestion]:
    """Quick 200-run duels of the winner against each candidate, closest to 50/50 first.

    The language model that proposes candidate names is called elsewhere; this only tests them.
    `tested_win_prob` is the candidate's chance of beating the winner. By default the winner
    duels as one plain fighter; pass the winner's side of the original request (its count and
    size reference) and the size-reference sheet to duel the winner as the user saw it, so
    "6 gray wolves" is tested as six and the reason says so. The candidate is always one fighter.
    """
    suggestions: list[ChallengerSuggestion] = []
    # The winner's side is the same for every candidate, so it is worked out once.
    winner_side = FighterRequest(entity=winner_sheet.fighter_id, raw=winner_sheet.display_name)
    references: list[StatSheet | None] | None = None
    scaled = False
    if winner_request is not None:
        winner_side = winner_request.model_copy(update={"entity": winner_sheet.fighter_id})
        if winner_request.size_reference and winner_reference is not None:
            references = [winner_reference, None]
            scaled = True
        elif winner_request.size_reference:
            logger.warning(
                "test_challengers: size_reference without a reference sheet; testing unscaled"
            )
            winner_side.size_reference = None  # no sheet to scale from: leave it unscaled
    # The reason says "X-sized" only when the winner is really scaled.
    winner_text = _winner_text(winner_sheet, winner_request, scaled)
    for candidate in candidates:
        duel = Matchup(
            fighters=[
                winner_side,
                FighterRequest(entity=candidate.fighter_id, raw=candidate.display_name),
            ],
            terrain=terrain,
            raw_text=f"{winner_sheet.display_name} vs {candidate.display_name}",
        )
        result = run(
            duel,
            [winner_sheet, candidate],
            runs=c.FAIR_RUNS,
            reference_sheets=references,
            explain=False,
        )
        if result.outcome == "no_contest":
            continue  # cannot even meet: not a useful next fight
        p = result.win_prob[1]
        reason = f"{candidate.display_name} would be {_how_even(p)} against {winner_text}."
        suggestions.append(
            ChallengerSuggestion(entity=candidate.display_name, tested_win_prob=p, reason=reason)
        )
    return sorted(suggestions, key=lambda s: (abs(s.tested_win_prob - 0.5), s.entity))


# The function is named in the task and is not a pytest test.
test_challengers.__test__ = False  # type: ignore[attr-defined]
