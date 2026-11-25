// Plain-language reasons a side won (#582): short sentences built by code from the saved stat
// sheets, so every number is one a sheet already shows (the number rule), and an estimate is
// labeled as one. No model writes any of it.
import type { StatSheet, StatValue } from "../api/client.ts";
import { formatExact } from "./StatSheet.tsx";

// What each stat says when the winner has more of it: the phrase and how to write its unit.
const EDGES: Record<
  string,
  { says: string; unit: (stat: StatValue) => string }
> = {
  mass_kg: { says: "is heavier", unit: () => " kg" },
  top_speed_mps: { says: "is faster", unit: () => " m/s" },
  attack_force_n: { says: "hits harder", unit: () => " N" },
  attacks_per_s: { says: "strikes more often", unit: () => " times a second" },
  reach_m: { says: "reaches farther", unit: () => " m" },
  endurance_s: { says: "lasts longer", unit: () => " s" },
  armor_0_1: { says: "has tougher armor", unit: () => " (on a 0 to 1 scale)" },
};

// A stat counts as a clear edge only when the winner has at least this much more of it.
export const CLEAR_EDGE = 1.25;

// How many reasons to show: a few, so the card stays a quick read.
export const MAX_REASONS = 3;

// "1,020 N" or "6,000 kg (estimate)": the sheet's own number, with its honesty tag.
const shown = (stat: StatValue, key: string) =>
  `${formatExact(stat.value)}${EDGES[key].unit(stat)}${stat.is_estimate ? " (estimate)" : ""}`;

// The winner's clearest edges over the loser, biggest first, as short sentences. A stat the
// winner does not clearly lead in is left out, and so is one both sides lack.
export function whyItWon(
  winnerName: string,
  winner: StatSheet,
  loser: StatSheet,
): string[] {
  const edges = Object.keys(EDGES).flatMap((key) => {
    const mine = winner.stats[key];
    const theirs = loser.stats[key];
    if (!mine || !theirs || mine.value <= 0) return [];
    const ratio = theirs.value > 0 ? mine.value / theirs.value : Infinity;
    if (ratio < CLEAR_EDGE) return [];
    return [{ key, ratio, mine, theirs }];
  });
  return edges
    .sort((a, b) => b.ratio - a.ratio)
    .slice(0, MAX_REASONS)
    .map(
      ({ key, mine, theirs }) =>
        `${winnerName} ${EDGES[key].says}: ${shown(mine, key)} against ${shown(theirs, key)}.`,
    );
}

// Said when the winner has no clear edge on any stat, so the card is never empty or invented.
export const NO_CLEAR_EDGE =
  "No single stat gave it a clear edge, so it came down to how the fights played out.";
