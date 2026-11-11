// Stage layout rules: the 50-per-side cap, "× N" badges, placeholders, and sprite matching (D05).
import { describe, expect, test } from "vitest";
import type { Asset } from "../api/client.ts";
import done from "../fixtures/battle-record-done.json";
import {
  MAX_SPRITES_PER_SIDE,
  SIDE_COLORS,
  STAGE,
  badgeText,
  battlefieldUrl,
  layoutSide,
  layoutStage,
  spriteUrls,
  visibleSlots,
} from "./layout.ts";

const assets = done.assets as Asset[];
const fighters = done.matchup.fighters;
const sprite = (asset_id: string, url: string): Asset => ({
  asset_id,
  kind: "sprite",
  url,
  prompt_hash: "x",
  fallback: false,
});

describe("sprite cap and badges", () => {
  test('1,000 fighters draw 50 sprites with a "× 1,000" badge', () => {
    const side = layoutSide(0, "house cat", 1000, null);
    expect(side.slots).toHaveLength(MAX_SPRITES_PER_SIDE);
    expect(side.badge).toBe("× 1,000");
  });

  test("50 or fewer fighters get one sprite each and no badge", () => {
    expect(layoutSide(1, "gray wolf", 6, null)).toMatchObject({ badge: null });
    expect(layoutSide(1, "gray wolf", 6, null).slots).toHaveLength(6);
    expect(layoutSide(0, "ant", 50, null).slots).toHaveLength(50);
    expect(layoutSide(0, "ant", 50, null).badge).toBeNull();
    expect(layoutSide(0, "ant", 51, null).slots).toHaveLength(50);
    expect(layoutSide(0, "ant", 51, null).badge).toBe("× 51");
  });

  test("badge text groups thousands", () => {
    expect(badgeText(10000)).toBe("× 10,000");
    expect(badgeText(1)).toBe("× 1");
  });

  test("every slot is on the stage, side 0 on the left half and side 1 on the right", () => {
    for (const count of [1, 6, 50, 1000]) {
      const left = layoutSide(0, "a", count, null);
      const right = layoutSide(1, "b", count, null);
      for (const { x, y } of left.slots) {
        expect(x).toBeGreaterThan(0);
        expect(x).toBeLessThan(STAGE.width / 2);
        expect(y).toBeGreaterThan(0);
        expect(y).toBeLessThan(STAGE.height);
      }
      for (const { x } of right.slots) {
        expect(x).toBeGreaterThan(STAGE.width / 2);
        expect(x).toBeLessThan(STAGE.width);
      }
    }
  });

  test("a sprite is never taller than its row, so fighters in a column don't overlap", () => {
    for (let count = 1; count <= MAX_SPRITES_PER_SIDE; count++) {
      const { slots, size } = layoutSide(0, "a", count, null);
      expect(size).toBeGreaterThan(0);
      // The first column holds up to 10 fighters, top to bottom.
      const column = slots.slice(0, 10);
      for (let row = 1; row < column.length; row++) {
        expect(column[row].y - column[row - 1].y).toBeGreaterThanOrEqual(size);
      }
    }
  });

  test("sprite sizes: big for a lone fighter, capped by row height for a column", () => {
    const sizeFor = (count: number) => layoutSide(1, "b", count, null).size;
    expect(sizeFor(1)).toBe(140);
    expect(sizeFor(3)).toBe(100);
    expect(sizeFor(6)).toBe(49); // 64 would overlap: six rows are 53 px apart
    expect(sizeFor(10)).toBe(28);
    expect(sizeFor(50)).toBe(28);
    expect(sizeFor(1000)).toBe(28);
  });

  test("visible sprites shrink with the crowd but never vanish while someone stands", () => {
    expect(visibleSlots(1000, 1000, 50)).toBe(50);
    expect(visibleSlots(500, 1000, 50)).toBe(25);
    expect(visibleSlots(3, 1000, 50)).toBe(1);
    expect(visibleSlots(0, 1000, 50)).toBe(0);
    expect(visibleSlots(4, 6, 6)).toBe(4);
  });
});

describe("placeholders when images are missing", () => {
  test("no assets: both sides get side-colored shapes with the fighter's initial", () => {
    const [bear, wolves] = layoutStage(fighters, []);
    expect(bear.spriteUrl).toBeNull();
    expect(bear.placeholder).toEqual({ color: SIDE_COLORS[0], initial: "G" });
    expect(wolves.placeholder).toEqual({ color: SIDE_COLORS[1], initial: "G" });
    expect(SIDE_COLORS[0]).not.toBe(SIDE_COLORS[1]);
  });

  test("side 0 is blue-ish and side 1 is red-ish", () => {
    const rgb = (c: number) => [(c >> 16) & 255, (c >> 8) & 255, c & 255];
    const [r0, , b0] = rgb(SIDE_COLORS[0]);
    const [r1, , b1] = rgb(SIDE_COLORS[1]);
    expect(b0).toBeGreaterThan(r0);
    expect(r1).toBeGreaterThan(b1);
  });

  test("with the fixture's sprites, each side uses its own image and no placeholder", () => {
    const [bear, wolves] = layoutStage(fighters, assets);
    expect(bear.spriteUrl).toBe("/media/sprites/grizzly-bear.png");
    expect(wolves.spriteUrl).toBe("/media/sprites/gray-wolf.png");
    expect(bear.placeholder).toBeNull();
    expect(battlefieldUrl(assets)).toBe("/media/battlefields/forest.png");
    expect(battlefieldUrl([])).toBeNull();
  });

  test("an ambiguous sprite is not guessed: that side gets a placeholder", () => {
    const three = [
      sprite("s1", "/media/a.png"),
      sprite("s2", "/media/b.png"),
      sprite("s3", "/media/c.png"),
    ];
    expect(spriteUrls(three, fighters)).toEqual([null, null]);
    const onlyBear = [
      sprite("sprite-grizzly-bear", "/media/sprites/grizzly-bear.png"),
    ];
    expect(spriteUrls(onlyBear, fighters)).toEqual([
      "/media/sprites/grizzly-bear.png",
      null,
    ]);
    const [, wolves] = layoutStage(fighters, onlyBear);
    expect(wolves.placeholder).toEqual({ color: SIDE_COLORS[1], initial: "G" });
  });

  test("names match whole words only: an ant does not take an elephant's sprite", () => {
    const antVsElephant = [{ entity: "ant" }, { entity: "elephant" }];
    const elephantOnly = [
      sprite("sprite-elephant", "/media/sprites/elephant.png"),
    ];
    expect(spriteUrls(elephantOnly, antVsElephant)).toEqual([
      null,
      "/media/sprites/elephant.png",
    ]);
    const giant = [sprite("s1", "/media/sprites/giant-squid.png")];
    expect(spriteUrls(giant, antVsElephant)).toEqual([null, null]);
  });

  test("when two names fit one sprite, the more specific name owns it", () => {
    const bears = [{ entity: "bear" }, { entity: "polar bear" }];
    const polarOnly = [sprite("s1", "/media/sprites/polar-bear.png")];
    expect(spriteUrls(polarOnly, bears)).toEqual([
      null,
      "/media/sprites/polar-bear.png",
    ]);
    const both = [
      sprite("s1", "/media/sprites/polar-bear.png"),
      sprite("s2", "/media/sprites/bear.png"),
    ];
    expect(spriteUrls(both, bears)).toEqual([
      "/media/sprites/bear.png",
      "/media/sprites/polar-bear.png",
    ]);
  });

  test("two unnamed sprites are taken in fighter order", () => {
    const two = [sprite("s1", "/media/a.png"), sprite("s2", "/media/b.png")];
    expect(spriteUrls(two, fighters)).toEqual(["/media/a.png", "/media/b.png"]);
  });
});
