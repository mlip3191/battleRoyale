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

describe("live mode", () => {
  // A fetch stand-in that answers every call with the same JSON and status.
  const answer = (body: unknown, status = 200) => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(Response.json(body, { status })),
    );
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  };

  test("calls our own /api routes", async () => {
    const fetchMock = answer({ battle_id: "b1" });
    await client.getBattle("b1");
    expect(fetchMock).toHaveBeenCalledWith("/api/battles/b1", undefined);
    expect(client.battleEventsUrl("b1")).toBe("/api/battles/b1/events");
  });

  test("createBattle sends a JSON POST with the matchup", async () => {
    const fetchMock = answer({ battle_id: "b9" });
    const matchup = {
      fighters: [],
      terrain: "forest",
      raw_text: "x",
      assumptions: [],
    };
    const created = await client.createBattle(
      matchup as unknown as client.Matchup,
    );
    expect(created.battle_id).toBe("b9");
    expect(fetchMock).toHaveBeenCalledWith("/api/battles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(matchup),
    });
  });

  test("a non-OK reply throws an ApiError with its status", async () => {
    answer({ detail: "missing" }, 404);
    const error = await client.getBattle("nope").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(client.ApiError);
    expect((error as client.ApiError).status).toBe(404);
    expect((error as Error).message).toBe("HTTP 404");
  });

  test("ids and search text are URL-encoded", async () => {
    const fetchMock = answer([]);
    await client.searchFighters("a b/c");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/fighters?q=a%20b%2Fc",
      undefined,
    );
    expect(client.mediaUrl("x/y")).toBe("/media/x%2Fy");
  });

  test("VITE_API_BASE prefixes every backend address", async () => {
    vi.stubEnv("VITE_API_BASE", "http://localhost:9999");
    const fetchMock = answer({ battle_id: "b1" });
    await client.getBattle("b1");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:9999/api/battles/b1",
      undefined,
    );
    expect(client.mediaUrl("a1")).toBe("http://localhost:9999/media/a1");
  });
});

test("client.ts takes its types only from the generated schema", () => {
  const typeImports = [
    ...clientSource.matchAll(/^import type .* from "(.+)";$/gm),
  ].map((m) => m[1]);
  expect(typeImports).toEqual(["./schema"]);
  expect(clientSource).not.toMatch(/\binterface\b/);
  // Every exported type is an alias of a generated schema type, never a hand-written shape.
  expect(clientSource).not.toMatch(/^export type \w+ = \{/m);
});
