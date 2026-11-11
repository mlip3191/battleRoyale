// Turns a simulation's replay log into timed "beats" for the battle scene (D05).
// Pure functions, no Phaser: the scene only plays these beats and never decides an outcome.
// Event meanings follow docs/simulation-api.md ("What the replay log contains").
import type { FightEvent, SimulationResult } from "../api/client.ts";

export type Side = 0 | 1;
export type Speed = 1 | 2;

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
  winner: Side | null; // END only: the winning side, null for a draw or no contest
  hint: string; // flavor text for captions; never used to decide anything
}

export interface Timeline {
  beats: Beat[];
  totalMs: number; // length at 1x speed
  swarm: boolean; // either side has more than SWARM_THRESHOLD fighters
}

export const SWARM_THRESHOLD = 200;

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

// Long logs are squeezed so a replay lasts at most this long at 1x, but no beat goes below MIN_BEAT_MS.
export const MAX_REPLAY_MS = 90_000;
export const MIN_BEAT_MS = 150;

const other = (side: Side): Side => (side === 0 ? 1 : 0);

// Swarm mode is decided from the matchup counts, never from group_size (simulation guide).
export const isSwarm = (counts: readonly [number, number]) =>
  counts[0] > SWARM_THRESHOLD || counts[1] > SWARM_THRESHOLD;

type Who = Omit<Beat, "index" | "start" | "duration" | "hint" | "damage">;

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

// Build the replay timeline: one beat per event, in log order, back to back.
// Beat lengths depend only on the kind of event; the log's `t` is ignored on purpose (a summary
// KO's `t` is the last logged event, not when that crowd fell), so do not time beats from `t`.
export function buildTimeline(
  result: Pick<SimulationResult, "representative_log" | "outcome">,
  counts: readonly [number, number],
): Timeline {
  const log = result.representative_log;
  const raw = log.map((event) => BEAT_MS[describe(event, result.outcome).kind]);
  const sum = raw.reduce((a, b) => a + b, 0);
  const squeeze = sum > MAX_REPLAY_MS ? MAX_REPLAY_MS / sum : 1;
  let clock = 0;
  const beats = log.map((event, index): Beat => {
    const duration = Math.max(MIN_BEAT_MS, Math.round(raw[index] * squeeze));
    const beat: Beat = {
      index,
      start: clock,
      duration,
      damage: event.damage ?? null,
      hint: event.text_hint,
      ...describe(event, result.outcome),
    };
    clock += duration;
    return beat;
  });
  return { beats, totalMs: clock, swarm: isSwarm(counts) };
}

// A beat's start and length in real ms at the given speed.
export const beatTimes = (beat: Beat, speed: Speed) => ({
  start: beat.start / speed,
  duration: beat.duration / speed,
});

// Reduced motion shows key frames only: the start, every knock-out (summary KOs too), and the end.
export function keyFrames(beats: readonly Beat[]): Beat[] {
  if (beats.length === 0) return [];
  const last = beats.length - 1;
  return beats.filter(
    (b, i) => i === 0 || i === last || b.kind === "ko" || b.kind === "crowd-ko",
  );
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
