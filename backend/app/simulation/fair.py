"""Fair-fight search ("a fair fight needs 37 house cats") and next-challenger testing."""

from dataclasses import dataclass

from app.models.matchup import FighterRequest, Matchup
from app.models.simulation import ChallengerSuggestion, FairFight, SimulationResult
from app.models.stats import StatSheet
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import run


@dataclass(frozen=True)
class FairFightSearch:
    """A FairFight plus how many probes the search used."""

    result: FairFight
    probes: int


_IRREGULAR_PLURALS = {
    "mouse": "mice", "goose": "geese", "ox": "oxen", "sheep": "sheep", "deer": "deer",
    "fish": "fish", "moose": "moose",
}  # fmt: skip


def plural(name: str, count: int) -> str:
    """ "House cat" -> "house cats" (simple English rules; only the first letter is lower-cased)."""
    name = name[:1].lower() + name[1:]
    if count == 1:
        return name
    head, _, last = name.rpartition(" ")
    if last in _IRREGULAR_PLURALS:
        return (head + " " if head else "") + _IRREGULAR_PLURALS[last]
    if name.endswith(("s", "x", "sh", "ch")):
        return name + "es"
    if name.endswith("y") and name[-2:-1] not in "aeiou":
        return name[:-1] + "ies"
    if name.endswith("f"):
        return name[:-1] + "ves"
    return name + "s"


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
    fixed_text = f"{other_count} {plural(stat_sheets[other].display_name, other_count)}"
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
        message = f"{lead} {count} {plural(name, count)} against {fixed_text}."
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
                message = (
                    f"No fair fight within {c.FAIR_MAX_COUNT:,} {plural(name, c.FAIR_MAX_COUNT)}."
                )
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


def test_challengers(
    winner_sheet: StatSheet,
    candidates: list[StatSheet],
    terrain: Terrain,
) -> list[ChallengerSuggestion]:
    """Quick 200-run duels of the winner against each candidate, closest to 50/50 first.

    The language model that proposes candidate names is called elsewhere; this only tests them.
    `tested_win_prob` is the candidate's chance of beating the winner.
    """
    suggestions: list[ChallengerSuggestion] = []
    for candidate in candidates:
        duel = Matchup(
            fighters=[
                FighterRequest(entity=winner_sheet.fighter_id, raw=winner_sheet.display_name),
                FighterRequest(entity=candidate.fighter_id, raw=candidate.display_name),
            ],
            terrain=terrain,
            raw_text=f"{winner_sheet.display_name} vs {candidate.display_name}",
        )
        result = run(duel, [winner_sheet, candidate], runs=c.FAIR_RUNS, explain=False)
        if result.outcome == "no_contest":
            continue  # cannot even meet: not a useful next fight
        p = result.win_prob[1]
        reason = (
            f"{candidate.display_name} would be {_how_even(p)} against {winner_sheet.display_name}."
        )
        suggestions.append(
            ChallengerSuggestion(entity=candidate.display_name, tested_win_prob=p, reason=reason)
        )
    return sorted(suggestions, key=lambda s: (abs(s.tested_win_prob - 0.5), s.entity))


# The function is named in the task and is not a pytest test.
test_challengers.__test__ = False  # type: ignore[attr-defined]
