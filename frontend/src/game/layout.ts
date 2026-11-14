// Where each side's sprites stand on the stage, and what to draw when an image is missing (D05).
// Pure functions, no Phaser, so the rules (50-sprite cap, "× N" badge, placeholders) are testable.
import type { Asset, FighterRequest } from "../api/client.ts";
import type { Side } from "./timeline.ts";
import { pluralOf } from "../components/Verdict.tsx";

// The fixed stage the scene draws on; Phaser scales it to fit the page.
export const STAGE = { width: 960, height: 540 } as const;
export const MAX_SPRITES_PER_SIDE = 50;
const ROWS = 10; // a crowd is drawn in columns of up to 10
const FLOOR_TOP = 150; // the band of the stage where fighters stand
const FLOOR_BOTTOM = 470;

// Side colors for placeholder shapes: side 0 blue, side 1 red (text on them is white).
export const SIDE_COLORS: Record<Side, number> = { 0: 0x2f6bff, 1: 0xe5384f };

export interface Placeholder {
  color: number;
  initial: string;
}

export interface SideLayout {
  side: Side;
  name: string;
  count: number; // fighters on this side (from the matchup)
  slots: { x: number; y: number }[]; // at most MAX_SPRITES_PER_SIDE positions
  size: number; // sprite width/height in stage pixels
  badge: string | null; // "× 1,000" when the side has more fighters than slots
  spriteUrl: string | null;
  placeholder: Placeholder | null; // drawn in code when there is no sprite image
  textureKey: string; // Phaser texture name for this side's sprite
}

// "× 1,000": how a crowd's head count is shown on its badge.
export const badgeText = (count: number) =>
  `× ${Math.max(0, Math.round(count)).toLocaleString("en-US")}`;

// The fighter's initial for a placeholder shape ("grizzly bear" → "G").
export const initialOf = (name: string) =>
  name.trim().charAt(0).toUpperCase() || "?";

// A colored shape with the fighter's initial, in the side's color.
export const placeholderFor = (side: Side, name: string): Placeholder => ({
  color: SIDE_COLORS[side],
  initial: initialOf(name),
});

// Sprite size shrinks as the crowd grows so up to 50 fit on one half of the stage.
export function spriteSize(slots: number) {
  if (slots <= 1) return 140;
  if (slots <= 3) return 100;
  if (slots <= 10) return 64;
  return 30;
}

// Grid positions for one side: side 0 fills from the left edge, side 1 from the right.
export function slotPositions(side: Side, slots: number, size: number) {
  const rows = Math.min(slots, ROWS);
  const gapY = (FLOOR_BOTTOM - FLOOR_TOP) / rows;
  const gapX = size + 6;
  const edge = 80 + size / 2;
  return Array.from({ length: slots }, (_, i) => {
    const col = Math.floor(i / ROWS);
    const row = i % ROWS;
    const offset = edge + col * gapX;
    return {
      x: Math.round(side === 0 ? offset : STAGE.width - offset),
      y: Math.round(FLOOR_TOP + gapY * (row + 0.5)),
    };
  });
}

// How many of a side's slots stay visible while `alive` of its `count` fighters are standing.
export function visibleSlots(alive: number, count: number, slots: number) {
  if (alive <= 0 || count <= 0) return 0;
  if (count <= slots) return Math.min(slots, alive);
  return Math.max(1, Math.min(slots, Math.round((alive / count) * slots)));
}

// Lowercase words joined by dashes, the way media file names spell fighters ("grizzly-bear").
const slug = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

// True when `name` appears in the sprite's id or URL as whole dash-separated words,
// so "ant" does not match "elephant" or "giant" ("-ant-" is not inside "-elephant-png-").
const namesSprite = (asset: Asset, name: string) =>
  name !== "" &&
  `-${slug(`${asset.asset_id} ${asset.url}`)}-`.includes(`-${name}-`);

// Which fighter a sprite belongs to: the one whose name it contains. When both names fit
// ("bear" and "polar bear" both fit "polar-bear.png"), the longer, more specific name wins.
function ownerOf(asset: Asset, names: readonly string[]): number | null {
  const fits = names
    .map((name, i) => ({ name, i }))
    .filter(({ name }) => namesSprite(asset, name));
  if (fits.length === 0) return null;
  const longest = Math.max(...fits.map((f) => f.name.length));
  const best = fits.filter((f) => f.name.length === longest);
  return best.length === 1 ? best[0].i : null;
}

// Pick each side's sprite URL. The Asset contract does not say which fighter a sprite belongs to,
// so a sprite is used only when that is unambiguous: its file name names exactly one side's
// fighter (whole words), or there are exactly two sprites and neither names a fighter (taken in
// fighter order). Otherwise that side gets a placeholder.
export function spriteUrls(
  assets: readonly Asset[],
  fighters: readonly Pick<FighterRequest, "entity">[],
): [string | null, string | null] {
  const sprites = assets.filter((a) => a.kind === "sprite" && a.url);
  const names = fighters.map((f) => slug(f.entity));
  const owners = sprites.map((a) => ownerOf(a, names));
  const byName = names.map((_, i) => {
    const hits = sprites.filter((_, s) => owners[s] === i);
    return hits.length === 1 ? hits[0] : null;
  });
  // Name matches win; a side with no match falls back to a placeholder.
  if (
    names[0] !== names[1] &&
    (byName[0] || byName[1]) &&
    byName[0] !== byName[1]
  ) {
    return [byName[0]?.url ?? null, byName[1]?.url ?? null];
  }
  if (names[0] === names[1] && sprites.length === 1) {
    return [sprites[0].url, sprites[0].url];
  }
  if (sprites.length === 2 && !byName[0] && !byName[1]) {
    return [sprites[0].url, sprites[1].url];
  }
  return [null, null];
}

// The battlefield backdrop, if one was made.
export const battlefieldUrl = (assets: readonly Asset[]) =>
  assets.find((a) => a.kind === "battlefield" && a.url)?.url ?? null;

// Everything the scene needs to draw one side.
export function layoutSide(
  side: Side,
  name: string,
  count: number,
  spriteUrl: string | null,
): SideLayout {
  const slots = Math.max(1, Math.min(count, MAX_SPRITES_PER_SIDE));
  // Never taller than a row, so a column of fighters doesn't overlap.
  const rowGap = Math.floor((FLOOR_BOTTOM - FLOOR_TOP) / Math.min(slots, ROWS));
  const size = Math.min(spriteSize(slots), rowGap - 4);
  return {
    side,
    name,
    count,
    slots: slotPositions(side, slots, size),
    size,
    badge: count > MAX_SPRITES_PER_SIDE ? badgeText(count) : null,
    spriteUrl,
    placeholder: spriteUrl ? null : placeholderFor(side, name),
    textureKey: `fighter-${side}`,
  };
}

// Both sides' layouts from the matchup and the battle's assets.
export function layoutStage(
  fighters: readonly Pick<FighterRequest, "entity" | "count">[],
  assets: readonly Asset[],
): [SideLayout, SideLayout] {
  const urls = spriteUrls(assets, fighters);
  return [
    layoutSide(0, fighters[0]?.entity ?? "?", fighters[0]?.count ?? 1, urls[0]),
    layoutSide(1, fighters[1]?.entity ?? "?", fighters[1]?.count ?? 1, urls[1]),
  ];
}

// The end banner for a winning side: "GRIZZLY BEAR WINS!" for one fighter, "6 GRAY WOLVES WIN!" for a
// group, so it matches the verdict's "6 gray wolves" instead of naming a single wolf.
export function winnerBanner(layout: Pick<SideLayout, "name" | "count">) {
  if (layout.count <= 1) return `${layout.name.toUpperCase()} WINS!`;
  const group = `${layout.count.toLocaleString("en-US")} ${pluralOf(layout.name)}`;
  return `${group.toUpperCase()} WIN!`;
}
