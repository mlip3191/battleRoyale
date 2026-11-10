// Stat sheet pieces (D04) against the contract fixtures: every stat traceable, honest tags,
// the guesswork banner, the lore card for mythical fighters, and the sources list.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import done from "../fixtures/battle-record-done.json";
import dragonSheet from "../fixtures/stat-sheet-dragon.json";
import toasterSheet from "../fixtures/stat-sheet-toaster.json";
import type { BattleRecord, StatSheet, StatValue } from "../api/client.ts";
import {
  formatExact,
  LoreCard,
  SourceList,
  StatSheetCard,
  statTag,
  uniqueSources,
} from "./StatSheet.tsx";
import styles from "./stat-sheet.module.css";

const sheets = (done as unknown as BattleRecord).stat_sheets;
const [grizzly] = sheets;
const dragon = dragonSheet as unknown as StatSheet;
const toaster = toasterSheet as unknown as StatSheet;

afterEach(cleanup);

// Show one card per sheet.
const showCards = (list: StatSheet[]) =>
  render(
    <>
      {list.map((s) => (
        <StatSheetCard key={s.fighter_id} sheet={s} />
      ))}
    </>,
  );

// The rows of a fighter's stat table (without the header row).
const statRows = (name: string) =>
  within(screen.getByRole("table", { name: `Stats for ${name}` }))
    .getAllByRole("row")
    .slice(1);

// The honesty tag shown on a stat row ("estimate", "assumption", "derived", ...), if any.
const tagOf = (row: HTMLElement) =>
  within(row).queryByText(
    /^(estimate|assumption|derived|hand verified|extracted)$/,
  )?.textContent;

// A stat table row by its visible label, e.g. "Armor".
const rowOf = (name: string, label: string) =>
  statRows(name).find((r) => r.querySelector("th")?.textContent === label)!;

// The grizzly sheet with only the named stats, each optionally overridden.
const grizzlyWith = (
  keys: string[],
  overrides: Record<string, Partial<StatValue>> = {},
): StatSheet => ({
  ...grizzly,
  stats: Object.fromEntries(
    keys.map((k) => [k, { ...grizzly.stats[k], ...overrides[k] }]),
  ),
});

// Our traceability promise: every stat row has a source link or an honesty tag, never a bare number.
function expectEveryStatTraceable(sheet: StatSheet) {
  const rows = statRows(sheet.display_name);
  expect(rows).toHaveLength(Object.keys(sheet.stats).length);
  for (const row of rows) {
    const link = within(row).queryByRole("link");
    expect(link || tagOf(row), row.textContent ?? "").toBeTruthy();
  }
}

test("every stat on the results fixture shows a source link or an estimate tag", () => {
  showCards(sheets);
  sheets.forEach(expectEveryStatTraceable);
});

test("the mythical and all-estimate fixtures are traceable too", () => {
  showCards([dragon, toaster]);
  [dragon, toaster].forEach(expectEveryStatTraceable);
});

test("a sourced stat links to its source in a new tab and carries its quote", () => {
  showCards([grizzly]);
  const mass = grizzly.stats.mass_kg;
  const [row] = statRows(grizzly.display_name);
  const link = within(row).getByRole("link");
  expect(link.getAttribute("href")).toBe(mass.source!.url);
  expect(link.getAttribute("target")).toBe("_blank");
  expect(link.getAttribute("rel")).toContain("noopener");
  expect(link.textContent).toContain("opens in a new tab");
  const quoteId = link.getAttribute("aria-describedby")!;
  expect(document.getElementById(quoteId)?.textContent).toContain(
    mass.source!.quote,
  );
  expect(row.textContent).toContain("389 kg");
  expect(row.textContent).toContain("high confidence");
});

test("assumptions are tagged 'assumption', defaults 'estimate', derived 'derived'", () => {
  showCards([grizzly]);
  const rows = statRows(grizzly.display_name);
  const row = (label: string) =>
    rows.find((r) => r.querySelector("th")?.textContent === label)!;
  expect(tagOf(row("Armor"))).toBe("assumption");
  expect(tagOf(row("Attack force"))).toBe("estimate");
  expect(tagOf(row("Reach"))).toBe("derived");
  expect(tagOf(row("Mass"))).toBeUndefined();
});

test("a banner appears when more than 3 stats are estimates or assumptions", () => {
  showCards([toaster]);
  expect(
    screen.getByText(/10 of 10 stats are estimates or assumptions/),
  ).toBeTruthy();
});

// Three sourced or derived stats plus three guesses (a default and two assumptions).
const threeGuesses = [
  "mass_kg",
  "size_m",
  "reach_m",
  "attack_force_n",
  "armor_0_1",
  "aggression_0_1",
];

test("no banner with exactly 3 estimates or assumptions", () => {
  const sheet = grizzlyWith(threeGuesses);
  const guesses = Object.values(sheet.stats).filter(
    (s) => s.is_estimate || s.method === "assumption",
  );
  expect(guesses).toHaveLength(3);
  showCards([sheet]);
  expect(screen.queryByText(/stats are estimates or assumptions/)).toBeNull();
});

test("the banner appears at exactly 4 estimates or assumptions", () => {
  showCards([grizzlyWith([...threeGuesses, "group_tactics_0_1"])]);
  expect(
    screen.getByText(/4 of 7 stats are estimates or assumptions/),
  ).toBeTruthy();
});

test("stat values keep every digit: tiny and many-decimal values are never rounded", () => {
  const values: Record<string, number> = {
    mass_kg: 0.00042,
    size_m: 1.23456,
    top_speed_mps: 0.123456789012,
    attack_force_n: 1234567.891,
    attacks_per_s: 4.2e-7,
    reach_m: 1.5e-25,
  };
  const overrides = Object.fromEntries(
    Object.entries(values).map(([k, value]) => [k, { value }]),
  );
  showCards([grizzlyWith(Object.keys(values), overrides)]);
  const shown = (label: string) =>
    rowOf(grizzly.display_name, label).querySelectorAll("td")[0].textContent;
  const unit = (key: string) => grizzly.stats[key].unit;
  expect(shown("Mass")).toBe(`0.00042 ${unit("mass_kg")}`);
  expect(shown("Size")).toBe(`1.23456 ${unit("size_m")}`);
  expect(shown("Top speed")).toBe(`0.123456789012 ${unit("top_speed_mps")}`);
  expect(shown("Attack force")).toBe(`1,234,567.891 ${unit("attack_force_n")}`);
  expect(shown("Attack rate")).toBe(`0.00000042 ${unit("attacks_per_s")}`);
  expect(shown("Reach")).not.toMatch(/^0 /);
  expect(shown("Reach")).toContain("15");
});

test("formatExact adds thousands separators but never drops a digit", () => {
  expect(formatExact(389)).toBe("389");
  expect(formatExact(0.0004)).toBe("0.0004");
  expect(formatExact(12000)).toBe("12,000");
  expect(formatExact(0.30000000000000004)).toBe("0.30000000000000004");
  expect(formatExact(-1234.5)).toBe("-1,234.5");
  for (const v of [0.00042, 1.23456, 1e21, 1.5e-25, 98765.4321]) {
    expect(Number(formatExact(v).replaceAll(",", ""))).toBe(v);
  }
});

test("the tag follows the stat's method, and a sourced stat is never called an estimate", () => {
  const { mass_kg: extracted, reach_m: derived } = grizzly.stats;
  const handVerified: StatValue = { ...extracted, method: "hand_verified" };
  expect(statTag(handVerified)).toBeNull();
  expect(statTag({ ...handVerified, source: null })).toBe("hand verified");
  expect(statTag({ ...extracted, source: null })).toBe("extracted");
  expect(statTag(extracted)).toBeNull();
  expect(statTag(derived)).toBe("derived");
  expect(statTag({ ...derived, source: extracted.source })).toBe("derived");
  expect(statTag(grizzly.stats.armor_0_1)).toBe("assumption");
  expect(statTag(grizzly.stats.attack_force_n)).toBe("estimate");
});

test("a hand-verified stat without a source is tagged 'hand verified', not 'estimate'", () => {
  showCards([
    grizzlyWith(["mass_kg"], {
      mass_kg: { method: "hand_verified", source: null },
    }),
  ]);
  const row = rowOf(grizzly.display_name, "Mass");
  expect(tagOf(row)).toBe("hand verified");
  expect(within(row).queryByText("estimate")).toBeNull();
});

test("the confidence dot and words follow the stat's confidence", () => {
  showCards([grizzly]);
  for (const [label, level] of [
    ["Mass", "high"],
    ["Size", "medium"],
  ] as const) {
    const row = rowOf(grizzly.display_name, label);
    expect(styles[level]).toBeTruthy();
    expect(row.textContent).toContain(`${level} confidence`);
    expect(row.querySelector('[aria-hidden="true"]')?.className).toContain(
      styles[level],
    );
  }
});

test("a low-confidence sourced stat shows a low dot and the words 'low confidence'", () => {
  showCards([grizzlyWith(["mass_kg"], { mass_kg: { confidence: "low" } })]);
  const row = rowOf(grizzly.display_name, "Mass");
  expect(row.textContent).toContain("low confidence");
  expect(row.querySelector('[aria-hidden="true"]')?.className).toContain(
    styles.low,
  );
});

test("a stat's note is shown under it", () => {
  showCards([grizzly]);
  const note = grizzly.stats.reach_m.note!;
  expect(rowOf(grizzly.display_name, "Reach").textContent).toContain(note);
});

test("a mythical fighter shows the LoreCard and the Legendary fighter banner", () => {
  showCards([dragon]);
  const lore = screen.getByRole("region", { name: "According to legend" });
  expect(lore.textContent).toContain(
    "Modeled on saltwater crocodile, scaled to African elephant.",
  );
  const abilities = within(lore).getByRole("list", { name: "Abilities" });
  expect(within(abilities).getAllByRole("listitem")).toHaveLength(2);
  expect(abilities.textContent).toContain("Flight");
  expect(abilities.textContent).toContain("Breath weapon");
  expect(lore.textContent).toContain(dragon.lore!.source.quote);
  expect(within(lore).getByRole("link").getAttribute("href")).toBe(
    dragon.lore!.source.url,
  );
  expect(
    screen.getByText("Legendary fighter: every stat is an assumption"),
  ).toBeTruthy();
  expect(screen.queryByText(/stats are estimates or assumptions/)).toBeNull();
  for (const row of statRows("Dragon")) expect(tagOf(row)).toBe("assumption");
});

test("a LoreCard without a size analog just names the body it is modeled on", () => {
  render(<LoreCard lore={{ ...dragon.lore!, size_analog: null }} />);
  const lore = screen.getByRole("region", { name: "According to legend" });
  expect(lore.textContent).toContain("Modeled on saltwater crocodile.");
  expect(lore.textContent).not.toContain("scaled to");
});

test("a LoreCard with extra heads shows how many", () => {
  render(
    <LoreCard
      lore={{
        ...dragon.lore!,
        abilities: [...dragon.lore!.abilities, "extra_heads"],
        heads: 3,
      }}
    />,
  );
  const abilities = screen.getByRole("list", { name: "Abilities" });
  expect(within(abilities).getAllByRole("listitem")).toHaveLength(3);
  expect(abilities.textContent).toContain("Extra heads (3)");
});

test("a legendary sheet with a non-assumption stat drops the 'every stat' claim", () => {
  showCards([
    { ...dragon, stats: { ...dragon.stats, mass_kg: grizzly.stats.mass_kg } },
  ]);
  expect(screen.getByText("Legendary fighter")).toBeTruthy();
  expect(screen.queryByText(/every stat is an assumption/)).toBeNull();
});

test("each fighter card has its own heading below the page's sections", () => {
  showCards(sheets);
  const names = screen.getAllByRole("heading", { level: 3 });
  expect(names.map((h) => h.textContent)).toEqual(
    sheets.map((s) => s.display_name),
  );
});

test("the Sources section lists every unique source once, with title, URL, and license", () => {
  const all = [...sheets, dragon];
  render(<SourceList sheets={all} />);
  const urls = new Set(
    all
      .flatMap((s) => [
        ...Object.values(s.stats).map((v) => v.source?.url),
        s.lore?.source.url,
      ])
      .filter(Boolean),
  );
  const items = within(
    screen.getByRole("region", { name: "Sources" }),
  ).getAllByRole("listitem");
  expect(items).toHaveLength(urls.size);
  uniqueSources(all).forEach((source, i) => {
    expect(within(items[i]).getByRole("link").getAttribute("href")).toBe(
      source.url,
    );
    expect(items[i].textContent).toContain(source.title);
    expect(items[i].textContent).toContain(source.url);
    expect(items[i].textContent).toContain(source.license);
  });
});

test("the Sources section says so when nothing was sourced", () => {
  render(<SourceList sheets={[toaster]} />);
  expect(screen.getByText(/every stat here is an estimate/)).toBeTruthy();
});
