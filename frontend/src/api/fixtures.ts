// A pretend backend for VITE_USE_FIXTURES=true: answers from src/fixtures/ with realistic delays,
// and plays a battle through every stage in about BATTLE_MS so the UI can be built without the backend.
import type { components } from "./schema";
import battleDone from "../fixtures/battle-record-done.json";
import intakeResult from "../fixtures/intake-result.json";
import grizzly from "../fixtures/stat-sheet.json";
import wolf from "../fixtures/stat-sheet-gray-wolf.json";
import thousandVsOne from "../game/fixtures/thousand-vs-one.json";
import twoHundredVsFive from "../game/fixtures/two-hundred-vs-five.json";

type BattleRecord = components["schemas"]["BattleRecord"];
type FighterRequest = components["schemas"]["FighterRequest"];
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

// Start a new pretend battle; its clock begins now.
export function createBattle() {
  const battle_id = `fixture-${started.size + 1}`;
  started.set(battle_id, Date.now());
  return later({ battle_id });
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

// Reserved ids that open a big-crowd replay at once, to check the frame rate (see
// src/game/fixtures/README.md). Only fixtures mode knows them; the real API treats them like any id.
export const CROWD_BATTLES = new Map<string, SimulationResult>([
  ["thousand-vs-one", thousandVsOne as unknown as SimulationResult],
  ["two-hundred-vs-five", twoHundredVsFive as unknown as SimulationResult],
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
export function crowdBattle(id: string): BattleRecord | null {
  const result = CROWD_BATTLES.get(id);
  if (!result) return null;
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
  if (crowd) return later(crowd);
  if (!started.has(id)) started.set(id, Date.now());
  return later(battleAt(id, Date.now() - started.get(id)!));
}

// The five planned showcase battles (PRODUCT_SPEC §9) until Gunnar's G08 saves the real ones.
// Every id plays the same pretend battle in fixtures mode.
export const SHOWCASE: { battle_id: string; title: string }[] = [
  {
    battle_id: "showcase-horses-duck",
    title: "100 duck-sized horses vs 1 horse-sized duck",
  },
  {
    battle_id: done.battle_id,
    title: "Grizzly bear vs 6 gray wolves (forest)",
  },
  { battle_id: "showcase-badger-cobra", title: "Honey badger vs king cobra" },
  {
    battle_id: "showcase-legionary-gorilla",
    title: "Roman legionary vs gorilla",
  },
  {
    battle_id: "showcase-dragon-tank",
    title: "A dragon vs a main battle tank (open field)",
  },
];

export const showcase = () => later(SHOWCASE);

export const searchFighters = (q: string) =>
  later(
    sheets
      .filter((s) => s.display_name.toLowerCase().includes(q.toLowerCase()))
      .map((s) => ({
        fighter_id: s.fighter_id,
        display_name: s.display_name,
        cached: true,
      })),
  );

export function getFighter(fighterId: string) {
  const sheet = sheets.find((s) => s.fighter_id === fighterId);
  return sheet ? later(sheet) : Promise.reject(new Error("HTTP 404"));
}

// Forget every pretend battle (tests use this between runs).
export const reset = () => started.clear();
