// Plain-language "why it won" sentences (#582): built from the sheets, never invented.
import { expect, test } from "vitest";
import type { StatSheet, StatValue } from "../api/client.ts";
import { MAX_REASONS, NO_CLEAR_EDGE, whyItWon } from "./why-it-won.ts";

const stat = (value: number, is_estimate = false): StatValue =>
  ({ value, unit: "x", is_estimate }) as StatValue;
const sheet = (stats: Record<string, StatValue>) =>
  ({ stats }) as unknown as StatSheet;

const wolf = sheet({
  mass_kg: stat(40),
  top_speed_mps: stat(18),
  attack_force_n: stat(1200),
  armor_0_1: stat(0.15),
});
const bear = sheet({
  mass_kg: stat(389),
  top_speed_mps: stat(12),
  attack_force_n: stat(1000),
  armor_0_1: stat(0.3),
});

test("a side's clear edges become short sentences with the sheet's own numbers", () => {
  expect(whyItWon("Gray wolf", wolf, bear)).toEqual([
    "Gray wolf is faster: 18 m/s against 12 m/s.",
  ]);
  const reasons = whyItWon("Grizzly bear", bear, wolf);
  expect(reasons).toEqual([
    "Grizzly bear is heavier: 389 kg against 40 kg.",
    "Grizzly bear has tougher armor: 0.3 (on a 0 to 1 scale) against 0.15 (on a 0 to 1 scale).",
  ]);
});

test("a number that is an estimate is labeled as one", () => {
  const dragon = sheet({ mass_kg: stat(6000, true) });
  const hippo = sheet({ mass_kg: stat(1500) });
  expect(whyItWon("Dragon", dragon, hippo)).toEqual([
    "Dragon is heavier: 6,000 kg (estimate) against 1,500 kg.",
  ]);
});

test("only the biggest few edges are shown, biggest first", () => {
  const big = sheet({
    mass_kg: stat(1000),
    top_speed_mps: stat(40),
    attack_force_n: stat(5000),
    reach_m: stat(4),
    endurance_s: stat(900),
  });
  const small = sheet({
    mass_kg: stat(10),
    top_speed_mps: stat(10),
    attack_force_n: stat(2500),
    reach_m: stat(2),
    endurance_s: stat(600),
  });
  const reasons = whyItWon("Big", big, small);
  expect(reasons).toHaveLength(MAX_REASONS);
  expect(reasons[0]).toContain("heavier"); // 100x
  expect(reasons[1]).toContain("faster"); // 4x
});

test("a stat the winner only slightly leads, or trails in, is not a reason", () => {
  const close = sheet({ mass_kg: stat(110), top_speed_mps: stat(5) });
  const rival = sheet({ mass_kg: stat(100), top_speed_mps: stat(10) });
  expect(whyItWon("Close", close, rival)).toEqual([]);
  expect(NO_CLEAR_EDGE).toMatch(/no single stat/i);
});

test("a stat the loser has none of is still a clear edge, and one both lack is skipped", () => {
  const armed = sheet({ attack_force_n: stat(150), reach_m: stat(0) });
  const inert = sheet({ attack_force_n: stat(0), reach_m: stat(0) });
  expect(whyItWon("Armed", armed, inert)).toEqual([
    "Armed hits harder: 150 N against 0 N.",
  ]);
});
