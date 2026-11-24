// Turns a simulation's replay log into timed "beats" for the battle scene (D05).
// Pure functions, no Phaser: the scene only plays these beats and never decides an outcome.
// Event meanings follow docs/simulation-api.md ("What the replay log contains").
import type { FightEvent, SimulationResult } from "../api/client.ts";

export type Side = 0 | 1;
export type Speed = 1 | 2 | 5 | 10;
// The replay speeds offered under the stage; 5x and 10x get through a long fight quickly (#577).
export const SPEEDS: readonly Speed[] = [1, 2, 5, 10];

// What the scene should animate for one event.
export type BeatKind =
  | "approach"
  | "lunge"
  | "hit"
  | "miss"
  | "ko"
  | "crowd-ko"
  | "retreat"
  | "flee"
  | "stalemate"
  | "end";

// One event of the log, placed on the replay timeline (times in ms at 1x speed).
export interface Beat {
  index: number; // position of the event in representative_log
  kind: BeatKind;
  start: number;
  duration: number;
  actorSide: Side | null; // the side doing something (closing in, striking, running)
  actor: number | null; // fighter index within actorSide, null for a group event
  affectedSide: Side | null; // the side on the receiving end (hit, missed, fallen)
  target: number | null; // fighter index within affectedSide (the fallen one for a KO)
  group: boolean; // true when a crowd acted or fell together (no single fighter to point at)
  count: number; // how many acted or fell (group_size)
  damage: number | null; // hit points from the log, shown as-is (never computed here)
  hpLeft: [number, number] | null; // each side's hit points still standing after it (#575), from the log
  winner: Side | null; // END only: the winning side, null for a draw or no contest
  hint: string; // flavor text for captions; never used to decide anything
}

export interface Timeline {
  beats: Beat[];
  totalMs: number; // length at 1x speed
  swarm: boolean; // the fight ran in swarm mode: a side over SWARM_THRESHOLD, or group events in the log
  startHp: [number, number] | null; // each side's starting hit points (#575); null for an older result
}

export const SWARM_THRESHOLD = 200;

// The word floated over a fighter who was swung at and missed. Plain on purpose: a tester read
// "whiff" as one animal smelling the other (#505).
export const MISS_LABEL = "miss!";

// Base length of each kind of beat at 1x, before long logs are squeezed.
export const BEAT_MS: Record<BeatKind, number> = {
  approach: 900,
  lunge: 350,
  hit: 550,
  miss: 450,
  ko: 800,
  "crowd-ko": 800,
  retreat: 800,
  flee: 900,
  stalemate: 1200,
  end: 1600,
};

// Long logs are squeezed so a replay lasts at most this long at 1x, but no beat goes below
// MIN_BEAT_MS. About 20 s since #580 (90 s before): a tester said a fight should last about 15 s,
// and a 151-event bear-vs-6-wolves log ran about 82 s. A log that already fits is not squeezed.
export const MAX_REPLAY_MS = 20_000;
// 60 ms, so even the engine's longest log (MAX_LOG_EVENTS, 300 events) fits the cap with room
// to spare: 300 x 60 ms = 18 s. That is still about four frames at 60 fps, enough to see a hit
// flash; at 2x speed the old 150 ms floor was already 75 ms on screen.
export const MIN_BEAT_MS = 60;

const other = (side: Side): Side => (side === 0 ? 1 : 0);

// Swarm mode (D-50): the engine uses it for a side over SWARM_THRESHOLD and also for a slow fight
// below that, so the counts alone are not enough. A swarm log has group HITs (`actor` is null,
// `group_size` can be 1); a one-by-one HIT always has an actor. KO is not checked: the summary KO
// ("more go down") has no actor in any fight (simulation guide).
export const isSwarm = (
  counts: readonly [number, number],
  log: readonly FightEvent[] = [],
) =>
  counts[0] > SWARM_THRESHOLD ||
  counts[1] > SWARM_THRESHOLD ||
  log.some((e) => e.type === "hit" && e.actor == null);

type Who = Omit<
  Beat,
  "index" | "start" | "duration" | "hint" | "damage" | "hpLeft"
>;

// Who acts and who is affected for one event, applying the per-type meanings of side/actor/target.
function describe(
  event: FightEvent,
  outcome: SimulationResult["outcome"],
): Who {
  const side = event.side;
  const count = event.group_size ?? 1;
  const none = {
    actorSide: null,
    actor: null,
    affectedSide: null,
    target: null,
    winner: null,
  };
  switch (event.type) {
    case "approach":
      // One per side at t=0; no positions in the log, so the scene closes the gap itself.
      return {
        ...none,
        kind: "approach",
        actorSide: side,
        affectedSide: other(side),
        group: true,
        count,
      };
    case "attack":
    case "hit":
    case "miss": {
      // side = the striker's side. A "spines jab back" hit already arrives swapped (side = the
      // spiny defender, target = the attacker it hurt), so reading side/actor/target as-is is right.
      const group = event.actor === null;
      const kind =
        event.type === "attack"
          ? "lunge"
          : event.type === "hit"
            ? "hit"
            : "miss";
      return {
        ...none,
        kind,
        actorSide: side,
        actor: event.actor ?? null,
        affectedSide: other(side),
        target: event.target ?? null,
        group,
        count,
      };
    }
    case "ko": {
      // side = the side that went down; actor = the fallen fighter. No actor = a crowd fell,
      // including the "more go down" summary KO, which must never be looked up as one fighter.
      // A machine whose operating time ran out also arrives as a plain KO (hint "out of action:
      // its operating time ran out"). It is animated like any KO; the wording ("breaks down", not
      // "dies") belongs to the captions, which may show text_hint but never branch on it.
      const fallen = event.actor ?? null;
      return {
        ...none,
        kind: fallen === null ? "crowd-ko" : "ko",
        affectedSide: side,
        target: fallen,
        group: fallen === null,
        count,
      };
    }
    case "retreat":
    case "flee":
      return {
        ...none,
        kind: event.type,
        actorSide: side,
        group: true,
        count,
      };
    case "stalemate":
      return { ...none, kind: "stalemate", group: false, count };
    case "end":
      // END side is the winner only when there is one (0 for a draw or no contest).
      return {
        ...none,
        kind: "end",
        winner: outcome === "win_0" || outcome === "win_1" ? side : null,
        group: false,
        count,
      };
  }
}

// How much to shrink every beat so the log fits in MAX_REPLAY_MS. Beats that would drop below
// MIN_BEAT_MS are held at that floor and take their share of the time first; the rest share
// what is left. 1 when the log already fits.
function squeezeFactor(raw: readonly number[]): number {
  let rest = raw.reduce((a, b) => a + b, 0); // length of the beats not held at the floor
  if (rest <= MAX_REPLAY_MS) return 1;
  let budget = MAX_REPLAY_MS; // time left for those beats
  for (const ms of [...raw].sort((a, b) => a - b)) {
    if ((ms * budget) / rest >= MIN_BEAT_MS) break; // this beat and every longer one stay above
    budget -= MIN_BEAT_MS;
    rest -= ms;
  }
  return rest > 0 ? Math.max(0, budget) / rest : 0;
}

// Build the replay timeline: one beat per event, in log order, back to back.
// Beat lengths depend only on the kind of event; the log's `t` is ignored on purpose (a summary
// KO's `t` is the last logged event, not when that crowd fell), so do not time beats from `t`.
export function buildTimeline(
  result: Pick<SimulationResult, "representative_log" | "outcome"> &
    Partial<Pick<SimulationResult, "start_hp">>,
  counts: readonly [number, number],
): Timeline {
  const log = result.representative_log;
  const raw = log.map((event) => BEAT_MS[describe(event, result.outcome).kind]);
  const squeeze = squeezeFactor(raw);
  let clock = 0;
  const beats = log.map((event, index): Beat => {
    // Rounded down, so the squeezed beats never add up to more than MAX_REPLAY_MS.
    const duration = Math.max(MIN_BEAT_MS, Math.floor(raw[index] * squeeze));
    const beat: Beat = {
      index,
      start: clock,
      duration,
      damage: event.damage ?? null,
      hpLeft: event.hp_left ?? null,
      hint: event.text_hint,
      ...describe(event, result.outcome),
    };
    clock += duration;
    return beat;
  });
  const startHp = result.start_hp ?? null;
  return { beats, totalMs: clock, swarm: isSwarm(counts, log), startHp };
}

// A beat's start and length in real ms at the given speed.
export const beatTimes = (beat: Beat, speed: Speed) => ({
  start: beat.start / speed,
  duration: beat.duration / speed,
});

// Reduced motion shows key frames only: the start, each side closing in (a jump, no walking),
// every knock-out (summary KOs too), and the end.
export function keyFrames(beats: readonly Beat[]): Beat[] {
  if (beats.length === 0) return [];
  const last = beats.length - 1;
  const key = new Set<BeatKind>(["approach", "ko", "crowd-ko"]);
  return beats.filter((b, i) => i === 0 || i === last || key.has(b.kind));
}

// Plays a timeline: advance(ms) moves time forward and reports each event index exactly once, in order.
export class ReplayClock {
  readonly beats: readonly Beat[];
  readonly totalMs: number;
  time = 0; // timeline position in ms at 1x
  speed: Speed = 1;
  playing = false;
  private next = 0; // first beat not yet reached

  constructor(timeline: Pick<Timeline, "beats" | "totalMs">) {
    this.beats = timeline.beats;
    this.totalMs = timeline.totalMs;
  }

  // True once every event has been reached.
  get done() {
    return this.next >= this.beats.length;
  }

  play() {
    this.playing = !this.done;
  }

  pause() {
    this.playing = false;
  }

  setSpeed(speed: Speed) {
    this.speed = speed;
  }

  // Move forward by real milliseconds (scaled by speed); returns the event indexes newly reached.
  advance(realMs: number): number[] {
    if (!this.playing || realMs <= 0) return [];
    this.time = Math.min(this.totalMs, this.time + realMs * this.speed);
    const reached = this.reachUntil((beat) => beat.start <= this.time);
    if (this.done) this.playing = false;
    return reached;
  }

  // Jump to the end; returns every event index not reached yet, in order.
  skipToEnd(): number[] {
    this.time = this.totalMs;
    const reached = this.reachUntil(() => true);
    this.playing = false;
    return reached;
  }

  // Reach beats in order while the test passes.
  private reachUntil(test: (beat: Beat) => boolean): number[] {
    const reached: number[] = [];
    while (this.next < this.beats.length && test(this.beats[this.next])) {
      reached.push(this.beats[this.next].index);
      this.next += 1;
    }
    return reached;
  }
}
