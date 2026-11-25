// How the announcer lines up each moment's lines (#601): a moment's lines wait for the ones still
// talking, so none is cut off. The gaps are the ones /qa measured on #585 for the three committed
// crowd fixtures at 1x, in ms between the starts of the play-by-play lines.
import { expect, test } from "vitest";
import { arrive, MAX_WAITING, next, type VoiceCue } from "./voice-queue.ts";

const cue = (at: number, start = at * 10, end = start + 3): VoiceCue => ({
  at,
  start,
  end,
});

test("a moment that arrives while the voice is silent plays now and replaces any waiting one", () => {
  const turn = arrive([cue(1)], cue(2), false);
  expect(turn.play).toEqual(cue(2));
  expect(turn.waiting).toEqual([]);
});

test("a moment that arrives while the voice is talking waits, and plays after the ones before it", () => {
  const first = arrive([], cue(2), true);
  expect(first.play).toBeNull();
  const second = arrive(first.waiting, cue(3), true);
  expect(second.waiting).toEqual([cue(2), cue(3)]);
  const turn = next(second.waiting);
  expect(turn.play).toEqual(cue(2));
  expect(next(turn.waiting).play).toEqual(cue(3));
  expect(next([]).play).toBeNull();
});

test("a voice that is far behind drops the oldest waiting moment, never the newest", () => {
  let waiting: VoiceCue[] = [];
  for (let at = 0; at < MAX_WAITING + 2; at += 1) {
    waiting = arrive(waiting, cue(at), true).waiting;
  }
  expect(waiting).toHaveLength(MAX_WAITING);
  expect(waiting.at(-1)?.at).toBe(MAX_WAITING + 1);
});

// Play the lines through the queue: each starts at the time its moment arrives or when the line
// before it ends, and says its whole stretch. Returns how long each line was actually heard.
function heard(gapsMs: number[], spokenMs: number): number[] {
  const arrivals = gapsMs.reduce<number[]>(
    (times, gap) => [...times, (times.at(-1) ?? 0) + gap],
    [],
  );
  const lengths: number[] = [];
  let waiting: VoiceCue[] = [];
  let talkingUntil = 0; // when the voice goes quiet
  const play = (c: VoiceCue, from: number) => {
    lengths.push(spokenMs); // the whole stretch of the file for this moment
    talkingUntil = from + spokenMs;
    return c;
  };
  // Every arrival, and the end of each talking stretch, in time order.
  let nextArrival = 0;
  while (nextArrival < arrivals.length || waiting.length > 0) {
    const arrivesAt =
      nextArrival < arrivals.length ? arrivals[nextArrival] : Infinity;
    const endsAt = waiting.length > 0 ? talkingUntil : Infinity;
    if (arrivesAt <= endsAt) {
      const talking = arrivesAt < talkingUntil;
      const turn = arrive(waiting, cue(nextArrival), talking);
      waiting = turn.waiting;
      if (turn.play) play(turn.play, arrivesAt);
      nextArrival += 1;
    } else {
      const turn = next(waiting);
      waiting = turn.waiting;
      if (turn.play) play(turn.play, endsAt);
    }
  }
  return lengths;
}

const FIXTURE_GAPS: Record<string, number[]> = {
  "hundred-vs-five": [640, 3318, 4838, 10847, 100],
  "two-hundred-vs-five": [715, 9004, 6602, 2877, 244],
  "thousand-vs-one": [956, 8515, 8945, 709, 297],
};

test.each(Object.entries(FIXTURE_GAPS))(
  "on %s every play-by-play line is heard whole, none for under a second (#601)",
  (_name, gaps) => {
    for (const spokenMs of [2000, 3000, 4000]) {
      const lengths = heard(gaps, spokenMs);
      expect(lengths).toHaveLength(gaps.length); // no line was dropped
      expect(Math.min(...lengths)).toBeGreaterThanOrEqual(1000);
    }
  },
);
