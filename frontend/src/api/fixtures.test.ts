// Fixtures mode must answer exactly like the backend's contract. Every reply is checked against
// the generated OpenAPI schema (openapi.json, the same file schema.d.ts is made from), so a
// contract change that isn't mirrored in the fixtures fails here instead of hiding behind a cast.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import openapi from "./openapi.json";
import battleCreated from "../fixtures/battle-created.json";
import fighterMatch from "../fixtures/fighter-match.json";
import showcaseBattle from "../fixtures/showcase-battle.json";
import { ApiError } from "./client.ts";
import * as fake from "./fixtures.ts";

// The parts of JSON Schema the generated contract uses.
type Schema = {
  $ref?: string;
  type?: string;
  enum?: unknown[];
  anyOf?: Schema[];
  properties?: Record<string, Schema>;
  required?: string[];
  additionalProperties?: boolean | Schema;
  propertyNames?: Schema;
  items?: Schema;
  prefixItems?: Schema[];
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  maxItems?: number;
};
const schemas = openapi.components.schemas as unknown as Record<string, Schema>;

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

// Whether a value has one JSON Schema type.
function hasType(value: unknown, type: string): boolean {
  if (type === "integer") return Number.isInteger(value);
  if (type === "null") return value === null;
  if (type === "array") return Array.isArray(value);
  if (type === "object") return isObject(value);
  return typeof value === type;
}

// Every way `value` breaks `schema`, as "path: problem" lines; empty when it fits.
function problems(value: unknown, schema: Schema, path = "$"): string[] {
  if (schema.$ref)
    return problems(value, schemas[schema.$ref.split("/").pop()!], path);
  if (schema.anyOf)
    return schema.anyOf.some((s) => problems(value, s, path).length === 0)
      ? []
      : [`${path}: matches none of its allowed shapes`];
  if (schema.enum && !schema.enum.includes(value))
    return [`${path}: ${JSON.stringify(value)} is not an allowed value`];
  if (schema.type && !hasType(value, schema.type))
    return [`${path}: expected ${schema.type}`];
  const out: string[] = [];
  const bound = (n: number, min?: number, max?: number, what = "") => {
    if ((min !== undefined && n < min) || (max !== undefined && n > max))
      out.push(`${path}: ${what}${n} is out of range`);
  };
  if (typeof value === "number") bound(value, schema.minimum, schema.maximum);
  if (typeof value === "string")
    bound(value.length, schema.minLength, schema.maxLength, "length ");
  if (Array.isArray(value)) {
    bound(value.length, schema.minItems, schema.maxItems, "item count ");
    const fixed = schema.prefixItems ?? [];
    value.forEach((item, i) => {
      const each = fixed[i] ?? schema.items;
      if (each) out.push(...problems(item, each, `${path}[${i}]`));
    });
  }
  if (isObject(value)) {
    const props = schema.properties ?? {};
    for (const key of schema.required ?? [])
      if (!(key in value)) out.push(`${path}.${key}: missing`);
    for (const [key, item] of Object.entries(value)) {
      const at = `${path}.${key}`;
      if (schema.propertyNames)
        out.push(...problems(key, schema.propertyNames, `${at} (name)`));
      const extra = schema.additionalProperties;
      if (props[key]) out.push(...problems(item, props[key], at));
      else if (extra === false) out.push(`${at}: not in the contract`);
      else if (isObject(extra)) out.push(...problems(item, extra, at));
    }
  }
  return out;
}

// Problems with a reply that should be one schema type, e.g. "StatSheet", or a list ("StatSheet[]").
const check = (value: unknown, name: string) =>
  problems(
    value,
    name.endsWith("[]")
      ? { type: "array", items: { $ref: name.slice(0, -2) } }
      : { $ref: name },
  );

beforeEach(() => {
  vi.useFakeTimers();
  fake.reset();
});

afterEach(() => {
  vi.useRealTimers();
});

// Let the pretend network delay pass and return the reply.
async function answer<T>(pending: Promise<T>): Promise<T> {
  await vi.advanceTimersByTimeAsync(300);
  return pending;
}

test("the schema check catches drift", () => {
  expect(check({ battle_id: "b1" }, "BattleCreated")).toEqual([]);
  expect(check({}, "BattleCreated")).toEqual(["$.battle_id: missing"]);
  expect(check({ battle_id: 7 }, "BattleCreated")).toEqual([
    "$.battle_id: expected string",
  ]);
  expect(check({ battle_id: "b1", extra: 1 }, "BattleCreated")).toEqual([
    "$.extra: not in the contract",
  ]);
  expect(check({ stage: "nap", status: "done" }, "StageStatus")).toEqual([
    '$.stage: "nap" is not an allowed value',
  ]);
  expect(check([{ fighter_id: "x" }], "FighterMatch[]")).toContain(
    "$[0].display_name: missing",
  );
});

describe("every fixtures-mode reply matches the contract", () => {
  test("intake, new battle, showcase, search and fighter sheets", async () => {
    expect(check(await answer(fake.intake()), "IntakeResult")).toEqual([]);
    expect(check(await answer(fake.createBattle()), "BattleCreated")).toEqual(
      [],
    );
    expect(check(await answer(fake.showcase()), "ShowcaseBattle[]")).toEqual(
      [],
    );
    const matches = await answer(fake.searchFighters(""));
    expect(matches.length).toBeGreaterThan(1);
    expect(check(matches, "FighterMatch[]")).toEqual([]);
    for (const m of matches)
      expect(
        check(await answer(fake.getFighter(m.fighter_id)), "StatSheet"),
      ).toEqual([]);
  });

  test.each([0, fake.BATTLE_MS / 2, fake.BATTLE_MS])(
    "a battle record %i ms in",
    (ms) => {
      expect(check(fake.battleAt("demo", ms), "BattleRecord")).toEqual([]);
    },
  );

  test.each([...fake.CROWD_BATTLES.keys()])(
    "the %s crowd replay",
    async (id) => {
      expect(check(await fake.crowdBattle(id), "BattleRecord")).toEqual([]);
    },
  );
});

describe("fixtures mode uses the synced fixture files", () => {
  test("new battles, showcase rows and fighter matches", async () => {
    const created = await answer(fake.createBattle());
    expect(Object.keys(created)).toEqual(Object.keys(battleCreated));
    expect(await answer(fake.showcase())).toContainEqual(showcaseBattle);
    expect(await answer(fake.searchFighters("grizzly"))).toEqual([
      fighterMatch,
    ]);
  });

  test("an unknown fighter rejects with ApiError(404), like live mode", async () => {
    const error = await fake.getFighter("nope").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
  });
});
