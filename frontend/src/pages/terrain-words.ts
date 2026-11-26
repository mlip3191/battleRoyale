// How a battlefield is worded in the card line and the matchup's own words (#612). The first
// table mirrors TERRAIN_PHRASES in backend/app/intake/parser.py (the arena is the default, so it
// has no phrase); keep the two in step.
import type { Matchup } from "../api/client.ts";

type Terrain = Matchup["terrain"];

export const TERRAIN_PHRASES: Record<Terrain, string> = {
  arena: "",
  open_field: " on an open field",
  forest: " in the forest",
  water: " in the water",
  shoreline: " on the shoreline",
  urban: " in the city",
  mountain: " on the mountain",
  sky: " in the sky",
};

// The end of the intake's card line, after the place (see ok_message in parser.py).
const RUMBLE = ". Let's get ready to rumble!";

// The card line for the battlefield the viewer picked, not the one intake read: only its place
// changes. A line in any other shape, or an unchanged battlefield, is left exactly as it was.
export function cardLine(message: string, from: Terrain, to: Terrain): string {
  if (from === to) return message;
  const old = TERRAIN_PHRASES[from] + RUMBLE;
  return message.endsWith(old)
    ? message.slice(0, -old.length) + TERRAIN_PHRASES[to] + RUMBLE
    : message;
}

// The matchup's words as the page title and results heading show them. Once the viewer has
// changed the battlefield, the place they typed is no longer true, so the words are the two sides
// as typed plus the place actually used. An unchanged battlefield keeps what was typed.
export function matchupWords(matchup: Matchup, to: Terrain): string {
  if (to === matchup.terrain) return matchup.raw_text;
  const sides = matchup.fighters.map((f) => f.raw).join(" vs ");
  return `${sides}${TERRAIN_PHRASES[to]}`;
}
