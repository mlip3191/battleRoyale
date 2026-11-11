// The React stage: one Phaser game per mount, destroyed on unmount, and controls wired to the scene.
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { BattleRecord, SimulationResult } from "../api/client.ts";
import done from "../fixtures/battle-record-done.json";
import type { BattleStage } from "./BattleScene.ts";
import { games } from "./fake-phaser.ts";
import PhaserStage from "./PhaserStage.tsx";

vi.mock("phaser", async () => (await import("./fake-phaser.ts")).fakePhaser);

const battle = done as unknown as BattleRecord;
const result = battle.result as SimulationResult;
const allIndexes = result.representative_log.map((_, i) => i);

beforeEach(() => {
  games.length = 0;
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const stageEl = (onEvent = vi.fn(), reducedMotion?: boolean) => (
  <PhaserStage
    result={result}
    matchup={battle.matchup}
    assets={battle.assets}
    onEvent={onEvent}
    reducedMotion={reducedMotion}
  />
);

// Wait for the lazy Phaser import, then return the scene the game was given.
async function sceneOf(index = 0) {
  await waitFor(() => expect(games.length).toBeGreaterThan(index));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Play" })).toHaveProperty(
      "disabled",
      false,
    ),
  );
  return games[index].config.scene[0] as BattleStage;
}

// Drive the scene's frame loop until the clock stops.
const runFrames = (scene: BattleStage, frames = 100_000) =>
  act(() => {
    for (let i = 0; i < frames && scene.clock.playing; i += 1)
      scene.update(0, 50);
  });

test("unmounting destroys the Phaser game exactly once", async () => {
  const view = render(stageEl());
  await sceneOf();
  expect(games).toHaveLength(1);
  view.unmount();
  expect(games[0].destroy).toHaveBeenCalledTimes(1);
  expect(games[0].destroy).toHaveBeenCalledWith(true);
});

test("StrictMode's double mount leaves exactly one game", async () => {
  const view = render(<StrictMode>{stageEl()}</StrictMode>);
  await sceneOf();
  await new Promise((r) => setTimeout(r, 20)); // let any late import settle
  expect(games).toHaveLength(1);
  view.unmount();
  expect(games[0].destroy).toHaveBeenCalledTimes(1);
});

test("mount, unmount, mount: the first game is destroyed and only the second runs", async () => {
  const first = render(stageEl());
  await sceneOf(0);
  first.unmount();
  render(stageEl());
  await sceneOf(1);
  expect(games).toHaveLength(2);
  expect(games[0].destroy).toHaveBeenCalledTimes(1);
  expect(games[1].destroy).not.toHaveBeenCalled();
});

test("a refreshed battle record with the same result does not restart the replay", async () => {
  const onEvent = vi.fn();
  // Each render gets brand-new objects with equal values, like a fresh fetch of the record.
  const fresh = () => structuredClone(battle);
  const el = (b: BattleRecord) => (
    <PhaserStage
      battleId="b1"
      result={b.result as SimulationResult}
      matchup={b.matchup}
      assets={b.assets}
      onEvent={onEvent}
    />
  );
  const view = render(el(fresh()));
  const scene = await sceneOf();
  fireEvent.click(screen.getByRole("button", { name: "Play" }));
  act(() => scene.update(0, 50));
  view.rerender(el(fresh()));
  view.rerender(el(fresh()));
  await new Promise((r) => setTimeout(r, 20)); // give any restart time to happen
  expect(games).toHaveLength(1);
  expect(games[0].destroy).not.toHaveBeenCalled();
  expect(scene.clock.playing).toBe(true);
  expect(screen.getByRole("button", { name: "Pause" })).toBeTruthy();
});

test("a different result or battle starts a fresh replay", async () => {
  const el = (id: string, r: SimulationResult) => (
    <PhaserStage battleId={id} result={r} matchup={battle.matchup} />
  );
  const view = render(el("b1", result));
  await sceneOf(0);
  view.rerender(el("b1", { ...result, seed: result.seed + 1 }));
  await sceneOf(1);
  expect(games[0].destroy).toHaveBeenCalledTimes(1);
  view.rerender(el("b2", { ...result, seed: result.seed + 1 }));
  await sceneOf(2);
  expect(games[1].destroy).toHaveBeenCalledTimes(1);
  expect(games).toHaveLength(3);
});

test("unmounting before Phaser finishes loading never starts a game", async () => {
  render(stageEl()).unmount();
  await new Promise((r) => setTimeout(r, 20));
  expect(games).toHaveLength(0);
});

test("Play, Pause, speed, and Skip call into the scene; onEvent fires in order", async () => {
  const onEvent = vi.fn();
  render(stageEl(onEvent));
  const scene = await sceneOf();

  fireEvent.click(screen.getByRole("button", { name: "Play" }));
  expect(scene.clock.playing).toBe(true);
  act(() => scene.update(0, 50));
  fireEvent.click(screen.getByRole("button", { name: "Pause" }));
  expect(scene.clock.playing).toBe(false);
  const seenWhilePlaying = onEvent.mock.calls.length;
  act(() => scene.update(0, 50));
  expect(onEvent.mock.calls.length).toBe(seenWhilePlaying);

  const fast = screen.getByRole("button", { name: "2× speed" });
  fireEvent.click(fast);
  expect(scene.clock.speed).toBe(2);
  expect(fast.getAttribute("aria-pressed")).toBe("true");
  expect(
    screen
      .getByRole("button", { name: "1× speed" })
      .getAttribute("aria-pressed"),
  ).toBe("false");

  fireEvent.click(screen.getByRole("button", { name: "Play" }));
  act(() => scene.update(0, 50));
  fireEvent.click(screen.getByRole("button", { name: "Skip to end" }));
  expect(onEvent.mock.calls.map(([i]) => i)).toEqual(allIndexes);
  expect(scene.clock.done).toBe(true);
  expect(screen.getByRole("button", { name: "Skip to end" })).toHaveProperty(
    "disabled",
    true,
  );
});

test("playing to the end reports every event once, in order, and resets the Play button", async () => {
  const onEvent = vi.fn();
  render(stageEl(onEvent));
  const scene = await sceneOf();
  fireEvent.click(screen.getByRole("button", { name: "Play" }));
  runFrames(scene);
  expect(onEvent.mock.calls.map(([i]) => i)).toEqual(allIndexes);
  const play = screen.getByRole("button", { name: "Play" });
  expect(play).toHaveProperty("disabled", true);
});

test("reduced motion defaults to the browser setting", async () => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: true })),
  );
  render(stageEl());
  const scene = await sceneOf();
  const opts = (scene as unknown as { opts: { reducedMotion: boolean } }).opts;
  expect(opts.reducedMotion).toBe(true);
  expect(window.matchMedia).toHaveBeenCalledWith(
    "(prefers-reduced-motion: reduce)",
  );
});

test("an explicit reducedMotion prop wins over the browser setting", async () => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: true })),
  );
  render(stageEl(vi.fn(), false));
  const scene = await sceneOf();
  const opts = (scene as unknown as { opts: { reducedMotion: boolean } }).opts;
  expect(opts.reducedMotion).toBe(false);
});

test("the controls are labeled buttons in a named group", async () => {
  render(stageEl());
  await sceneOf();
  const group = screen.getByRole("group", { name: "Replay controls" });
  expect(group.querySelectorAll("button")).toHaveLength(4);
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain(
    "grizzly bear versus gray wolf",
  );
});
