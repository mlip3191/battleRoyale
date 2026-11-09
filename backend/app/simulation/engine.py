"""The time-stepped combat loop: one fight, and many fights summarized."""

import heapq
import math
import random
from dataclasses import dataclass

from app.config import get_settings
from app.models.matchup import Matchup
from app.models.simulation import EventType, FightEvent, SimulationResult
from app.models.stats import StatSheet
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.fighters import Template, damage_per_hit, hit_chance, sample_template
from app.simulation.rng import make_seed, run_rng

DRAW = 2


@dataclass
class RunOutcome:
    """What happened in one fight."""

    winner: int  # 0, 1, or DRAW
    survivors: tuple[int, int]
    duration_s: float
    events: list[FightEvent]


def _tick_up(t: float) -> float:
    """Round a time up to the next tick boundary."""
    return round(math.ceil(t / c.TICK_S - 1e-9) * c.TICK_S, 6)


def run_once(
    sides: list[Template], terrain: Terrain, rng: random.Random, record_events: bool = False
) -> RunOutcome:
    """Simulate one fight to the end (a side wiped out, or 600 s).

    Time moves in 0.1 s ticks; the loop jumps straight to the next tick where someone acts.
    `terrain` is accepted now and used from F04 on.
    """
    events: list[FightEvent] = []
    # Leave room for the closing events so the log never passes the cap.
    room = c.MAX_LOG_EVENTS - 2

    def log(event: FightEvent) -> None:
        if record_events and len(events) < room:
            events.append(event)

    alive = [list(range(sides[0].count)), list(range(sides[1].count))]
    hp = [[sides[s].max_hp] * sides[s].count for s in (0, 1)]

    closing = sides[0].speed_mps + sides[1].speed_mps
    if not (sides[0].can_attack or sides[1].can_attack) or closing <= 0:
        return _finish(alive, c.MAX_FIGHT_S, events, record_events)

    reach = max(sides[0].reach_m, sides[1].reach_m)
    approach_s = max(0.0, c.START_DISTANCE_M - reach) / closing
    for s in (0, 1):
        log(
            FightEvent(
                t=0.0,
                type=EventType.APPROACH,
                side=s,
                group_size=sides[s].count,
                text_hint="closes in",
            )
        )

    # Queue of (time, random tiebreak, side, fighter). Each fighter gets a random first strike.
    queue: list[tuple[float, float, int, int]] = []
    for s in (0, 1):
        if not sides[s].can_attack:
            continue
        interval = 1.0 / sides[s].attacks_per_s
        for i in alive[s]:
            first = _tick_up(approach_s + rng.uniform(0.0, interval))
            heapq.heappush(queue, (first, rng.random(), s, i))

    while queue:
        t, _, s, i = heapq.heappop(queue)
        if t > c.MAX_FIGHT_S:
            break
        if i not in alive[s]:
            continue
        me, foe_side = sides[s], 1 - s
        foe = sides[foe_side]
        target = rng.choice(alive[foe_side])
        if rng.random() < hit_chance(me, foe):
            dmg = damage_per_hit(me, foe)
            hp[foe_side][target] -= dmg
            log(
                FightEvent(
                    t=t,
                    type=EventType.HIT,
                    side=s,
                    actor=i,
                    target=target,
                    damage=round(dmg, 1),
                    text_hint=f"{me.weapon_word} lands",
                )
            )
            if hp[foe_side][target] <= 0:
                alive[foe_side].remove(target)
                log(
                    FightEvent(
                        t=t, type=EventType.KO, side=foe_side, actor=target, text_hint="goes down"
                    )
                )
                if not alive[foe_side]:
                    return _finish(alive, t, events, record_events)
        else:
            log(
                FightEvent(
                    t=t,
                    type=EventType.MISS,
                    side=s,
                    actor=i,
                    target=target,
                    text_hint=f"{me.weapon_word} misses",
                )
            )
        heapq.heappush(queue, (_tick_up(t + 1.0 / me.attacks_per_s), rng.random(), s, i))

    # Clock ran out, or nobody can finish the other: a draw at the time limit.
    return _finish(alive, c.MAX_FIGHT_S, events, record_events)


def _finish(
    alive: list[list[int]], t: float, events: list[FightEvent], record_events: bool
) -> RunOutcome:
    survivors = (len(alive[0]), len(alive[1]))
    if survivors[0] and survivors[1]:
        winner = DRAW
    else:
        winner = 0 if survivors[0] else 1
    if record_events:
        if winner == DRAW:
            events.append(
                FightEvent(t=t, type=EventType.STALEMATE, side=0, text_hint="neither side can win")
            )
            hint = "fight ends in a draw"
        else:
            hint = f"side {winner} wins"
        end_side = 0 if winner == DRAW else winner
        events.append(FightEvent(t=t, type=EventType.END, side=end_side, text_hint=hint))
    return RunOutcome(winner, survivors, t, events)


def wilson(successes: int, n: int, z: float = c.WILSON_Z) -> tuple[float, float]:
    """95% Wilson score interval for a share."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _templates(matchup: Matchup, sheets: list[StatSheet], rng: random.Random) -> list[Template]:
    return [sample_template(sheets[s], matchup.fighters[s].count, rng) for s in (0, 1)]


def run(
    matchup: Matchup, stat_sheets: list[StatSheet], runs: int | None = None
) -> SimulationResult:
    """Run the fight many times and summarize it."""
    runs = get_settings().sim_runs if runs is None else runs
    seed = make_seed(matchup, stat_sheets[0].sheet_hash, stat_sheets[1].sheet_hash)

    outcomes: list[RunOutcome] = []
    for k in range(runs):
        rng = run_rng(seed, k)
        outcomes.append(run_once(_templates(matchup, stat_sheets, rng), matchup.terrain, rng))

    wins = [sum(o.winner == s for o in outcomes) for s in (0, 1)]
    draws = runs - wins[0] - wins[1]
    counts = {"win_0": wins[0], "win_1": wins[1], "draw": draws}
    outcome_name = max(counts, key=lambda k: counts[k])
    code = {"win_0": 0, "win_1": 1, "draw": DRAW}[outcome_name]

    # Representative fight: closest to the median duration among runs with the top outcome.
    same = sorted(
        (k for k, o in enumerate(outcomes) if o.winner == code),
        key=lambda k: outcomes[k].duration_s,
    )
    pick = same[len(same) // 2]
    rng = run_rng(seed, pick)
    replay = run_once(
        _templates(matchup, stat_sheets, rng), matchup.terrain, rng, record_events=True
    )

    return SimulationResult(
        seed=seed,
        runs=runs,
        win_prob=(wins[0] / runs, wins[1] / runs),
        draw_prob=draws / runs,
        win_prob_ci95=(wilson(wins[0], runs), wilson(wins[1], runs)),
        mean_survivors=(
            sum(o.survivors[0] for o in outcomes) / runs,
            sum(o.survivors[1] for o in outcomes) / runs,
        ),
        mean_duration_s=sum(o.duration_s for o in outcomes) / runs,
        outcome=outcome_name,
        deciding_factor="mass_kg",
        deciding_factor_explainer="Placeholder until the deciding-factor analysis (F05) is built.",
        representative_log=replay.events,
    )
