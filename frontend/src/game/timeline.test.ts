// The replay timeline outside Phaser: order, speed, skip, key frames, and who-did-what (D05).
import { describe, expect, test } from "vitest";
import type { FightEvent, SimulationResult } from "../api/client.ts";
import fixture from "../fixtures/simulation-result.json";
import hundredVsFive from "./fixtures/hundred-vs-five.json";
import thousand from "./fixtures/thousand-vs-one.json";
import twoHundredVsFive from "./fixtures/two-hundred-vs-five.json";
import {
  BEAT_MS,
  MAX_REPLAY_MS,
  MISS_LABEL,
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

  test("a short log that already fits plays at full length, not squeezed", () => {
    const { beats, totalMs } = buildTimeline(result, WOLF_COUNTS);
    beats.forEach((b) => expect(b.duration).toBe(BEAT_MS[b.kind]));
    expect(totalMs).toBe(beats.reduce((sum, b) => sum + BEAT_MS[b.kind], 0));
    expect(totalMs).toBeLessThan(MAX_REPLAY_MS);
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

// The approved length of a replay at 1x (#580: T3 said a fight should last about 15 s; the PM
// chose about 20 s). Pinned here as a number, so the cap can't drift back up unnoticed.
const TARGET_MS = 20_000;

// A log of `n` events with the engine's usual shape: both sides close in, then mostly hits with
// some misses, the given knock-outs and retreat near the end, and END last.
function engineLikeLog(n: number, kos: number, misses: number): FightEvent[] {
  const log: FightEvent[] = [
    ev({ type: "approach", side: 0 }),
    ev({ type: "approach", side: 1, group_size: 6 }),
  ];
  const fighting = n - log.length - kos - 2; // minus the KOs, the retreat and END
  for (let i = 0; i < fighting; i += 1) {
    // Exactly `misses` misses, spread evenly through the fighting.
    const miss =
      Math.floor(((i + 1) * misses) / fighting) >
      Math.floor((i * misses) / fighting);
    const type = miss ? "miss" : "hit";
    log.push(ev({ type, t: i, side: 1, actor: i % 6, target: 0, damage: 4 }));
  }
  for (let k = 0; k < kos; k += 1)
    log.push(ev({ type: "ko", side: k % 2 === 0 ? 1 : 0, actor: 0 }));
  log.splice(log.length - 1, 0, ev({ type: "retreat", side: 0 }));
  log.push(ev({ type: "end", side: 1 }));
  return log;
}

describe("replay length (#580)", () => {
  const play = (log: FightEvent[], counts: readonly [number, number]) =>
    playThrough({ ...result, representative_log: log }, 1, counts);

  test("the cap is about 20 s and even the engine's longest log fits it", () => {
    expect(MAX_REPLAY_MS).toBeLessThanOrEqual(TARGET_MS);
    // The engine keeps at most 300 events (MAX_LOG_EVENTS), so 300 floor-length beats must fit.
    expect(300 * MIN_BEAT_MS).toBeLessThanOrEqual(MAX_REPLAY_MS);
  });

  test("a 151-event grizzly-vs-6-wolves-like log plays in about 20 s at 1x", () => {
    // Same mix as the engine's "a grizzly bear vs 6 gray wolves in a forest": 151 events
    // (123 hits, 22 misses, 2 KOs, a retreat), which took about 82 s before #580.
    const log = engineLikeLog(151, 2, 22);
    expect(log).toHaveLength(151);
    const count = (type: string) => log.filter((e) => e.type === type).length;
    expect([count("hit"), count("miss"), count("ko")]).toEqual([123, 22, 2]);
    const { beats, totalMs } = buildTimeline(
      { representative_log: log, outcome: "win_1" },
      WOLF_COUNTS,
    );
    expect(totalMs).toBeLessThanOrEqual(TARGET_MS);
    expect(totalMs).toBeGreaterThan(15_000); // squeezed to the cap, not cut short
    expect(Math.min(...beats.map((b) => b.duration))).toBeGreaterThanOrEqual(
      MIN_BEAT_MS,
    );
    const { seen, frames } = play(log, WOLF_COUNTS);
    expect(seen).toEqual(log.map((_, i) => i));
    expect(frames * 16).toBeLessThanOrEqual(TARGET_MS + 16);
  });

  test("a 300-event log (the engine's limit) still fits in about 20 s at 1x", () => {
    const log = engineLikeLog(300, 2, 40);
    expect(log).toHaveLength(300);
    const { beats, totalMs } = buildTimeline(
      { representative_log: log, outcome: "win_1" },
      WOLF_COUNTS,
    );
    expect(totalMs).toBeLessThanOrEqual(TARGET_MS);
    expect(totalMs).toBeGreaterThan(15_000);
    expect(Math.min(...beats.map((b) => b.duration))).toBeGreaterThanOrEqual(
      MIN_BEAT_MS,
    );
    expect(play(log, WOLF_COUNTS).seen).toEqual(log.map((_, i) => i));
  });

  test("a big crowd (100 ducks falling one by one) plays in about 20 s at 1x", () => {
    const crowd = hundredVsFive as SimulationResult;
    const { totalMs } = buildTimeline(crowd, [100, 5]);
    expect(crowd.representative_log.length).toBeGreaterThan(200);
    expect(totalMs).toBeLessThanOrEqual(TARGET_MS);
    expect(totalMs).toBeGreaterThan(15_000);
    const { seen } = playThrough(crowd, 1, [100, 5]);
    expect(seen).toEqual(allIndexes(crowd));
  });
});

describe("reduced-motion key frames", () => {
  test("fixture: the start, each side closing in, each KO, and the end", () => {
    const { beats } = buildTimeline(result, WOLF_COUNTS);
    const kinds = (...k: string[]) =>
      beats.filter((b) => k.includes(b.kind)).map((b) => b.index);
    const approaches = kinds("approach");
    const kos = kinds("ko", "crowd-ko");
    expect(approaches).toEqual([0, 1]);
    expect(kos.length).toBeGreaterThan(0);
    expect(keyFrames(beats).map((b) => b.index)).toEqual([
      ...approaches,
      ...kos,
      beats.length - 1,
    ]);
  });

  test("the walk-in is a key frame for each side, even after other events", () => {
    const log = [
      ev({ type: "approach", side: 0 }),
      ev({ type: "miss", side: 0, actor: 0, target: 0 }),
      ev({ type: "approach", side: 1 }),
      ev({ type: "hit", side: 1, actor: 0, target: 0, damage: 3 }),
      ev({ type: "end", side: 1 }),
    ];
    const { beats } = buildTimeline(
      { representative_log: log, outcome: "win_1" },
      [1, 1],
    );
    expect(keyFrames(beats).map((b) => b.index)).toEqual([0, 2, 4]);
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
    expect(keyFrames(beats).map((b) => b.index)).toEqual([0, 1, 3, 4, 5]);
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

  test("a miss is labeled in plain words, not 'whiff' (#505)", () => {
    expect(MISS_LABEL).toBe("miss!");
    expect(MISS_LABEL.toLowerCase()).not.toContain("whiff");
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

  test("a swarm log below 200 a side (D-50, by work) is still swarm mode (#302)", () => {
    const log = twoHundredVsFive as SimulationResult;
    // 200 ducks v 5 lions: neither side is over the threshold, but the engine ran it in groups.
    expect(buildTimeline(log, [200, 5]).swarm).toBe(true);
    // A one-by-one log of the same size has actors on its hits and stays false.
    const single: Pick<SimulationResult, "representative_log" | "outcome"> = {
      representative_log: [
        ev({ type: "approach", group_size: 150 }),
        ev({ type: "hit", side: 0, actor: 3, target: 0, group_size: 1 }),
        ev({ type: "ko", side: 1, actor: 0 }),
      ],
      outcome: "win_0",
    };
    expect(buildTimeline(single, [150, 1]).swarm).toBe(false);
  });

  test("a swarm hit of one still counts; a summary KO does not (#302)", () => {
    const hitOfOne: Pick<SimulationResult, "representative_log" | "outcome"> = {
      representative_log: [
        ev({ type: "hit", side: 0, actor: null, group_size: 1 }),
      ],
      outcome: "win_0",
    };
    expect(buildTimeline(hitOfOne, [150, 1]).swarm).toBe(true);
    const summaryKo: Pick<SimulationResult, "representative_log" | "outcome"> =
      {
        representative_log: [
          ev({ type: "hit", side: 0, actor: 3, target: 0, group_size: 1 }),
          ev({ type: "ko", side: 1, actor: null, group_size: 40 }),
        ],
        outcome: "win_0",
      };
    expect(buildTimeline(summaryKo, [150, 1]).swarm).toBe(false);
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
