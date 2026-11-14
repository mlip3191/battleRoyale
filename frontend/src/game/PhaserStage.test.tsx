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
import type { Asset, BattleRecord, SimulationResult } from "../api/client.ts";
import done from "../fixtures/battle-record-done.json";
import type { BattleStage } from "./BattleScene.ts";
import { games } from "./fake-phaser.ts";
import type { SideLayout } from "./layout.ts";
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
  expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
    "Animated fight replay: 1 grizzly bear versus 6 gray wolves. The captions describe each moment.",
  );
});

test("autoPlay starts the replay as soon as it is ready", async () => {
  render(<PhaserStage result={result} matchup={battle.matchup} autoPlay />);
  const pause = await screen.findByRole("button", { name: "Pause" });
  expect(pause).toHaveProperty("disabled", false);
  expect((games[0].config.scene[0] as BattleStage).clock.playing).toBe(true);
});

test("onFinish fires once when the replay ends, by playing or by skipping", async () => {
  const onFinish = vi.fn();
  const view = render(
    <PhaserStage
      result={result}
      matchup={battle.matchup}
      onFinish={onFinish}
    />,
  );
  const scene = await sceneOf();
  fireEvent.click(screen.getByRole("button", { name: "Play" }));
  runFrames(scene);
  expect(onFinish).toHaveBeenCalledTimes(1);
  view.unmount();
  const skipped = vi.fn();
  render(
    <PhaserStage result={result} matchup={battle.matchup} onFinish={skipped} />,
  );
  await sceneOf(1);
  fireEvent.click(screen.getByRole("button", { name: "Skip to end" }));
  expect(skipped).toHaveBeenCalledTimes(1);
});

test("Replay appears after the fight ends and plays a fresh game from event 0", async () => {
  const onEvent = vi.fn();
  const onReplay = vi.fn();
  render(
    <PhaserStage
      result={result}
      matchup={battle.matchup}
      onEvent={onEvent}
      onReplay={onReplay}
    />,
  );
  await sceneOf();
  expect(screen.queryByRole("button", { name: "Replay" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Skip to end" }));
  fireEvent.click(screen.getByRole("button", { name: "Replay" }));
  expect(onReplay).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(games).toHaveLength(2));
  expect(games[0].destroy).toHaveBeenCalledTimes(1);
  const again = games[1].config.scene[0] as BattleStage;
  await waitFor(() => expect(again.clock.playing).toBe(true));
  onEvent.mockClear();
  runFrames(again);
  expect(onEvent.mock.calls.map(([i]) => i)).toEqual(allIndexes);
});

test("reduced motion: the key-moments note is real text under the stage", async () => {
  render(stageEl(vi.fn(), true));
  await sceneOf();
  const note = screen.getByText(/key moments only/);
  expect(note.closest('[role="img"]')).toBeNull();
  expect(screen.queryByText(/relative hit points/)).toBeNull();
});

test("normal motion: a note explains the damage numbers' unit", async () => {
  render(stageEl(vi.fn(), false));
  await sceneOf();
  expect(screen.getByText(/relative hit points/)).toBeTruthy();
  expect(screen.queryByText(/key moments only/)).toBeNull();
});

// The options a game's scene was built with.
const optsOf = (index: number) =>
  (
    games[index].config.scene[0] as unknown as {
      opts: { battlefieldUrl: string | null; layouts: SideLayout[] };
    }
  ).opts;

test("pictures that arrive after the stage started get a fresh stage that draws them", async () => {
  const el = (assets: Asset[]) => (
    <PhaserStage
      battleId="b1"
      result={result}
      matchup={battle.matchup}
      assets={assets}
    />
  );
  const view = render(el([]));
  await sceneOf(0);
  expect(optsOf(0).battlefieldUrl).toBeNull();
  view.rerender(el(structuredClone(battle.assets)));
  await sceneOf(1);
  expect(games[0].destroy).toHaveBeenCalledTimes(1);
  expect(optsOf(1).battlefieldUrl).toBe("/media/battlefields/forest.png");
  expect(optsOf(1).layouts.map((l) => l.spriteUrl)).toEqual([
    "/media/sprites/grizzly-bear.png",
    "/media/sprites/gray-wolf.png",
  ]);
  // New sound or the same pictures again never restart it.
  view.rerender(
    el([
      ...structuredClone(battle.assets),
      { ...battle.assets[0], asset_id: "x", kind: "music" },
    ]),
  );
  await new Promise((r) => setTimeout(r, 20));
  expect(games).toHaveLength(2);
});

test("keyboard: Skip to end moves focus to Replay instead of losing it", async () => {
  render(stageEl());
  await sceneOf();
  const skip = screen.getByRole("button", { name: "Skip to end" });
  skip.focus();
  fireEvent.click(skip);
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "Replay" }),
  );
});

test("keyboard: the fight ending under Pause moves focus to Replay", async () => {
  render(stageEl());
  const scene = await sceneOf();
  fireEvent.click(screen.getByRole("button", { name: "Play" }));
  screen.getByRole("button", { name: "Pause" }).focus();
  runFrames(scene);
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "Replay" }),
  );
});

test("keyboard: Replay moves focus to Pause once the fresh game is ready", async () => {
  render(stageEl());
  await sceneOf();
  fireEvent.click(screen.getByRole("button", { name: "Skip to end" }));
  const replay = screen.getByRole("button", { name: "Replay" });
  replay.focus();
  fireEvent.click(replay);
  await waitFor(() =>
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Pause" }),
    ),
  );
});

test("keyboard: the page can hand focus to Play/Pause when the stage is ready", async () => {
  const claimFocus = vi.fn(() => true);
  render(
    <PhaserStage
      result={result}
      matchup={battle.matchup}
      autoPlay
      claimFocus={claimFocus}
    />,
  );
  const pause = await screen.findByRole("button", { name: "Pause" });
  await waitFor(() => expect(document.activeElement).toBe(pause));
  expect(claimFocus).toHaveBeenCalledTimes(1);
});

test("keyboard: focus elsewhere is left alone when the stage gets ready or ends", async () => {
  render(
    <>
      <button type="button">Elsewhere</button>
      <PhaserStage
        result={result}
        matchup={battle.matchup}
        claimFocus={() => false}
      />
    </>,
  );
  const elsewhere = screen.getByRole("button", { name: "Elsewhere" });
  elsewhere.focus();
  await sceneOf();
  fireEvent.click(screen.getByRole("button", { name: "Skip to end" }));
  expect(document.activeElement).toBe(elsewhere);
});
