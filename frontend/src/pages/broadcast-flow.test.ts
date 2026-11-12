// The broadcast logic outside React: show phases, caption sync, audio choice, and degraded-mode notes.
import { describe, expect, test } from "vitest";
import type {
  Asset,
  BattleRecord,
  ScriptLine,
  SimulationResult,
  StatSheet,
} from "../api/client.ts";
import done from "../fixtures/battle-record-done.json";
import running from "../fixtures/battle-record-running.json";
import {
  LINE_MS,
  START,
  audioPlan,
  canSkip,
  captionsAt,
  lineMs,
  linesOf,
  nextShow,
  placeLines,
  sideNames,
  unavailableNote,
  verdictReveal,
  type Show,
} from "./broadcast-flow.ts";

const battle = done as unknown as BattleRecord;
const result = battle.result as SimulationResult;
const eventCount = result.representative_log.length;
const pbp = linesOf(battle.scripts, "play_by_play");

const line = (text: string, at_event: number | null): ScriptLine => ({
  speaker: "announcer",
  text,
  at_event,
});
const asset = (kind: Asset["kind"], url: string): Asset => ({
  asset_id: url,
  kind,
  url,
  prompt_hash: "h",
  fallback: false,
});

describe("show phases", () => {
  const intro: Show = { phase: "intro", revealed: false };

  test("waits while the battle runs, then opens with the intro once it is done", () => {
    expect(nextShow(START, { type: "update", battle: null })).toBe(START);
    const live = running as unknown as BattleRecord;
    expect(nextShow(START, { type: "update", battle: live })).toBe(START);
    expect(nextShow(START, { type: "update", battle })).toEqual(intro);
  });

  test("no intro lines: straight to the fight", () => {
    const noIntro = {
      ...battle,
      scripts: battle.scripts.filter((s) => s.kind !== "intro"),
    };
    expect(nextShow(START, { type: "update", battle: noIntro }).phase).toBe(
      "fight",
    );
  });

  test("done without a result never starts the show", () => {
    const empty = { ...battle, result: null };
    expect(nextShow(START, { type: "update", battle: empty })).toBe(START);
  });

  test("intro, fight, verdict; a later update never restarts the show", () => {
    const fight = nextShow(intro, { type: "intro-done" });
    expect(fight).toEqual({ phase: "fight", revealed: false });
    expect(nextShow(fight, { type: "update", battle })).toBe(fight);
    const verdict = nextShow(fight, { type: "fight-done" });
    expect(verdict).toEqual({ phase: "verdict", revealed: true });
  });

  test("skip jumps straight to the verdict from any phase", () => {
    for (const phase of ["waiting", "intro", "fight"] as const) {
      expect(nextShow({ phase, revealed: false }, { type: "skip" })).toEqual({
        phase: "verdict",
        revealed: true,
      });
    }
  });

  test("replay goes back to the fight and keeps the verdict revealed", () => {
    const verdict: Show = { phase: "verdict", revealed: true };
    expect(nextShow(verdict, { type: "replay" })).toEqual({
      phase: "fight",
      revealed: true,
    });
  });

  test("out-of-place actions change nothing", () => {
    expect(nextShow(START, { type: "intro-done" })).toBe(START);
    expect(nextShow(intro, { type: "fight-done" })).toBe(intro);
    expect(nextShow(intro, { type: "replay" })).toBe(intro);
  });

  test("Skip to verdict is offered once the result exists, until the verdict is up", () => {
    const simulated = { ...battle, status: "running" as const };
    expect(canSkip(START, null)).toBe(false);
    expect(canSkip(START, running as unknown as BattleRecord)).toBe(false);
    expect(canSkip(START, simulated)).toBe(true);
    expect(canSkip({ phase: "fight", revealed: false }, battle)).toBe(true);
    expect(canSkip({ phase: "verdict", revealed: true }, battle)).toBe(false);
  });
});

describe("caption sync", () => {
  test("fixture: captions change only on events that have lines (ScriptLine.at_event)", () => {
    const placed = placeLines(pbp, eventCount);
    const shown = result.representative_log.map((_, i) =>
      captionsAt(placed, i).map((l) => l.text),
    );
    expect(captionsAt(placed, -1)).toEqual([]);
    for (let i = 0; i < eventCount; i += 1) {
      const latest = Math.max(
        ...pbp.filter((l) => l.at_event! <= i).map((l) => l.at_event!),
      );
      expect(shown[i]).toEqual(
        pbp.filter((l) => l.at_event === latest).map((l) => l.text),
      );
    }
  });

  test("lines on the same event show together, in script order", () => {
    const placed = placeLines([line("a", 2), line("b", 2), line("c", 4)], 6);
    expect(captionsAt(placed, 1)).toEqual([]);
    expect(captionsAt(placed, 3).map((l) => l.text)).toEqual(["a", "b"]);
    expect(captionsAt(placed, 5).map((l) => l.text)).toEqual(["c"]);
  });

  test("a line with no at_event follows the line before it; the first opens the fight", () => {
    const placed = placeLines(
      [line("open", null), line("x", 3), line("y", null)],
      5,
    );
    expect(placed.map((p) => p.at)).toEqual([0, 3, 3]);
  });

  test("at_event outside the log is clamped so the line still shows", () => {
    const placed = placeLines([line("early", -2), line("late", 99)], 4);
    expect(placed.map((p) => p.at)).toEqual([0, 3]);
    expect(placeLines([line("x", 0)], 0)).toEqual([]);
  });

  test("lines out of order: the latest reached event wins", () => {
    const placed = placeLines([line("five", 5), line("two", 2)], 8);
    expect(captionsAt(placed, 3).map((l) => l.text)).toEqual(["two"]);
    expect(captionsAt(placed, 6).map((l) => l.text)).toEqual(["five"]);
  });

  test("intro lines stay up long enough to read, within limits", () => {
    expect(lineMs("Hi")).toBe(LINE_MS.min);
    expect(lineMs("x".repeat(1000))).toBe(LINE_MS.max);
    expect(lineMs("x".repeat(80))).toBe(80 * LINE_MS.perChar);
  });
});

describe("audio", () => {
  test("fixture: the music file and the single narration file", () => {
    expect(audioPlan(battle.assets)).toEqual({
      music: "/media/music/retro-broadcast.mp3",
      narration: "/media/audio/b-7f3k2q-narration.mp3",
    });
  });

  test("no audio assets: captions only, silent", () => {
    expect(audioPlan([asset("sprite", "/media/s.png")])).toEqual({
      music: null,
      narration: null,
    });
  });

  test("several narration files can't be told apart, so none plays", () => {
    const plan = audioPlan([
      asset("narration_audio", "/media/a.mp3"),
      asset("narration_audio", "/media/b.mp3"),
      asset("music", "/media/m.mp3"),
    ]);
    expect(plan).toEqual({ music: "/media/m.mp3", narration: null });
  });

  test("only files under /media are ever played", () => {
    const plan = audioPlan([
      asset("narration_audio", "https://elsewhere.example/a.mp3"),
      asset("music", "/api/m.mp3"),
    ]);
    expect(plan).toEqual({ music: null, narration: null });
  });
});

describe("notes and verdict", () => {
  test('"some effects unavailable" names every fallback stage, and only then', () => {
    expect(unavailableNote(battle.stages)).toBe(
      "Some effects unavailable: music.",
    );
    const fine = battle.stages.map((s) => ({ ...s, status: "done" as const }));
    expect(unavailableNote(fine)).toBeNull();
    const two = fine.map((s) =>
      s.stage === "audio" || s.stage === "images"
        ? { ...s, status: "fallback" as const }
        : s,
    );
    expect(unavailableNote(two)).toBe(
      "Some effects unavailable: announcer voice, pictures.",
    );
  });

  test("names: the display name for one fighter, the count for a group", () => {
    const sheets = battle.stat_sheets as StatSheet[];
    expect(sideNames(battle.matchup, sheets)).toEqual([
      sheets[0].display_name,
      "6 gray wolves",
    ]);
  });

  test("the reveal names the winner with odds from the result", () => {
    const v = verdictReveal(result, ["Grizzly bear", "6 gray wolves"]);
    expect(v.headline).toBe("Winner: 6 gray wolves!");
    expect(v.odds).toBe(
      "Win chance 55% - range 52-58%, over 1,000 simulated fights.",
    );
    expect(v.why).toBe(result.deciding_factor_explainer);
  });

  test("draw and no contest have no winner's odds", () => {
    const names = ["a", "b"];
    expect(verdictReveal({ ...result, outcome: "draw" }, names)).toMatchObject({
      headline: "It's a draw!",
      odds: null,
    });
    expect(
      verdictReveal({ ...result, outcome: "no_contest" }, names).headline,
    ).toBe("No contest!");
  });
});
