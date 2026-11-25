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
import type { VoiceCue } from "../components/AudioBar.tsx";
import {
  explainerOf,
  sideName,
  winRange,
  isTooCloseToCall,
  winnerOf,
} from "../components/Verdict.tsx";

// The parts of the show, in order. "waiting" covers research and simulation (the ticker).
// "standby" is the intro's card held after its last line while the fight's voice is still being
// recorded (#592).
export type Phase = "waiting" | "intro" | "standby" | "fight" | "verdict";

// Where the show is, and whether the verdict has been shown once (it stays up after a replay).
export interface Show {
  phase: Phase;
  revealed: boolean;
}

export type ShowAction =
  | { type: "update"; battle: BattleRecord | null } // a fresh battle record arrived
  // The last intro line finished, or the viewer started the fight; `battle` is the latest record.
  | { type: "intro-done"; battle?: BattleRecord | null }
  | { type: "voice-late" } // the fight waited FIGHT_VOICE_WAIT_MS for its voice (#592)
  | { type: "fight-done" } // the replay reached its last event
  | { type: "skip" } // "Skip to verdict"
  | { type: "replay" }; // the viewer replays the fight

export const START: Show = { phase: "waiting", revealed: false };

// The lines of one part of the script (none when that script is missing).
export const linesOf = (
  scripts: readonly Script[],
  kind: Script["kind"],
): ScriptLine[] => scripts.find((s) => s.kind === kind)?.lines ?? [];

// The longest the fight waits for its announcer after the intro; then it starts captions-only.
export const FIGHT_VOICE_WAIT_MS = 45_000;

// Whether a stage has finished, for good or with a stand-in.
const settled = (b: BattleRecord, stage: StageStatus["stage"]) =>
  b.stages.some(
    (s) =>
      s.stage === stage && (s.status === "done" || s.status === "fallback"),
  );

// Whether this part of the show's announcer file is still being recorded (#592): the battle runs,
// the audio stage hasn't settled, the part has lines, and its file isn't on the record yet.
const voiceComing = (b: BattleRecord, phase: "intro" | "fight") =>
  b.status === "running" &&
  !settled(b, "audio") &&
  linesOf(b.scripts, SCRIPT_OF[phase]!).length > 0 &&
  audioPlan(b.assets, phase).narration === null;

// Whether the show can start. A finished battle can. While the rest of the announcer is recorded,
// it can once the verdict, the scripts and the pictures are in (so pictures never pop in halfway)
// and the intro's voice is in or will not come (#592). Music is cut (#538), so it is not awaited.
const readyToStart = (b: BattleRecord) =>
  Boolean(b.result) &&
  (b.status === "done" ||
    (settled(b, "images") && b.scripts.length > 0 && !voiceComing(b, "intro")));

// The fight starts, unless its voice is still being recorded: then the intro's card holds.
const toFight = (show: Show, b: BattleRecord | null | undefined): Show => ({
  ...show,
  phase: b && voiceComing(b, "fight") ? "standby" : "fight",
});

// Move the show along. The broadcast starts once it is safe to (readyToStart); with no intro
// lines it goes straight to the fight. A held fight starts once its voice is in, the audio stage
// settles, or it has waited FIGHT_VOICE_WAIT_MS (#592).
export function nextShow(show: Show, action: ShowAction): Show {
  switch (action.type) {
    case "update": {
      const b = action.battle;
      if (show.phase === "standby")
        return b && !voiceComing(b, "fight")
          ? { ...show, phase: "fight" }
          : show;
      if (show.phase !== "waiting" || !b || !readyToStart(b)) return show;
      const intro = linesOf(b.scripts, "intro").length > 0;
      return intro ? { ...show, phase: "intro" } : toFight(show, b);
    }
    case "intro-done":
      return show.phase === "intro" ? toFight(show, action.battle) : show;
    case "voice-late":
      return show.phase === "standby" ? { ...show, phase: "fight" } : show;
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

// The announcer can't talk over a 5x or 10x replay, so it waits until the fight slows (#577).
export const tooFastToTalk = (speed: number) => speed > 2;

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

// What the audio bar can play in each part of the show. Only files under /media are used (the
// front end calls nothing else). Music is unambiguous: the battle's music file, all show long.
// Narration files say which script they read (script_kind): the intro plays the intro's file, the
// fight the play-by-play's, the verdict the outro's, and a part with no file of its own is silent.
// Older records have one narration file with no script_kind: it plays in every part, as before.
// Several untagged files can't be told apart, so the show falls back to captions only.
export interface AudioPlan {
  music: string | null;
  narration: string | null;
  lineTimes: Asset["line_times_s"]; // where each line sits in the narration file, if known (#576)
}

// The script each part of the show reads aloud (nothing while the ticker runs). The held intro
// card keeps the intro's file, so the "Start the fight" click's unlock carries into the fight.
const SCRIPT_OF: Record<Phase, Script["kind"] | null> = {
  waiting: null,
  intro: "intro",
  standby: "intro",
  fight: "play_by_play",
  verdict: "outro",
};

export function audioPlan(assets: readonly Asset[], phase: Phase): AudioPlan {
  const ours = assets.filter((a) => a.url.startsWith("/media/"));
  const narration = ours.filter((a) => a.kind === "narration_audio");
  const tagged = narration.filter((a) => a.script_kind); // older records leave it out
  const untagged = narration.length === 1 ? narration[0] : null;
  const voice =
    tagged.length > 0
      ? (tagged.find((a) => a.script_kind === SCRIPT_OF[phase]) ?? null)
      : untagged;
  return {
    music: ours.find((a) => a.kind === "music")?.url ?? null,
    narration: voice?.url ?? null,
    lineTimes: voice?.line_times_s ?? null,
  };
}

// The stretch of the announcer's file for the replay's current moment (#576): the lines of the
// latest reached event that has any (the lines captionsAt shows), from the first one's start to
// the last one's end. Null before the first line, or when none of them was spoken.
export function voiceCue(
  placed: readonly PlacedLine[],
  index: number,
  lineTimes: NonNullable<AudioPlan["lineTimes"]>,
): VoiceCue | null {
  const reached = placed
    .map((p, line) => ({ at: p.at, line }))
    .filter((p) => p.at <= index);
  if (reached.length === 0) return null;
  const at = Math.max(...reached.map((p) => p.at));
  const times = reached
    .filter((p) => p.at === at)
    .map((p) => lineTimes[p.line])
    .filter((t): t is [number, number] => Array.isArray(t));
  if (times.length === 0) return null;
  return {
    at,
    start: Math.min(...times.map(([start]) => start)),
    end: Math.max(...times.map(([, end]) => end)),
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

// Said when the script stage fell back: the show still has full commentary, from the template.
export const TEMPLATE_SCRIPT_NOTE = "Some commentary used the template script.";

// Music is cut (no music service), so its fallback is the normal case, not news (#538).
export const shownStage = (s: StageStatus) =>
  !(s.stage === "music" && s.status === "fallback");

// "Some effects unavailable: pictures." when any stage used a stand-in, otherwise null. A template
// script is not missing, so it gets its own sentence (on mocks the play-by-play always is one),
// and so does a research note.
export function unavailableNote(stages: readonly StageStatus[]) {
  const fellBack = stages.filter(
    (s) => s.status === "fallback" && shownStage(s),
  );
  // Research falls back when a fighter isn't on our list; its note names the fighter on
  // estimates, which says more than "research unavailable" (#540).
  const research = fellBack.find((s) => s.stage === "research")?.detail ?? "";
  const names = fellBack
    .filter(
      (s) => s.stage !== "script" && !(s.stage === "research" && research),
    )
    .map((s) => STAGE_NAMES[s.stage]);
  const parts = [
    fellBack.some((s) => s.stage === "script") ? TEMPLATE_SCRIPT_NOTE : "",
    research,
    names.length > 0 ? `Some effects unavailable: ${names.join(", ")}.` : "",
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" ") : null;
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
        ? isTooCloseToCall(result)
          ? `Too close to call! Slight edge: ${names[winner]}`
          : `Winner: ${names[winner]}!`
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
