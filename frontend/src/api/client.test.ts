import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import clientSource from "./client.ts?raw";
import * as client from "./client.ts";
import { BATTLE_MS, reset } from "./fixtures.ts";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("fixtures mode (no backend)", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_USE_FIXTURES", "true");
    vi.useFakeTimers();
    reset();
  });

  // Read the battle after a given amount of pretend time, letting the fake network delay pass.
  async function battleAfter(id: string, ms: number) {
    await vi.advanceTimersByTimeAsync(ms);
    const pending = client.getBattle(id);
    await vi.advanceTimersByTimeAsync(300);
    return pending;
  }

  test("a battle moves through every stage in about 10 seconds", async () => {
    vi.stubGlobal("fetch", vi.fn());
    const start = await battleAfter("demo", 0);
    expect(start.status).toBe("running");
    expect(start.stages[0].status).toBe("running");
    expect(start.result).toBeNull();

    const middle = await battleAfter("demo", 4_000);
    expect(middle.status).toBe("running");
    expect(middle.stat_sheets.length).toBeGreaterThan(0);
    expect(middle.stages.some((s) => s.status === "pending")).toBe(true);

    const almost = await battleAfter("demo", BATTLE_MS - 4_000 - 1_200);
    expect(almost.status).toBe("running");

    const end = await battleAfter("demo", 1_200);
    expect(end.status).toBe("done");
    expect(
      end.stages.every((s) => s.status === "done" || s.status === "fallback"),
    ).toBe(true);
    expect(end.result).not.toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  test("intake and fighter search answer from fixtures", async () => {
    const intake = client.postIntake("a bear vs wolves");
    const fighters = client.searchFighters("wolf");
    await vi.advanceTimersByTimeAsync(300);
    expect((await intake).status).toBeDefined();
    expect(
      (await fighters).map((f) => f.display_name.toLowerCase()).join(),
    ).toContain("wolf");
  });
});

test("live mode calls our own /api routes", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(Response.json({ battle_id: "b1" }));
  vi.stubGlobal("fetch", fetchMock);
  await client.getBattle("b1");
  expect(fetchMock).toHaveBeenCalledWith("/api/battles/b1", undefined);
  expect(client.battleEventsUrl("b1")).toBe("/api/battles/b1/events");
});

test("client.ts takes its types only from the generated schema", () => {
  const typeImports = [
    ...clientSource.matchAll(/^import type .* from "(.+)";$/gm),
  ].map((m) => m[1]);
  expect(typeImports).toEqual(["./schema"]);
  expect(clientSource).not.toMatch(/\binterface\b/);
  // Only the documented contract-gap replies may be described by hand.
  const handWritten = [
    ...clientSource.matchAll(/^export type (\w+) = \{/gm),
  ].map((m) => m[1]);
  expect(handWritten).toEqual([
    "BattleCreated",
    "ShowcaseBattle",
    "FighterMatch",
  ]);
});
