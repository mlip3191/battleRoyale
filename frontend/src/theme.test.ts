// WCAG AA check for the broadcast theme: every text/background pair must reach 4.5:1.
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

// [text, background] pairs the UI actually uses.
const pairs = [
  ["text", "bg"],
  ["muted", "bg"],
  ["neon", "bg"],
  ["hot", "bg"],
  ["text", "panel"],
  ["muted", "panel"],
  ["neon", "panel"],
  ["hot", "panel"],
  ["danger", "panel"],
  ["banner-text", "banner"],
];

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
