// WCAG AA check for the broadcast theme: every text/background pair must reach 4.5:1.
// The pairs are built from every colour token in index.css, so a new colour is checked automatically.
import { expect, test } from "vitest";
import css from "./index.css?raw";

const vars = Object.fromEntries(
  [...css.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]),
);

// Relative luminance of a #rrggbb color (WCAG 2.x formula).
function luminance(hex: string) {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// Contrast ratio between two colors, from 1:1 to 21:1.
function contrast(a: string, b: string) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// Pairing rule, applied to every colour token:
// - Page surfaces (below) are backgrounds that any text may sit on.
// - A token named "<surface>-text" is the text colour for that one surface, and that surface is
//   a special background (like the gold banner) that only its own text colour sits on.
// - Every other colour token is a text colour and must pass on every page surface.
// A new background colour is treated as text until it is added here, so it can't slip through.
const pageSurfaces = ["bg", "panel"];
const tokens = Object.keys(vars);
const specialSurfaces = tokens
  .filter((t) => t.endsWith("-text"))
  .map((t) => t.slice(0, -"-text".length));
const textColours = tokens.filter(
  (t) =>
    !pageSurfaces.includes(t) &&
    !specialSurfaces.includes(t) &&
    !t.endsWith("-text"),
);
const pairs = [
  ...textColours.flatMap((fg) => pageSurfaces.map((bg) => [fg, bg])),
  ...specialSurfaces.map((bg) => [`${bg}-text`, bg]),
];

test("every colour token is a #rrggbb value this test can read", () => {
  const colourValues = [...css.matchAll(/--([\w-]+):\s*([^;]+);/g)].filter(
    ([, , value]) =>
      /^(#|rgb|hsl|hwb|lab|lch|oklab|oklch|color\()/i.test(value),
  );
  for (const [, name, value] of colourValues) {
    expect(vars[name], `--${name}: ${value} should be #rrggbb`).toBe(value);
  }
});

test("the pairing covers the theme's surfaces and text colours", () => {
  for (const surface of [...pageSurfaces, ...specialSurfaces]) {
    expect(vars[surface], `--${surface} is defined`).toBeDefined();
  }
  expect(textColours.length).toBeGreaterThan(0);
});

test("the pairs the results page uses are among the checked pairs", () => {
  // Stat sheet: values in --neon and tags in --hot on --panel, notes in --muted, the quote
  // tooltip on --bg, and the gold banner.
  const used = [
    ["neon", "panel"],
    ["hot", "panel"],
    ["muted", "panel"],
    ["text", "panel"],
    ["text", "bg"],
    ["neon", "bg"],
    ["banner-text", "banner"],
  ];
  const checked = pairs.map((p) => p.join(" on "));
  for (const pair of used) expect(checked).toContain(pair.join(" on "));
});

test.each(pairs)("--%s on --%s meets WCAG AA (4.5:1)", (fg, bg) => {
  expect(vars[fg], `--${fg} is defined`).toBeDefined();
  expect(vars[bg], `--${bg} is defined`).toBeDefined();
  expect(contrast(vars[fg], vars[bg])).toBeGreaterThanOrEqual(4.5);
});

test("animations stop when the user prefers reduced motion", () => {
  expect(css).toMatch(
    /@media \(prefers-reduced-motion: reduce\)\s*\{[^}]*\{[^}]*animation:\s*none\s*!important/,
  );
});
