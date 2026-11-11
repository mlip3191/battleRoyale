// The replay timeline outside Phaser: order, speed, skip, key frames, and who-did-what (D05).
import { describe, expect, test } from "vitest";
import type { FightEvent, SimulationResult } from "../api/client.ts";
import fixture from "../fixtures/simulation-result.json";
import thousand from "./fixtures/thousand-vs-one.json";
import {
  MAX_REPLAY_MS,
  MIN_BEAT_MS,
  ReplayClock,
  beatTimes,
  buildTimeline,
  keyFrames,
  type Speed,
} from "./timeline.ts";

const result = fixture as SimulationResult;
const bigResult = thousand as SimulationResult;
const WOLF_COUNTS: readonly [number, number] = [1, 6]; // the fixture's matchup: a grizzly vs 6 gray wolves

// Run a clock at one speed in 16 ms frames and collect every reported event index.
function playThrough(r: SimulationResult, speed: Speed, counts = WOLF_COUNTS) {
  const clock = new ReplayClock(buildTimeline(r, counts));
  clock.setSpeed(speed);
  clock.play();
  const seen: number[] = [];
  let frames = 0;
  while (!clock.done && frames < 100_000) {
    seen.push(...clock.advance(16));
    frames += 1;
  }
  return { seen, frames, clock };
}

const allIndexes = (r: SimulationResult) =>
  r.representative_log.map((_, i) => i);

// A minimal event for semantics tests.
const ev = (e: Partial<FightEvent> & Pick<FightEvent, "type">): FightEvent => ({
  t: 0,
  side: 0,
  actor: null,
  target: null,
  group_size: 1,
  damage: null,
  text_hint: "",
  ...e,
});

describe("every event is visited exactly once, in order", () => {
  test.each([1, 2] as const)("fixture log at %ix", (speed) => {
    expect(playThrough(result, speed).seen).toEqual(allIndexes(result));
  });

  test.each([1, 2] as const)("1,000-v-1 engine log at %ix", (speed) => {
    const { seen } = playThrough(bigResult, speed, [1000, 1]);
    expect(seen).toEqual(allIndexes(bigResult));
  });

  test("2x finishes in about half the frames of 1x", () => {
    const slow = playThrough(result, 1).frames;
    const fast = playThrough(result, 2).frames;
    expect(fast).toBeLessThan(slow);
    expect(Math.abs(fast * 2 - slow)).toBeLessThanOrEqual(2);
  });

  test("switching speed mid-replay still visits each event once", () => {
    const clock = new ReplayClock(buildTimeline(result, WOLF_COUNTS));
    clock.play();
    const seen = [...clock.advance(2000)];
    clock.setSpeed(2);
    while (!clock.done) seen.push(...clock.advance(33));
    expect(seen).toEqual(allIndexes(result));
  });

  test("pausing stops time and reports nothing", () => {
    const clock = new ReplayClock(buildTimeline(result, WOLF_COUNTS));
    clock.play();
    const first = clock.advance(100);
    clock.pause();
    expect(clock.advance(60_000)).toEqual([]);
    clock.play();
    const rest: number[] = [];
    while (!clock.done) rest.push(...clock.advance(50));
    expect([...first, ...rest]).toEqual(allIndexes(result));
  });

  test("skip to end visits the remaining events once and then stops", () => {
    const clock = new ReplayClock(buildTimeline(result, WOLF_COUNTS));
    clock.play();
    const before = clock.advance(3000);
    expect(before.length).toBeGreaterThan(0);
    const after = clock.skipToEnd();
    expect([...before, ...after]).toEqual(allIndexes(result));
    expect(clock.skipToEnd()).toEqual([]);
    expect(clock.done).toBe(true);
    expect(clock.playing).toBe(false);
  });
});

describe("timing", () => {
  test("beats are back to back and 2x halves every start and length", () => {
    const { beats, totalMs } = buildTimeline(result, WOLF_COUNTS);
    beats.forEach((b, i) => {
      expect(b.index).toBe(i);
      if (i > 0)
        expect(b.start).toBe(beats[i - 1].start + beats[i - 1].duration);
      expect(beatTimes(b, 2)).toEqual({
        start: b.start / 2,
        duration: b.duration / 2,
      });
    });
    const last = beats[beats.length - 1];
    expect(totalMs).toBe(last.start + last.duration);
  });

  test("a 300-event log is squeezed to the replay limit, never below the shortest beat", () => {
    const log = Array.from({ length: 300 }, (_, i) =>
      ev({ type: "hit", t: i, actor: 0, target: 0, damage: 1 }),
    );
    const { beats, totalMs } = buildTimeline(
      { representative_log: log, outcome: "win_0" },
      [1, 1],
    );
    expect(totalMs).toBeLessThanOrEqual(MAX_REPLAY_MS + 300);
    expect(Math.min(...beats.map((b) => b.duration))).toBeGreaterThanOrEqual(
      MIN_BEAT_MS,
    );
  });

  test("an empty log gives an empty timeline that is already done", () => {
    const timeline = buildTimeline(
      { representative_log: [], outcome: "no_contest" },
      [1, 1],
    );
    expect(timeline.beats).toEqual([]);
    expect(keyFrames(timeline.beats)).toEqual([]);
    expect(new ReplayClock(timeline).done).toBe(true);
  });
});

describe("reduced-motion key frames", () => {
  test("fixture: the start, each KO, and the end", () => {
    const { beats } = buildTimeline(result, WOLF_COUNTS);
    const kos = beats
      .filter((b) => b.kind === "ko" || b.kind === "crowd-ko")
      .map((b) => b.index);
    expect(kos.length).toBeGreaterThan(0);
    expect(keyFrames(beats).map((b) => b.index)).toEqual([
      0,
      ...kos,
      beats.length - 1,
    ]);
  });

  test('a summary KO ("more go down") is a key frame', () => {
    const log = [
      ev({ type: "approach", side: 0 }),
      ev({ type: "approach", side: 1 }),
      ev({ type: "hit", side: 0, actor: 0, target: 1, damage: 5 }),
      ev({ type: "ko", side: 1, actor: 1 }),
      ev({ type: "ko", side: 1, group_size: 40, text_hint: "more go down" }),
      ev({ type: "end", side: 0 }),
    ];
    const { beats } = buildTimeline(
      { representative_log: log, outcome: "win_0" },
      [1, 60],
    );
    expect(keyFrames(beats).map((b) => b.index)).toEqual([0, 3, 4, 5]);
  });

  test("a log cut off before END still ends on its last event", () => {
    const log = [
      ev({ type: "approach" }),
      ev({ type: "hit", actor: 0, target: 0, damage: 2 }),
      ev({ type: "miss", side: 1, actor: 0, target: 0 }),
    ];
    const { beats } = buildTimeline(
      { representative_log: log, outcome: "win_0" },
      [1, 1],
    );
    expect(keyFrames(beats).map((b) => b.index)).toEqual([0, 2]);
  });
});

describe("who acts and who is affected", () => {
  const one = (e: FightEvent, outcome: SimulationResult["outcome"] = "win_0") =>
    buildTimeline({ representative_log: [e], outcome }, [3, 3]).beats[0];

  test("a KO's side is the side that fell, and its actor is the fallen fighter", () => {
    const beat = one(ev({ type: "ko", side: 1, actor: 2 }));
    expect(beat).toMatchObject({
      kind: "ko",
      affectedSide: 1,
      target: 2,
      actorSide: null,
      group: false,
    });
  });

  test("a spines HIT already arrives swapped: the defender's side strikes the attacker", () => {
    // Side 0 attacks side 1's porcupine; its spines jab back at attacker 0.
    const attack = one(
      ev({ type: "hit", side: 0, actor: 0, target: 1, damage: 3 }),
    );
    const spines = one(
      ev({
        type: "hit",
        side: 1,
        actor: 1,
        target: 0,
        damage: 2,
        text_hint: "spines jab back",
      }),
    );
    expect(attack).toMatchObject({ actorSide: 0, affectedSide: 1, target: 1 });
    expect(spines).toMatchObject({
      kind: "hit",
      actorSide: 1,
      actor: 1,
      affectedSide: 0,
      target: 0,
      damage: 2,
    });
  });

  test("the summary KO is a crowd falling, never a single fighter", () => {
    const beat = one(
      ev({ type: "ko", side: 0, group_size: 120, text_hint: "more go down" }),
    );
    expect(beat).toMatchObject({
      kind: "crowd-ko",
      affectedSide: 0,
      target: null,
      group: true,
      count: 120,
    });
  });

  test("swarm hits are group hits with the group's total damage", () => {
    const beat = one(ev({ type: "hit", side: 0, group_size: 6, damage: 8.6 }));
    expect(beat).toMatchObject({
      kind: "hit",
      actorSide: 0,
      affectedSide: 1,
      group: true,
      count: 6,
      damage: 8.6,
    });
  });

  test("attack is a lunge, miss has no damage, retreat and flee are the runner's side", () => {
    expect(one(ev({ type: "attack", side: 1, actor: 0, target: 0 })).kind).toBe(
      "lunge",
    );
    expect(
      one(ev({ type: "miss", side: 1, actor: 0, target: 0 })),
    ).toMatchObject({ kind: "miss", damage: null, affectedSide: 0 });
    expect(one(ev({ type: "retreat", side: 1 }))).toMatchObject({
      kind: "retreat",
      actorSide: 1,
    });
    expect(one(ev({ type: "flee", side: 0 }))).toMatchObject({
      kind: "flee",
      actorSide: 0,
    });
    expect(one(ev({ type: "stalemate" })).kind).toBe("stalemate");
  });

  test("END names a winner only when the outcome has one", () => {
    expect(one(ev({ type: "end", side: 1 }), "win_1").winner).toBe(1);
    expect(one(ev({ type: "end", side: 0 }), "draw").winner).toBeNull();
    expect(one(ev({ type: "end", side: 0 }), "no_contest").winner).toBeNull();
  });

  test("swarm mode comes from the matchup counts, not from group_size", () => {
    const small: Pick<SimulationResult, "representative_log" | "outcome"> = {
      representative_log: [ev({ type: "approach", group_size: 900 })],
      outcome: "win_0",
    };
    expect(buildTimeline(small, [200, 1]).swarm).toBe(false);
    expect(buildTimeline(small, [1, 201]).swarm).toBe(true);
    expect(buildTimeline(bigResult, [1000, 1]).swarm).toBe(true);
  });

  test("the 1,000-v-1 engine log is all crowd events (swarm mode)", () => {
    const { beats } = buildTimeline(bigResult, [1000, 1]);
    const fighting = beats.filter((b) =>
      ["hit", "ko", "crowd-ko"].includes(b.kind),
    );
    expect(fighting.length).toBeGreaterThan(0);
    expect(fighting.every((b) => b.group)).toBe(true);
    expect(beats.some((b) => b.kind === "ko")).toBe(false);
  });
});
