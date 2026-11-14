// The whole broadcast in fixtures mode (no backend): ticker -> intro with captions -> fight with
// captions -> verdict -> results button. Uses the real useBattle and fixture clock; only the Phaser
// stage is a stand-in (jsdom has no canvas), driven through the same onEvent/onFinish callbacks.
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { BattleRecord } from "../api/client.ts";
import { BATTLE_MS, reset } from "../api/fixtures.ts";
import done from "../fixtures/battle-record-done.json";
import type { PhaserStageProps } from "../game/PhaserStage.tsx";
import Battle from "./Battle.tsx";
import { lineMs, linesOf } from "./broadcast-flow.ts";

const stage = vi.hoisted(() => ({ props: null as unknown }));
vi.mock("../game/PhaserStage.tsx", () => ({
  default: (props: unknown) => {
    stage.props = props;
    return <div data-testid="phaser-stage" />;
  },
}));
const stageProps = () => stage.props as PhaserStageProps;

const record = done as unknown as BattleRecord;
const intro = linesOf(record.scripts, "intro");
const pbp = linesOf(record.scripts, "play_by_play");
const outro = linesOf(record.scripts, "outro");

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubEnv("VITE_USE_FIXTURES", "true");
  vi.stubGlobal("fetch", vi.fn()); // fixtures mode must never call the network
  reset();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

// Let fixture replies and page timers run, inside React's act().
const flush = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));
const captions = () => screen.getByRole("region", { name: "Captions" });
const skipButton = () =>
  screen.queryByRole("button", { name: "Skip to verdict" });

test("fixtures mode: the whole show from the ticker to the results button", async () => {
  render(
    <MemoryRouter initialEntries={["/battle/demo"]}>
      <Routes>
        <Route path="/battle/:id" element={<Battle />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(screen.getByRole("status").textContent).toContain("Warming up");

  // Research running: the ticker shows live stage updates; no verdict to skip to yet.
  await flush(800);
  expect(screen.getByRole("status").textContent).toMatch(/Researching/);
  expect(skipButton()).toBeNull();

  // The simulation finishes: Skip to verdict appears while the rest still runs.
  await flush(BATTLE_MS / 2);
  expect(skipButton()).not.toBeNull();
  expect(screen.queryByTestId("phaser-stage")).toBeNull();

  // Every stage done: the intro card and its captions.
  await flush(BATTLE_MS);
  expect(screen.getByRole("status").textContent).toBe("");
  expect(
    screen.getByRole("region", { name: "Tonight's matchup" }),
  ).toBeTruthy();
  expect(captions().textContent).toContain(intro[0].text);
  await flush(lineMs(intro[0].text));
  expect(captions().textContent).toContain(intro[1].text);
  await flush(lineMs(intro[1].text));

  // The fight: captions follow the replay's events.
  expect(screen.getByTestId("phaser-stage")).toBeTruthy();
  expect(stage.props).not.toBeNull();
  act(() => stageProps().onEvent!(0));
  expect(captions().textContent).toContain(pbp[0].text);
  act(() => stageProps().onEvent!(5));
  expect(captions().textContent).toContain(pbp[1].text);

  // The verdict, the outro, and the way to the results page.
  act(() => stageProps().onFinish!());
  expect(screen.getByRole("heading", { level: 2 }).textContent).toBe(
    "Winner: 6 gray wolves!",
  );
  expect(captions().textContent).toContain(outro[0].text);
  const results = screen.getByRole("link", { name: "See the full results" });
  expect(results.getAttribute("href")).toBe("/battle/demo/results");
  expect(skipButton()).toBeNull();
});

test("fixtures mode: Skip to verdict during the run jumps straight to the verdict", async () => {
  render(
    <MemoryRouter initialEntries={["/battle/skip"]}>
      <Routes>
        <Route path="/battle/:id" element={<Battle />} />
      </Routes>
    </MemoryRouter>,
  );
  await flush(BATTLE_MS / 2);
  fireEvent.click(skipButton()!);
  expect(screen.getByRole("heading", { level: 2 }).textContent).toBe(
    "Winner: 6 gray wolves!",
  );
  // The show never goes back to the intro once the remaining stages finish.
  await flush(BATTLE_MS);
  expect(
    screen.queryByRole("region", { name: "Tonight's matchup" }),
  ).toBeNull();
});
