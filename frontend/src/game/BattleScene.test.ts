// The battle scene on a stand-in Phaser: it replays beats, uses placeholders, and keeps still
// in reduced-motion mode (key frames only, no shaking, no tweens).
import { describe, expect, test, vi } from "vitest";
import type Phaser from "phaser";
import type { FightEvent, SimulationResult } from "../api/client.ts";
import fixture from "../fixtures/simulation-result.json";
import thousand from "./fixtures/thousand-vs-one.json";
import { createBattleScene, type BattleSceneOptions } from "./BattleScene.ts";
import { FakeScene, fakePhaser } from "./fake-phaser.ts";
import { MAX_SPRITES_PER_SIDE, layoutStage } from "./layout.ts";
import { buildTimeline, keyFrames } from "./timeline.ts";

const BattleScene = createBattleScene(fakePhaser as unknown as typeof Phaser);
type Scene = InstanceType<typeof BattleScene> & FakeScene;

// Build and "create" a scene for a result and matchup counts, with no images available.
function stage(
  result: SimulationResult,
  counts: [number, number],
  reducedMotion: boolean,
) {
  const fighters = [
    { entity: "grizzly bear", count: counts[0] },
    { entity: "gray wolf", count: counts[1] },
  ];
  const onEvent = vi.fn();
  const onFinish = vi.fn();
  const opts: BattleSceneOptions = {
    timeline: buildTimeline(result, counts),
    layouts: layoutStage(fighters, []),
    battlefieldUrl: null,
    outcome: result.outcome,
    reducedMotion,
    onEvent,
    onFinish,
  };
  const scene = new BattleScene(opts) as Scene;
  scene.preload();
  scene.create();
  return { scene, onEvent, onFinish };
}

// Play the whole replay in 16 ms frames.
function playAll(scene: Scene) {
  scene.play();
  for (let i = 0; i < 100_000 && !scene.clock.done; i += 1) scene.update(0, 16);
}

const result = fixture as SimulationResult;
const big = thousand as SimulationResult;

describe("placeholders", () => {
  test("no images: both sides get generated placeholder textures with their initial", () => {
    const { scene } = stage(result, [1, 6], false);
    expect(scene.load.image).not.toHaveBeenCalled();
    expect(scene.textureKeys.has("placeholder-0")).toBe(true);
    expect(scene.textureKeys.has("placeholder-1")).toBe(true);
    const keys = scene.images.map((i) => i.text);
    expect(keys.filter((k) => k === "placeholder-0")).toHaveLength(1);
    expect(keys.filter((k) => k === "placeholder-1")).toHaveLength(6);
  });

  test('1,000-v-1: 50 sprites on the crowd side, a "× 1,000" badge that counts down', () => {
    const { scene } = stage(big, [1000, 1], false);
    const crowd = scene.images.filter((i) => i.text === "placeholder-0");
    expect(crowd).toHaveLength(MAX_SPRITES_PER_SIDE);
    const badge = scene.texts.find((t) => t.text.startsWith("×"));
    expect(badge?.text).toBe("× 1,000");
    playAll(scene);
    const fell = big.representative_log
      .filter((e) => e.type === "ko" && e.side === 0)
      .reduce((n, e) => n + e.group_size, 0);
    expect(badge?.text).toBe(`× ${(1000 - fell).toLocaleString("en-US")}`);
  });
});

describe("normal motion", () => {
  test("plays every event once, in order, with tweens and a shake on hits", () => {
    const { scene, onEvent, onFinish } = stage(result, [1, 6], false);
    playAll(scene);
    expect(onEvent.mock.calls.map(([i]) => i)).toEqual(
      result.representative_log.map((_, i) => i),
    );
    expect(onFinish).toHaveBeenCalledTimes(1);
    expect(scene.tweens.add).toHaveBeenCalled();
    expect(scene.cameras.main.shake).toHaveBeenCalled();
    expect(scene.texts.some((t) => t.text === "GRAY WOLF WINS!")).toBe(true);
  });

  test("skip to end reports the rest once, stops tweens, and shows the result", () => {
    const { scene, onEvent, onFinish } = stage(result, [1, 6], false);
    scene.play();
    scene.update(0, 100);
    scene.skipToEnd();
    expect(onEvent.mock.calls.map(([i]) => i)).toEqual(
      result.representative_log.map((_, i) => i),
    );
    expect(scene.tweens.killAll).toHaveBeenCalled();
    expect(onFinish).toHaveBeenCalledTimes(1);
    expect(scene.texts.some((t) => t.text === "GRAY WOLF WINS!")).toBe(true);
  });
});

describe("reduced motion", () => {
  test("no tweens and no shaking, but every event is still reported", () => {
    const { scene, onEvent } = stage(result, [1, 6], true);
    playAll(scene);
    expect(scene.tweens.add).not.toHaveBeenCalled();
    expect(scene.cameras.main.shake).not.toHaveBeenCalled();
    expect(onEvent).toHaveBeenCalledTimes(result.representative_log.length);
    expect(scene.texts.some((t) => t.text === "GRAY WOLF WINS!")).toBe(true);
  });

  test("the picture changes only at key frames (start, each KO, end)", () => {
    const ev = (
      e: Partial<FightEvent> & Pick<FightEvent, "type">,
    ): FightEvent => ({
      t: 0,
      side: 0,
      actor: null,
      target: null,
      group_size: 1,
      damage: null,
      text_hint: "",
      ...e,
    });
    const log = [
      ev({ type: "approach", side: 0 }),
      ev({ type: "approach", side: 1, group_size: 3 }),
      ev({ type: "hit", side: 0, actor: 0, target: 1, damage: 9 }),
      ev({ type: "ko", side: 1, actor: 1 }),
      ev({ type: "retreat", side: 1, group_size: 2 }),
      ev({ type: "flee", side: 1, group_size: 2 }),
      ev({ type: "end", side: 0 }),
    ];
    const r = { ...result, outcome: "win_0" as const, representative_log: log };
    const { scene } = stage(r, [1, 3], true);
    const wolves = scene.images.filter((i) => i.text === "placeholder-1");
    const startX = wolves.map((w) => w.x);
    const keys = new Set(
      keyFrames(buildTimeline(r, [1, 3]).beats).map((b) => b.index),
    );
    expect([...keys]).toEqual([0, 3, 6]);

    scene.play();
    const snapshots: string[] = [];
    for (let i = 0; i < 100_000 && !scene.clock.done; i += 1) {
      const before = JSON.stringify(wolves.map((w) => [w.x, w.alpha]));
      scene.update(0, 16);
      const after = JSON.stringify(wolves.map((w) => [w.x, w.alpha]));
      if (before !== after) snapshots.push(after);
    }
    // The approach shows at the start, wolf 1 drops at the KO, and the escape shows at the end.
    expect(snapshots.length).toBeLessThanOrEqual(keys.size);
    expect(wolves[1].alpha).toBe(0);
    expect(wolves.every((w, i) => w.x !== startX[i])).toBe(true);
    expect(scene.tweens.add).not.toHaveBeenCalled();
  });
});
