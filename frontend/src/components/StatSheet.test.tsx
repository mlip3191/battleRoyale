// Stat sheet pieces (D04) against the contract fixtures: every stat traceable, honest tags,
// the guesswork banner, the lore card for mythical fighters, and the sources list.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import done from "../fixtures/battle-record-done.json";
import dragonSheet from "../fixtures/stat-sheet-dragon.json";
import toasterSheet from "../fixtures/stat-sheet-toaster.json";
import type { BattleRecord, StatSheet } from "../api/client.ts";
import {
  SourceList,
  StatSheetCard,
  formatStatValue,
  statTag,
  uniqueSources,
} from "./StatSheet.tsx";

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

// The honesty tag shown on a stat row ("estimate", "assumption", "derived"), if any.
const tagOf = (row: HTMLElement) =>
  within(row).queryByText(
    /^(estimate|assumption|derived|hand verified|extracted)$/,
  )?.textContent;

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

test("tiny and precise values keep every digit (the UI never rounds)", () => {
  expect(formatStatValue(0.00042)).toBe("0.00042");
  expect(formatStatValue(1.23456)).toBe("1.23456");
  expect(formatStatValue(1500)).toBe("1,500");
  const mass = grizzly.stats.mass_kg;
  const stats = { ...grizzly.stats, mass_kg: { ...mass, value: 0.00042 } };
  showCards([{ ...grizzly, stats }]);
  const [row] = statRows(grizzly.display_name);
  expect(row.textContent).toContain(`0.00042 ${mass.unit}`);
});

test("the tag follows the method, so a sourceless hand-verified stat isn't called an estimate", () => {
  const mass = grizzly.stats.mass_kg;
  const bare = { ...mass, source: null, is_estimate: false };
  expect(statTag({ ...bare, method: "hand_verified" })).toBe("hand verified");
  expect(statTag({ ...bare, method: "derived" })).toBe("derived");
  expect(
    statTag({ ...bare, method: "category_default", is_estimate: true }),
  ).toBe("estimate");
  expect(statTag(mass)).toBeNull();
  const stats = {
    ...grizzly.stats,
    mass_kg: { ...bare, method: "hand_verified" as const },
  };
  showCards([{ ...grizzly, stats }]);
  const [row] = statRows(grizzly.display_name);
  expect(tagOf(row)).toBe("hand verified");
});

test("a banner appears when more than 3 stats are estimates or assumptions", () => {
  showCards([toaster]);
  expect(
    screen.getByText(/10 of 10 stats are estimates or assumptions/),
  ).toBeTruthy();
});

test("no banner with 3 or fewer estimates or assumptions", () => {
  const keep = ["mass_kg", "size_m", "attack_force_n", "armor_0_1", "reach_m"];
  const stats = Object.fromEntries(keep.map((k) => [k, grizzly.stats[k]]));
  showCards([{ ...grizzly, stats }]);
  expect(screen.queryByText(/stats are estimates or assumptions/)).toBeNull();
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
