// The big-crowd replays (#162): reserved battle ids that open them in fixtures mode only, so anyone
// can check the frame rate with 1,000 fighters on stage (see src/game/fixtures/README.md).
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { CROWD_BATTLES } from "../api/fixtures.ts";
import { NOT_FOUND } from "../api/useBattle.ts";
import { games, type FakeScene } from "../game/fake-phaser.ts";
import { MAX_SPRITES_PER_SIDE } from "../game/layout.ts";
import Battle from "./Battle.tsx";

vi.mock(
  "phaser",
  async () => (await import("../game/fake-phaser.ts")).fakePhaser,
);

beforeEach(() => {
  games.length = 0;
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

// Open the battle page at /battle/<id>, the way the app's router does.
const open = (id: string) =>
  render(
    <MemoryRouter initialEntries={[`/battle/${id}`]}>
      <Routes>
        <Route path="/battle/:id" element={<Battle />} />
      </Routes>
    </MemoryRouter>,
  );

// Wait for the replay stage to start its (fake) Phaser game, then return the scene.
async function stageScene() {
  await waitFor(() => expect(games).toHaveLength(1));
  return games[0].config.scene[0] as FakeScene;
}

test("fixtures mode: /battle/thousand-vs-one plays 1,000 ducks vs 1 lion with the sprite cap and badge", async () => {
  vi.stubEnv("VITE_USE_FIXTURES", "true");
  open("thousand-vs-one");
  const scene = await stageScene();
  expect(
    screen.getByRole("img", { name: /1,000 ducks versus 1 lion/ }),
  ).toBeDefined();
  const ducks = scene.images.filter((i) => i.text === "placeholder-0");
  expect(ducks).toHaveLength(MAX_SPRITES_PER_SIDE);
  expect(scene.texts.map((t) => t.text)).toContain("× 1,000");
  expect(fetch).not.toHaveBeenCalled();
});

test("fixtures mode: /battle/two-hundred-vs-five plays the log that fills the event cap", async () => {
  vi.stubEnv("VITE_USE_FIXTURES", "true");
  const log = CROWD_BATTLES.get("two-hundred-vs-five")!.representative_log;
  expect(log.length).toBeGreaterThan(290);
  expect(log.length).toBeLessThanOrEqual(300); // the engine's MAX_LOG_EVENTS
  expect(log.some((e) => e.text_hint === "more go down")).toBe(true);
  open("two-hundred-vs-five");
  const scene = await stageScene();
  expect(
    screen.getByRole("img", { name: /200 ducks versus 5 lions/ }),
  ).toBeDefined();
  expect(scene.texts.map((t) => t.text)).toContain("× 200");
});

test("normal mode: /battle/thousand-vs-one asks the real API like any unknown id", async () => {
  vi.stubEnv("VITE_USE_FIXTURES", "false");
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(Response.json({}, { status: 404 }))),
  );
  open("thousand-vs-one");
  expect(await screen.findByText(NOT_FOUND)).toBeDefined();
  expect(fetch).toHaveBeenCalledWith("/api/battles/thousand-vs-one", undefined);
  expect(games).toHaveLength(0);
});
