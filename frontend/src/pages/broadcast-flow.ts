// The Battle page's broadcast logic (D07): which part of the show is on, which captions show,
// which audio can play, and the notes for degraded modes. Pure functions, no React.
import type {
  Asset,
  BattleRecord,
  Matchup,
  Script,
  ScriptLine,
  SimulationResult,
  StageStatus,
  StatSheet,
} from "../api/client.ts";
import {
  explainerOf,
  sideName,
  winRange,
  winnerOf,
} from "../components/Verdict.tsx";

// The parts of the show, in order. "waiting" covers research and simulation (the ticker).
export type Phase = "waiting" | "intro" | "fight" | "verdict";

// Where the show is, and whether the verdict has been shown once (it stays up after a replay).
export interface Show {
  phase: Phase;
  revealed: boolean;
}

export type ShowAction =
  | { type: "update"; battle: BattleRecord | null } // a fresh battle record arrived
  | { type: "intro-done" } // the last intro line finished, or the viewer started the fight
  | { type: "fight-done" } // the replay reached its last event
  | { type: "skip" } // "Skip to verdict"
  | { type: "replay" }; // the viewer replays the fight

export const START: Show = { phase: "waiting", revealed: false };

// The lines of one part of the script (none when that script is missing).
export const linesOf = (
  scripts: readonly Script[],
  kind: Script["kind"],
): ScriptLine[] => scripts.find((s) => s.kind === kind)?.lines ?? [];

// Move the show along. The broadcast starts once the battle is done (all media in), so pictures
// and sound never pop in halfway; with no intro lines it goes straight to the fight.
export function nextShow(show: Show, action: ShowAction): Show {
  switch (action.type) {
    case "update": {
      const b = action.battle;
      if (show.phase !== "waiting" || b?.status !== "done" || !b.result)
        return show;
      const intro = linesOf(b.scripts, "intro").length > 0;
      return { ...show, phase: intro ? "intro" : "fight" };
    }
    case "intro-done":
      return show.phase === "intro" ? { ...show, phase: "fight" } : show;
    case "fight-done":
      return show.phase === "fight"
        ? { phase: "verdict", revealed: true }
        : show;
    case "skip":
      return { phase: "verdict", revealed: true };
    case "replay":
      return show.phase === "verdict" ? { ...show, phase: "fight" } : show;
  }
}

// "Skip to verdict" is offered as soon as the result exists, until the verdict is up.
export const canSkip = (show: Show, battle: BattleRecord | null) =>
  Boolean(battle?.result) && show.phase !== "verdict";

// A play-by-play line and the replay event it belongs to.
export interface PlacedLine {
  line: ScriptLine;
  at: number;
}

// Put play-by-play lines on the replay. at_event is clamped into the log; a line with no
// at_event follows the line before it (the first one opens the fight).
export function placeLines(
  lines: readonly ScriptLine[],
  eventCount: number,
): PlacedLine[] {
  if (eventCount <= 0) return [];
  let previous = 0;
  return lines.map((line) => {
    const at =
      line.at_event === null
        ? previous
        : Math.min(eventCount - 1, Math.max(0, line.at_event));
    previous = at;
    return { line, at };
  });
}

// The captions once the replay has reached event `index` (-1 before it starts): the lines of the
// latest reached event that has any, in script order. Captions only change on events with lines.
export function captionsAt(
  placed: readonly PlacedLine[],
  index: number,
): ScriptLine[] {
  const reached = placed.filter((p) => p.at <= index);
  if (reached.length === 0) return [];
  const latest = Math.max(...reached.map((p) => p.at));
  return reached.filter((p) => p.at === latest).map((p) => p.line);
}

// How long an intro or outro line stays up: long enough to read, never too long.
export const LINE_MS = { perChar: 60, min: 2500, max: 7000 };
export const lineMs = (text: string) =>
  Math.min(LINE_MS.max, Math.max(LINE_MS.min, text.length * LINE_MS.perChar));

// Display names for the speakers.
export const SPEAKERS: Record<ScriptLine["speaker"], string> = {
  announcer: "Announcer",
  color_commentator: "Color commentator",
};

// What the audio bar can play. Only files under /media are used (the front end calls nothing else).
// Music is unambiguous: the battle's music file. Narration plays only when there is exactly one
// narration file: the Asset contract does not say which script a file belongs to, so with several
// (one per script) the show falls back to captions only rather than guess.
export interface AudioPlan {
  music: string | null;
  narration: string | null;
}

export function audioPlan(assets: readonly Asset[]): AudioPlan {
  const ours = assets.filter((a) => a.url.startsWith("/media/"));
  const narration = ours.filter((a) => a.kind === "narration_audio");
  return {
    music: ours.find((a) => a.kind === "music")?.url ?? null,
    narration: narration.length === 1 ? narration[0].url : null,
  };
}

// Plain names for the stages a viewer might notice missing.
const STAGE_NAMES: Record<StageStatus["stage"], string> = {
  intake: "matchup check",
  research: "research",
  simulate: "simulation",
  summary: "summary",
  challenger: "next challenger",
  script: "announcer script",
  audio: "announcer voice",
  music: "music",
  images: "pictures",
};

// "Some effects unavailable: music." when any stage used a stand-in, otherwise null.
export function unavailableNote(stages: readonly StageStatus[]) {
  const names = stages
    .filter((s) => s.status === "fallback")
    .map((s) => STAGE_NAMES[s.stage]);
  return names.length > 0
    ? `Some effects unavailable: ${names.join(", ")}.`
    : null;
}

// Both sides' names for the title card and the verdict, e.g. ["Grizzly bear", "6 gray wolves"].
export const sideNames = (
  matchup: Pick<Matchup, "fighters">,
  sheets: readonly StatSheet[],
) =>
  ([0, 1] as const).map((side) => {
    const fighter = matchup.fighters[side];
    return fighter ? sideName(fighter, sheets[side]) : "?";
  });

// The verdict reveal: headline, the winner's odds, and why. Every number comes from the result.
export function verdictReveal(result: SimulationResult, names: string[]) {
  const winner = winnerOf(result);
  const runs = result.runs.toLocaleString("en-US");
  return {
    headline:
      winner !== null
        ? `Winner: ${names[winner]}!`
        : result.outcome === "draw"
          ? "It's a draw!"
          : "No contest!",
    odds:
      winner !== null
        ? `Win chance ${winRange(result, winner)}, over ${runs} simulated fights.`
        : null,
    why: explainerOf(result),
  };
}
