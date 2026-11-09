"""The time-stepped combat loop: one fight, and many fights summarized."""

import heapq
import math
import random
from collections.abc import Callable
from dataclasses import dataclass

from app.config import get_settings
from app.models.matchup import Matchup
from app.models.simulation import EventType, FightEvent, SimulationResult
from app.models.stats import Body, StatName, StatSheet
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.decide import decide
from app.simulation.fighters import (
    Template,
    apply_terrain,
    can_hurt,
    damage_per_hit,
    effective_habitat,
    group_bonus,
    hit_chance,
    max_engagers,
    sample_template,
    scale_factor,
)
from app.simulation.rng import make_seed, run_rng
from app.simulation.terrain import can_engage

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


class _Pool:
    """Lanchester linear law for one attacking side: each target takes only so many attackers.

    Attackers that find every target full wait in a queue until a slot opens.
    """

    def __init__(self, n_targets: int, cap: int) -> None:
        self.cap = cap
        self.engaged: dict[int, set[int]] = {}
        self.open = list(range(n_targets))  # targets with a free slot
        self.pos = {t: k for k, t in enumerate(self.open)}
        self.assign: dict[int, int] = {}
        self.gone: set[int] = set()
        self.waiting: list[int] = []

    def _open_add(self, t: int) -> None:
        if t not in self.pos:
            self.pos[t] = len(self.open)
            self.open.append(t)

    def _open_remove(self, t: int) -> None:
        k = self.pos.pop(t, None)
        if k is None:
            return
        last = self.open.pop()
        if k < len(self.open):
            self.open[k] = last
            self.pos[last] = k

    def acquire(self, i: int, rng: random.Random) -> int | None:
        """The target attacker `i` fights now, or None if every target is full."""
        t = self.assign.get(i)
        if t is not None:
            if t not in self.gone:
                return t
            del self.assign[i]
        if not self.open:
            return None
        t = self.open[rng.randrange(len(self.open))]
        group = self.engaged.setdefault(t, set())
        group.add(i)
        self.assign[i] = t
        if len(group) >= self.cap:
            self._open_remove(t)
        return t

    def attacker_died(self, i: int) -> bool:
        """Free the dead attacker's slot. True if a waiting attacker can now take it."""
        t = self.assign.pop(i, None)
        if t is None or t in self.gone:
            return False
        self.engaged[t].discard(i)
        self._open_add(t)
        return True

    def target_died(self, t: int) -> None:
        self.gone.add(t)
        self._open_remove(t)
        self.engaged.pop(t, None)


def _starts(sides: list[Template]) -> list[float]:
    """When each side can first attack: the gap closes, minus that side's own reach.

    A side that cannot close the gap and cannot reach across it (inf) never attacks.
    """
    closing = sides[0].speed_mps + sides[1].speed_mps
    out = []
    for s in (0, 1):
        gap = max(0.0, c.START_DISTANCE_M - sides[s].reach_m)
        out.append(0.0 if gap == 0 else (gap / closing if closing > 0 else math.inf))
    return out


def run_once(
    sides: list[Template],
    terrain: Terrain,
    rng: random.Random,
    record_events: bool = False,
    notes: tuple[str, str] = ("", ""),
) -> RunOutcome:
    """Simulate one fight to the end (a side wiped out, or 600 s).

    Time moves in 0.1 s ticks; the loop jumps straight to the next tick where someone acts.
    Sides with more than 200 individuals run in groups (swarm mode). `notes` are short
    neutral phrases added to the opening events (e.g. "scaled to horse size").
    Terrain modifiers are already applied to `sides` (see `_templates`). A side that loses too
    much of its hit points retreats; if it is faster than its pursuers it escapes. Machines
    never retreat and stop when their operating time runs out; inert fighters never approach.
    """
    events: list[FightEvent] = []
    # Leave room for the closing events so the log never passes the cap.
    room = c.MAX_LOG_EVENTS - c.CLOSING_EVENTS

    def log(event: FightEvent) -> None:
        if record_events and len(events) < room:
            events.append(event)

    starts = _starts(sides)
    if not any(sides[s].can_attack and starts[s] != math.inf for s in (0, 1)):
        alive = [sides[0].count, sides[1].count]
        return _outcome(alive, c.MAX_FIGHT_S, events, record_events)

    for s in (0, 1):
        hint = "closes in" + (f", {notes[s]}" if notes[s] else "")
        log(
            FightEvent(
                t=0.0, type=EventType.APPROACH, side=s, group_size=sides[s].count, text_hint=hint
            )
        )

    if max(sides[0].count, sides[1].count) > c.SWARM_THRESHOLD:
        return _run_swarm(sides, rng, starts, log, events, record_events)
    return _run_individuals(sides, rng, starts, log, events, record_events)


OUT_OF_ACTION = "out of action: its operating time ran out"


def _run_individuals(
    sides: list[Template],
    rng: random.Random,
    starts: list[float],
    log: Callable[[FightEvent], None],
    events: list[FightEvent],
    record_events: bool,
) -> RunOutcome:
    alive_list = [list(range(sides[0].count)), list(range(sides[1].count))]
    alive_set = [set(a) for a in alive_list]
    hp = [[sides[s].max_hp] * sides[s].count for s in (0, 1)]
    start_hp = [sides[s].max_hp * sides[s].count for s in (0, 1)]
    total_hp = list(start_hp)
    retreating: int | None = None
    bonus = [group_bonus(sides[0]), group_bonus(sides[1])]
    hit_p = [hit_chance(sides[0], sides[1]), hit_chance(sides[1], sides[0])]
    dmg = [damage_per_hit(sides[0], sides[1]), damage_per_hit(sides[1], sides[0])]
    # Damage a side's spines deal to whoever hits it (inert fighters with spines only).
    spike = [damage_per_hit(sides[s], sides[1 - s]) if sides[s].spiky else 0.0 for s in (0, 1)]
    # Regeneration heals lazily: a fighter catches up on healing whenever it is next touched.
    regen = [sides[s].regen_per_s * sides[s].max_hp for s in (0, 1)]
    last_t = [[0.0] * sides[s].count for s in (0, 1)]
    # Pools only matter for melee; ranged sides use the square law (everyone engages).
    pools = [
        None
        if sides[s].ranged or not sides[s].can_attack
        else _Pool(sides[1 - s].count, max_engagers(sides[s], sides[1 - s]))
        for s in (0, 1)
    ]

    # Queue of (time, random tiebreak, side, fighter). Each fighter gets a random first strike.
    # A negative fighter number -1 - i means "machine i runs out of operating time now".
    queue: list[tuple[float, float, int, int]] = []
    for s in (0, 1):
        if sides[s].can_attack and starts[s] != math.inf:
            interval = 1.0 / sides[s].attacks_per_s
            for i in alive_list[s]:
                first = _tick_up(starts[s] + rng.uniform(0.0, interval))
                heapq.heappush(queue, (first, rng.random(), s, i))
        if sides[s].body == Body.MACHINE and sides[s].endurance_s <= c.MAX_FIGHT_S:
            for i in alive_list[s]:
                heapq.heappush(queue, (sides[s].endurance_s, rng.random(), s, -1 - i))

    def heal(side: int, idx: int, t: float) -> None:
        if regen[side] > 0:
            gain = regen[side] * (t - last_t[side][idx])
            last_t[side][idx] = t
            before = hp[side][idx]
            after = min(sides[side].max_hp, before + gain)
            total_hp[side] += after - before
            hp[side][idx] = after

    def remove(side: int, idx: int, t: float, hint: str) -> bool:
        """Take a fighter out of the fight. True if that empties its side."""
        alive_list[side].remove(idx)
        alive_set[side].discard(idx)
        log(FightEvent(t=t, type=EventType.KO, side=side, actor=idx, text_hint=hint))
        if not alive_list[side]:
            return True
        attackers = pools[1 - side]
        if attackers is not None:
            attackers.target_died(idx)
        own = pools[side]
        if own is not None and own.attacker_died(idx):
            # A slot opened for the dead fighter's side: wake one waiting attacker.
            while own.waiting:
                j = own.waiting.pop()
                if j in alive_set[side]:
                    heapq.heappush(queue, (_tick_up(t + c.TICK_S), rng.random(), side, j))
                    break
        return False

    def finish(t: float) -> RunOutcome:
        alive = [len(alive_list[0]), len(alive_list[1])]
        return _outcome(alive, t, events, record_events)

    while queue:
        t, _, s, i = heapq.heappop(queue)
        if t > c.MAX_FIGHT_S:
            break
        if i < 0:  # a machine ran out of operating time
            j = -1 - i
            if j in alive_set[s]:
                total_hp[s] -= max(hp[s][j], 0.0)
                if remove(s, j, t, OUT_OF_ACTION):
                    return finish(t)
            continue
        if i not in alive_set[s] or s == retreating:
            continue  # dead fighters and a side that is running away do not attack
        me, foe_side = sides[s], 1 - s
        pool = pools[s]
        if pool is None:
            target = rng.choice(alive_list[foe_side])
        else:
            target = pool.acquire(i, rng)
            if target is None:
                pool.waiting.append(i)  # every target is full: wait for a free slot
                continue
        chance = hit_p[s]
        if sides[s].group_tactics > 0 and (
            len(pool.engaged.get(target, ())) >= 2 if pool is not None else len(alive_list[s]) >= 2
        ):
            chance = min(c.HIT_MAX, chance * bonus[s])  # coordinated attack
        if rng.random() < chance:
            heal(foe_side, target, t)
            total_hp[foe_side] -= min(dmg[s], max(hp[foe_side][target], 0.0))
            hp[foe_side][target] -= dmg[s]
            log(
                FightEvent(
                    t=t,
                    type=EventType.HIT,
                    side=s,
                    actor=i,
                    target=target,
                    damage=round(dmg[s], 1),
                    text_hint=f"{me.weapon_word} lands",
                )
            )
            if hp[foe_side][target] <= 0 and remove(foe_side, target, t, "goes down"):
                return finish(t)
            if retreating is None and 1 - total_hp[foe_side] / start_hp[foe_side] >= (
                sides[foe_side].morale
            ):
                retreating = foe_side
                log(
                    FightEvent(
                        t=t,
                        type=EventType.RETREAT,
                        side=foe_side,
                        group_size=len(alive_list[foe_side]),
                        text_hint="breaks and runs",
                    )
                )
                if sides[foe_side].speed_mps > sides[s].speed_mps:
                    log(
                        FightEvent(
                            t=t,
                            type=EventType.FLEE,
                            side=foe_side,
                            group_size=len(alive_list[foe_side]),
                            text_hint="escapes",
                        )
                    )
                    alive = [len(alive_list[0]), len(alive_list[1])]
                    return _outcome(alive, t, events, record_events, winner=s)
            if spike[foe_side] > 0 and target in alive_set[foe_side]:
                # Spines: the target hurts whoever hit it.
                heal(s, i, t)
                taken = spike[foe_side]
                total_hp[s] -= min(taken, max(hp[s][i], 0.0))
                hp[s][i] -= taken
                log(
                    FightEvent(
                        t=t,
                        type=EventType.HIT,
                        side=foe_side,
                        actor=target,
                        target=i,
                        damage=round(taken, 1),
                        text_hint="spines jab back",
                    )
                )
                if hp[s][i] <= 0:
                    if remove(s, i, t, "goes down"):
                        return finish(t)
                    continue  # the attacker is dead: no next attack
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
    return finish(c.MAX_FIGHT_S)


def _apply_hits(
    hits: int, dmg: float, n: int, front_hp: float, full_hp: float
) -> tuple[int, int, float]:
    """Focus-fire `hits` on a bin of `n` identical fighters. Returns (kills, n_left, front_hp).

    Hits land on one fighter at a time; damage beyond a kill is wasted, as in the 1-by-1 engine.
    """
    first = max(1, math.ceil(front_hp / dmg - 1e-9))
    if hits < first:
        return 0, n, front_hp - hits * dmg
    full = max(1, math.ceil(full_hp / dmg - 1e-9))
    kills = min(n, 1 + (hits - first) // full)
    left = n - kills
    rest = (hits - first) % full
    return kills, left, full_hp - rest * dmg


def _run_swarm(
    sides: list[Template],
    rng: random.Random,
    starts: list[float],
    log: Callable[[FightEvent], None],
    events: list[FightEvent],
    record_events: bool,
) -> RunOutcome:
    """Aggregated fight for big groups: each side is one bin of identical fighters."""
    n = [sides[0].count, sides[1].count]
    front = [sides[0].max_hp, sides[1].max_hp]
    hit_p = [hit_chance(sides[0], sides[1]), hit_chance(sides[1], sides[0])]
    dmg = [damage_per_hit(sides[0], sides[1]), damage_per_hit(sides[1], sides[0])]
    spike = [damage_per_hit(sides[s], sides[1 - s]) if sides[s].spiky else 0.0 for s in (0, 1)]
    cap = [max_engagers(sides[0], sides[1]), max_engagers(sides[1], sides[0])]
    bonus = [group_bonus(sides[0]), group_bonus(sides[1])]
    start_hp = [sides[s].max_hp * sides[s].count for s in (0, 1)]
    retreating: int | None = None
    t = _tick_up(min(starts))

    while t <= c.MAX_FIGHT_S:
        dt = max(c.SWARM_STEP_S, t * c.SWARM_STEP_GROWTH)
        for s in (0, 1):
            if sides[s].regen_per_s > 0 and n[s] > 0:
                heal_hp = sides[s].regen_per_s * sides[s].max_hp * dt
                front[s] = min(sides[s].max_hp, front[s] + heal_hp)
            if sides[s].body == Body.MACHINE and n[s] > 0 and t >= sides[s].endurance_s:
                log(
                    FightEvent(
                        t=t, type=EventType.KO, side=s, group_size=n[s], text_hint=OUT_OF_ACTION
                    )
                )
                n[s] = 0
        if n[0] == 0 or n[1] == 0:
            return _outcome(n, t, events, record_events)
        # The sides act in random order each step, so equal swarms do not always wipe each
        # other out at the same instant (and neither side gets a built-in first strike).
        order = (0, 1) if rng.random() < 0.5 else (1, 0)
        for s in order:
            me, foe = sides[s], 1 - s
            if n[s] == 0 or not me.can_attack or n[foe] == 0 or s == retreating or t < starts[s]:
                continue
            engaged = n[s] if me.ranged else min(n[s], n[foe] * cap[s])
            crowding = n[s] >= 2 if me.ranged else engaged > n[foe]
            rate = me.attacks_per_s * dt
            whole = int(rate)
            attempts = engaged * whole
            if rate > whole:
                attempts += rng.binomialvariate(engaged, rate - whole)
            chance = min(c.HIT_MAX, hit_p[s] * bonus[s]) if crowding else hit_p[s]
            hits = rng.binomialvariate(attempts, chance) if attempts else 0
            if not hits or dmg[s] <= 0:
                continue
            log(
                FightEvent(
                    t=t,
                    type=EventType.HIT,
                    side=s,
                    group_size=hits,
                    damage=round(hits * dmg[s], 1),
                    text_hint=f"{me.weapon_word}s land",
                )
            )
            kills, n[foe], front[foe] = _apply_hits(
                hits, dmg[s], n[foe], front[foe], sides[foe].max_hp
            )
            if kills:
                log(
                    FightEvent(
                        t=t,
                        type=EventType.KO,
                        side=foe,
                        group_size=kills,
                        text_hint="go down" if kills > 1 else "goes down",
                    )
                )
            remaining = (n[foe] - 1) * sides[foe].max_hp + front[foe] if n[foe] else 0.0
            if (
                retreating is None
                and n[foe] > 0
                and 1 - remaining / start_hp[foe] >= sides[foe].morale
            ):
                retreating = foe
                log(
                    FightEvent(
                        t=t,
                        type=EventType.RETREAT,
                        side=foe,
                        group_size=n[foe],
                        text_hint="break and run",
                    )
                )
                if sides[foe].speed_mps > me.speed_mps:
                    log(
                        FightEvent(
                            t=t,
                            type=EventType.FLEE,
                            side=foe,
                            group_size=n[foe],
                            text_hint="escape",
                        )
                    )
                    return _outcome(n, t, events, record_events, winner=s)
            if spike[foe] > 0 and n[foe] > 0:
                # Spines: the targets hurt whoever hit them.
                log(
                    FightEvent(
                        t=t,
                        type=EventType.HIT,
                        side=foe,
                        group_size=hits,
                        damage=round(hits * spike[foe], 1),
                        text_hint="spines jab back",
                    )
                )
                back, n[s], front[s] = _apply_hits(
                    hits, spike[foe], n[s], front[s], sides[s].max_hp
                )
                if back:
                    log(
                        FightEvent(
                            t=t,
                            type=EventType.KO,
                            side=s,
                            group_size=back,
                            text_hint="go down" if back > 1 else "goes down",
                        )
                    )
        if n[0] == 0 or n[1] == 0:
            return _outcome(n, t, events, record_events)
        t = _tick_up(t + dt)
    return _outcome(n, c.MAX_FIGHT_S, events, record_events)


def _outcome(
    alive: list[int],
    t: float,
    events: list[FightEvent],
    record_events: bool,
    winner: int | None = None,
) -> RunOutcome:
    """Wrap up a fight. `winner` is given when the loser fled while still alive."""
    survivors = (alive[0], alive[1])
    if winner is not None:
        pass
    elif (survivors[0] and survivors[1]) or not (survivors[0] or survivors[1]):
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
            hint = "the fight is over"  # the narration step names the winner
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


def scale_factors(
    matchup: Matchup, sheets: list[StatSheet], reference_sheets: list[StatSheet | None] | None
) -> tuple[float, float]:
    """Scale factor k per side from `size_reference` ("horse-sized duck"); 1.0 when unset.

    Computed here in code from the two sheets' masses, never by a model.
    """
    ks = [1.0, 1.0]
    for s in (0, 1):
        if matchup.fighters[s].size_reference is None:
            continue
        ref = reference_sheets[s] if reference_sheets else None
        if ref is None:
            raise ValueError(
                f"fighter {s} has size_reference "
                f"{matchup.fighters[s].size_reference!r} but no reference stat sheet was given"
            )
        ks[s] = scale_factor(sheets[s], ref)
    return ks[0], ks[1]


def _templates(
    matchup: Matchup,
    sheets: list[StatSheet],
    rng: random.Random,
    ks: tuple[float, float],
    use_terrain: bool = True,
) -> list[Template]:
    sides = [sample_template(sheets[s], matchup.fighters[s].count, rng, ks[s]) for s in (0, 1)]
    return [apply_terrain(t, matchup.terrain) for t in sides] if use_terrain else sides


def _notes(matchup: Matchup, ks: tuple[float, float]) -> tuple[str, str]:
    """Neutral phrases the announcer can use, e.g. "scaled to horse size"."""

    def note(s: int) -> str:
        ref = matchup.fighters[s].size_reference
        return f"scaled to {ref} size" if ref and ks[s] != 1.0 else ""

    return note(0), note(1)


def _no_contest(
    matchup: Matchup, sheets: list[StatSheet], seed: int, runs: int, harmless: bool = False
) -> SimulationResult:
    """Nobody can damage anybody: end immediately with a clear hint for the announcer."""
    names = (sheets[0].display_name, sheets[1].display_name)
    if harmless:
        factor: StatName | str = StatName.ATTACK_FORCE
        explainer = f"No contest: neither {names[0]} nor {names[1]} can hurt the other."
        hint = "no contest: nobody can hurt anybody"
    else:
        terrain = matchup.terrain.value.replace("_", " ")
        factor = "habitat"
        explainer = (
            f"No contest: {names[0]} ({effective_habitat(sheets[0]).value}) and {names[1]} "
            f"({effective_habitat(sheets[1]).value}) can't reach each other in the {terrain}."
        )
        hint = "no contest: neither can reach the other"
    return SimulationResult(
        seed=seed,
        runs=runs,
        win_prob=(0.0, 0.0),
        draw_prob=0.0,
        win_prob_ci95=((0.0, 0.0), (0.0, 0.0)),
        mean_survivors=(float(matchup.fighters[0].count), float(matchup.fighters[1].count)),
        mean_duration_s=0.0,
        outcome="no_contest",
        deciding_factor=factor,
        deciding_factor_explainer=explainer,
        representative_log=[FightEvent(t=0.0, type=EventType.END, side=0, text_hint=hint)],
    )


def _simulate(
    matchup: Matchup,
    sheets: list[StatSheet],
    ks: tuple[float, float],
    seed: int,
    runs: int,
    use_terrain: bool = True,
) -> list[RunOutcome]:
    """Run `runs` fights with a fixed seed (run k always uses the same random stream)."""
    outcomes = []
    for k in range(runs):
        rng = run_rng(seed, k)
        sides = _templates(matchup, sheets, rng, ks, use_terrain)
        outcomes.append(run_once(sides, matchup.terrain, rng))
    return outcomes


def run(
    matchup: Matchup,
    stat_sheets: list[StatSheet],
    runs: int | None = None,
    reference_sheets: list[StatSheet | None] | None = None,
    explain: bool = True,
) -> SimulationResult:
    """Run the fight many times and summarize it.

    `reference_sheets[s]` is the stat sheet of fighter s's `size_reference` entity, if any.
    `explain=False` skips the deciding-factor analysis (about a dozen extra 200-run checks);
    use it for quick probes such as the fair-fight search.
    """
    runs = get_settings().sim_runs if runs is None else runs
    if runs < 1:
        raise ValueError("runs must be at least 1")
    seed = make_seed(matchup, stat_sheets[0].sheet_hash, stat_sheets[1].sheet_hash)
    ks = scale_factors(matchup, stat_sheets, reference_sheets)
    habitats = [effective_habitat(sheet) for sheet in stat_sheets]
    if not can_engage(matchup.terrain, habitats[0], habitats[1]):
        return _no_contest(matchup, stat_sheets, seed, runs)
    central = [
        apply_terrain(
            sample_template(stat_sheets[s], 1, random.Random(0), ks[s], central=True),
            matchup.terrain,
        )
        for s in (0, 1)
    ]
    if not (can_hurt(central[0], central[1]) or can_hurt(central[1], central[0])):
        return _no_contest(matchup, stat_sheets, seed, runs, harmless=True)

    outcomes = _simulate(matchup, stat_sheets, ks, seed, runs)

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
    sides = _templates(matchup, stat_sheets, rng, ks)
    replay = run_once(sides, matchup.terrain, rng, record_events=True, notes=_notes(matchup, ks))

    if explain:
        decision = decide(
            matchup,
            stat_sheets,
            outcomes,
            lambda m, sh, terrain, n: _simulate(m, sh, ks, seed, n, terrain),
        )
        factor, explainer = decision.factor, decision.explainer
    else:
        factor, explainer = "mass_kg", "Deciding factor not computed."

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
        deciding_factor=factor,
        deciding_factor_explainer=explainer,
        representative_log=replay.events,
    )
