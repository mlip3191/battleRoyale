// Typed calls to our own backend (ARCHITECTURE §6). Types come only from the generated schema.
// With VITE_USE_FIXTURES=true every call is answered from src/fixtures/ instead (see fixtures.ts).
import type { components } from "./schema";
import * as fake from "./fixtures.ts";

export type BattleRecord = components["schemas"]["BattleRecord"];
export type IntakeResult = components["schemas"]["IntakeResult"];
export type Matchup = components["schemas"]["Matchup"];
export type StageStatus = components["schemas"]["StageStatus"];
export type StatSheet = components["schemas"]["StatSheet"];
export type BattleCreated = components["schemas"]["BattleCreated"];
export type ShowcaseBattle = components["schemas"]["ShowcaseBattle"];
export type FighterMatch = components["schemas"]["FighterMatch"];
export type SimulationResult = components["schemas"]["SimulationResult"];
export type FightEvent = components["schemas"]["FightEvent"];
export type Asset = components["schemas"]["Asset"];
export type FighterRequest = components["schemas"]["FighterRequest"];

// An HTTP error from our backend; `status` lets callers tell "not found" from a passing hiccup.
export class ApiError extends Error {
  status: number;
  constructor(status: number) {
    super(`HTTP ${status}`);
    this.status = status;
  }
}

// Whether to answer from fixtures instead of the backend (read on each call so tests can switch it).
export const fixturesMode = () => import.meta.env.VITE_USE_FIXTURES === "true";

const base = () => import.meta.env.VITE_API_BASE ?? "";

// Send one request to our backend and parse the JSON reply, throwing on HTTP errors.
async function call<T>(
  path: string,
  init?: { method: string; body: unknown },
): Promise<T> {
  const response = await fetch(
    `${base()}${path}`,
    init && {
      method: init.method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(init.body),
    },
  );
  if (!response.ok) throw new ApiError(response.status);
  return (await response.json()) as T;
}

// Parse a typed matchup request (step 1).
export const postIntake = (text: string) =>
  fixturesMode()
    ? fake.intake()
    : call<IntakeResult>("/api/intake", { method: "POST", body: { text } });

// Answer the clarifying question for a pending intake.
export const answerIntake = (pendingId: string, answer: string) =>
  fixturesMode()
    ? fake.intake()
    : call<IntakeResult>(
        `/api/intake/${encodeURIComponent(pendingId)}/answer`,
        {
          method: "POST",
          body: { answer },
        },
      );

// Start a battle; the backend replies right away with its id.
export const createBattle = (matchup: Matchup) =>
  fixturesMode()
    ? fake.createBattle()
    : call<BattleCreated>("/api/battles", { method: "POST", body: matchup });

// Fetch a battle (partial while it is still running).
export const getBattle = (id: string) =>
  fixturesMode()
    ? fake.getBattle(id)
    : call<BattleRecord>(`/api/battles/${encodeURIComponent(id)}`);

// List the five saved showcase battles.
export const listShowcase = () =>
  fixturesMode()
    ? fake.showcase()
    : call<ShowcaseBattle[]>("/api/battles?showcase=true");

// Search known fighters by name.
export const searchFighters = (q: string) =>
  fixturesMode()
    ? fake.searchFighters(q)
    : call<FighterMatch[]>(`/api/fighters?q=${encodeURIComponent(q)}`);

// Fetch one fighter's stat sheet.
export const getFighter = (fighterId: string) =>
  fixturesMode()
    ? fake.getFighter(fighterId)
    : call<StatSheet>(`/api/fighters/${encodeURIComponent(fighterId)}`);

// URL of a battle's live stage updates (Server-Sent Events).
export const battleEventsUrl = (id: string) =>
  `${base()}/api/battles/${encodeURIComponent(id)}/events`;

// URL of a generated media file.
export const mediaUrl = (assetId: string) =>
  `${base()}/media/${encodeURIComponent(assetId)}`;
