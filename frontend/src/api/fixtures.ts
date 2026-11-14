// A pretend backend for VITE_USE_FIXTURES=true: answers from src/fixtures/ with realistic delays,
// and plays a battle through every stage in about BATTLE_MS so the UI can be built without the backend.
import type { components } from "./schema";
import { ApiError } from "./api-error.ts";
import battleCreated from "../fixtures/battle-created.json";
import battleDone from "../fixtures/battle-record-done.json";
import fighterMatch from "../fixtures/fighter-match.json";
import intakeResult from "../fixtures/intake-result.json";
import showcaseBattle from "../fixtures/showcase-battle.json";
import grizzly from "../fixtures/stat-sheet.json";
import wolf from "../fixtures/stat-sheet-gray-wolf.json";

type BattleCreated = components["schemas"]["BattleCreated"];
type BattleRecord = components["schemas"]["BattleRecord"];
type FighterMatch = components["schemas"]["FighterMatch"];
type FighterRequest = components["schemas"]["FighterRequest"];
type ShowcaseBattle = components["schemas"]["ShowcaseBattle"];
type SimulationResult = components["schemas"]["SimulationResult"];
type StatSheet = components["schemas"]["StatSheet"];

export const BATTLE_MS = 10_000;
const DELAY_MS = 300;
const done = battleDone as unknown as BattleRecord;
const sheets = [grizzly, wolf] as unknown as StatSheet[];
const started = new Map<string, number>();

// Wait like a real network call would.
const later = <T>(value: T): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), DELAY_MS));

export const intake = () =>
  later(intakeResult as unknown as components["schemas"]["IntakeResult"]);

// Start a new pretend battle; its clock begins now. The reply is the synced battle-created.json
// with a fresh id, since each pretend battle keeps its own clock.
export function createBattle() {
  const battle_id = `fixture-${started.size + 1}`;
  started.set(battle_id, Date.now());
  return later<BattleCreated>({ ...battleCreated, battle_id });
}

// The battle as it looks right now: stages finish one by one, and each part appears when its stage is done.
// The real pipeline runs some stages in parallel (summary/challenger/script; audio/music/images),
// so no screen should assume stages finish in this exact order.
export function battleAt(id: string, elapsedMs: number): BattleRecord {
  const step = BATTLE_MS / done.stages.length;
  const stages = done.stages.map((s, i) =>
    elapsedMs >= (i + 1) * step
      ? s
      : {
          ...s,
          status:
            elapsedMs >= i * step ? ("running" as const) : ("pending" as const),
        },
  );
  const finished = (name: string) =>
    stages.some(
      (s) =>
        s.stage === name && s.status !== "pending" && s.status !== "running",
    );
  const all = stages.every(
    (s) => s.status !== "pending" && s.status !== "running",
  );
  return {
    ...done,
    battle_id: id,
    stages,
    status: all ? "done" : "running",
    stat_sheets: finished("research") ? done.stat_sheets : [],
    result: finished("simulate") ? done.result : null,
    fair_fight: finished("summary") ? done.fair_fight : null,
    challenger: finished("challenger") ? done.challenger : null,
    scripts: finished("script") ? done.scripts : [],
    assets: finished("images") ? done.assets : [],
  };
}

// Read a crowd log out of its lazily loaded JSON module.
const crowdLog = (file: Promise<{ default: unknown }>) =>
  file.then((module) => module.default as SimulationResult);

// Reserved ids that open a big-crowd replay at once, to check the frame rate (see
// src/game/fixtures/README.md). Only fixtures mode knows them; the real API treats them like any id.
// Each log loads only when its id is asked for, so the big files stay out of the main bundle (#215).
export const CROWD_BATTLES = new Map<string, () => Promise<SimulationResult>>([
  [
    "thousand-vs-one",
    () => crowdLog(import("../game/fixtures/thousand-vs-one.json")),
  ],
  [
    "two-hundred-vs-five",
    () => crowdLog(import("../game/fixtures/two-hundred-vs-five.json")),
  ],
]);

// A side's head count, read from its opening "approach" event in the log.
const headCount = (result: SimulationResult, side: number) =>
  result.representative_log.find(
    (e) => e.type === "approach" && e.side === side,
  )?.group_size ?? 1;

// One side of the stand-in matchup the crowd logs were made from.
const standIn = (entity: string, plural: string, count: number) =>
  ({
    entity,
    count,
    variant: null,
    size_reference: null,
    raw: count === 1 ? `a ${entity}` : `${count} ${plural}`,
  }) satisfies FighterRequest;

// A finished battle that replays a crowd log: stand-in ducks vs a stand-in lion, no sheets or scripts.
// Null at once for any other id; a reserved id loads its log first.
export function crowdBattle(id: string): Promise<BattleRecord> | null {
  const load = CROWD_BATTLES.get(id);
  return load ? load().then((result) => crowdRecord(id, result)) : null;
}

// The finished battle record built around one crowd log.
function crowdRecord(id: string, result: SimulationResult): BattleRecord {
  const fighters = [
    standIn("duck", "ducks", headCount(result, 0)),
    standIn("lion", "lions", headCount(result, 1)),
  ];
  return {
    ...done,
    battle_id: id,
    matchup: {
      fighters,
      terrain: "open_field",
      raw_text: `${fighters[0].raw} vs ${fighters[1].raw} in an open field`,
      assumptions: ["Stand-in fighters with round-number stats (no sources)"],
    },
    stat_sheets: [],
    result,
    fair_fight: null,
    challenger: null,
    scripts: [],
    assets: [],
    stages: done.stages.map((s) => ({ ...s, status: "done", detail: null })),
    status: "done",
  };
}

// Any id works; an id seen for the first time starts its battle clock now.
export function getBattle(id: string) {
  const crowd = crowdBattle(id);
  if (crowd) return crowd.then(later);
  if (!started.has(id)) started.set(id, Date.now());
  return later(battleAt(id, Date.now() - started.get(id)!));
}

// A planned showcase row, shaped like the synced showcase-battle.json.
const planned = (battle_id: string, title: string): ShowcaseBattle => ({
  ...showcaseBattle,
  battle_id,
  title,
});

// The five planned showcase battles (PRODUCT_SPEC §9) until Gunnar's G08 saves the real ones;
// the grizzly row is showcase-battle.json itself. Every id plays the same pretend battle.
export const SHOWCASE: ShowcaseBattle[] = [
  planned(
    "showcase-horses-duck",
    "100 duck-sized horses vs 1 horse-sized duck",
  ),
  showcaseBattle,
  planned("showcase-badger-cobra", "Honey badger vs king cobra"),
  planned("showcase-legionary-gorilla", "Roman legionary vs gorilla"),
  planned(
    "showcase-dragon-tank",
    "A dragon vs a main battle tank (open field)",
  ),
];

export const showcase = () => later(SHOWCASE);

// Known fighters whose name contains the search text, each shaped like the synced
// fighter-match.json (the grizzly match is that file exactly).
export const searchFighters = (q: string) =>
  later(
    sheets
      .filter((s) => s.display_name.toLowerCase().includes(q.toLowerCase()))
      .map((s): FighterMatch => ({
        ...fighterMatch,
        fighter_id: s.fighter_id,
        display_name: s.display_name,
      })),
  );

// One fighter's sheet, or a 404 ApiError just like the live backend.
export function getFighter(fighterId: string) {
  const sheet = sheets.find((s) => s.fighter_id === fighterId);
  return sheet ? later(sheet) : Promise.reject(new ApiError(404));
}

// Forget every pretend battle (tests use this between runs).
export const reset = () => started.clear();
