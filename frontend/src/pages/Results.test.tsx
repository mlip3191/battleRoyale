// The results page (D04) in fixtures mode: verdict, fair fight, next challenger, no contest,
// headings, and the traceability promise on the whole page. useBattle and createBattle are mocked.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import done from "../fixtures/battle-record-done.json";
import dragonSheet from "../fixtures/stat-sheet-dragon.json";
import * as client from "../api/client.ts";
import { NOT_FOUND } from "../api/useBattle.ts";
import type { BattleRecord, StatSheet } from "../api/client.ts";
import Results from "./Results.tsx";

const state = vi.hoisted(() => ({
  value: { battle: null as unknown, error: null as string | null },
}));
vi.mock("../api/useBattle.ts", async (original) => ({
  ...(await original<typeof import("../api/useBattle.ts")>()),
  useBattle: () => state.value,
}));
vi.mock("../api/client.ts", async (original) => ({
  ...(await original<typeof import("../api/client.ts")>()),
  createBattle: vi.fn(),
}));
const api = vi.mocked(client);

const record = done as unknown as BattleRecord;
const dragon = dragonSheet as unknown as StatSheet;

beforeEach(() => {
  api.createBattle.mockResolvedValue({ battle_id: "b-new" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Show the results page for battle b1 with the given record, plus a stand-in page to land on.
function show(battle: BattleRecord | null, error: string | null = null) {
  state.value = { battle, error };
  render(
    <MemoryRouter initialEntries={["/battle/b1/results"]}>
      <Routes>
        <Route path="/battle/:id/results" element={<Results />} />
        <Route path="/battle/:id" element={<p>Broadcast page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

test("every stat on the page shows a source link or an estimate tag", () => {
  show({ ...record, stat_sheets: [...record.stat_sheets, dragon] });
  const rows = screen
    .getAllByRole("table")
    .flatMap((t) => within(t).getAllByRole("row").slice(1));
  expect(rows).toHaveLength(30);
  for (const row of rows) {
    const link = within(row).queryByRole("link");
    const tag = within(row).queryByText(/^(estimate|assumption|derived)$/);
    expect(link || tag, row.textContent ?? "").toBeTruthy();
  }
});

test("win % is shown with its range, plus the deciding-factor explainer", () => {
  show(record);
  const verdict = screen.getByRole("region", { name: "Winner: 6 gray wolves" });
  expect(verdict.textContent).toContain("38% - range 35-41%");
  expect(verdict.textContent).toContain("55% - range 52-58%");
  expect(verdict.textContent).toContain("Draw7%");
  expect(verdict.textContent).toContain(
    record.result!.deciding_factor_explainer,
  );
});

test("averages over many runs are rounded to one decimal, and duration sits outside the draw row", () => {
  const result = {
    ...record.result!,
    mean_survivors: [0.38, 2.738] as [number, number],
    mean_duration_s: 41.237,
  };
  show({ ...record, result });
  const verdict = screen.getByRole("region", { name: "Winner: 6 gray wolves" });
  expect(verdict.textContent).toContain("about 0.4 left standing on average");
  expect(verdict.textContent).toContain("about 2.7 left standing on average");
  expect(verdict.textContent).toContain("Fights last about 41.2 s on average.");
  expect(verdict.textContent).not.toMatch(/2\.738|41\.237/);
  const draw = within(verdict).getByText("Draw").parentElement!;
  expect(draw.textContent).not.toContain("Fights last");
});

test("a stalemate's explainer is shown as written", () => {
  const explainer =
    "Neither side could hurt the other, so it ended in a stalemate.";
  show({
    ...record,
    result: {
      ...record.result!,
      outcome: "draw",
      deciding_factor_explainer: explainer,
    },
  });
  expect(
    screen.getByRole("region", { name: "It's a draw" }).textContent,
  ).toContain(explainer);
});

test("a 'too close to call' explainer is shown as written", () => {
  const explainer =
    "Too close to call: the two sides traded wins almost evenly.";
  show({
    ...record,
    result: { ...record.result!, deciding_factor_explainer: explainer },
  });
  const verdict = screen.getByRole("region", { name: "Winner: 6 gray wolves" });
  expect(verdict.textContent).toContain(`Deciding factor: ${explainer}`);
});

test.each(["", "   ", "Deciding factor not computed."])(
  "no 'Deciding factor' line when the explainer is %j",
  (explainer) => {
    show({
      ...record,
      result: { ...record.result!, deciding_factor_explainer: explainer },
    });
    const verdict = screen.getByRole("region", {
      name: "Winner: 6 gray wolves",
    });
    expect(verdict.textContent).not.toContain("Deciding factor");
    expect(verdict.textContent).not.toContain("not computed");
  },
);

test("a single fighter is named by its stat sheet's display name", () => {
  show({ ...record, result: { ...record.result!, outcome: "win_0" } });
  const name = record.stat_sheets[0].display_name;
  const verdict = screen.getByRole("region", { name: `Winner: ${name}` });
  expect(within(verdict).getByText(name)).toBeTruthy();
  expect(within(verdict).getByText("6 gray wolves")).toBeTruthy();
});

test("a finished battle with no result says so instead of showing nothing", () => {
  show({ ...record, status: "done", result: null });
  const alert = screen.getByRole("alert");
  expect(alert.textContent).toContain("No verdict");
  expect(alert.textContent).toContain("result is missing");
  expect(screen.queryByRole("region", { name: /Next challenger/ })).toBeNull();
});

test("fair fight: shows the count", () => {
  show(record);
  const card = screen.getByRole("region", { name: "Fair fight" });
  expect(card.textContent).toContain(record.fair_fight!.message);
  expect(card.textContent).toContain(
    "Tested with 4 gray wolves: 49% win chance.",
  );
});

test("fair fight: shows the no-fair-fight message when there is no count", () => {
  const message = "No number of gray wolves makes this a fair fight.";
  show({
    ...record,
    fair_fight: {
      varied_side: 1,
      count: null,
      win_prob_at_count: null,
      message,
    },
  });
  const card = screen.getByRole("region", { name: "No fair fight" });
  expect(card.textContent).toContain(message);
  expect(card.textContent).not.toContain("Tested with");
});

test("fair fight: varying side 0 names side 0's fighter", () => {
  show({
    ...record,
    fair_fight: {
      varied_side: 0,
      count: 2,
      win_prob_at_count: 0.51,
      message: "About 2 grizzly bears make it a coin flip.",
    },
  });
  const card = screen.getByRole("region", { name: "Fair fight" });
  expect(card.textContent).toContain(
    "Tested with 2 grizzly bears: 51% win chance.",
  );
});

test("fair fight: an 'about' count with no tested chance shows the count only", () => {
  const message = "About 40 gray wolves; we couldn't pin it closer.";
  show({
    ...record,
    fair_fight: {
      varied_side: 1,
      count: 40,
      win_prob_at_count: null,
      message,
    },
  });
  const card = screen.getByRole("region", { name: "Fair fight" });
  expect(card.textContent).toContain(message);
  expect(card.textContent).toContain("Tested with 40 gray wolves.");
  expect(card.textContent).not.toContain("win chance");
});

test("'Fight them!' posts a new battle with the winner vs the suggestion", async () => {
  show(record);
  fireEvent.click(screen.getByRole("button", { name: "Fight them!" }));
  expect(api.createBattle).toHaveBeenCalledWith({
    fighters: [
      record.matchup.fighters[1],
      {
        entity: "moose",
        count: 1,
        variant: null,
        size_reference: null,
        raw: "moose",
      },
    ],
    terrain: "forest",
    raw_text: "6 gray wolves vs moose",
    assumptions: [],
  });
  await waitFor(() => expect(screen.getByText("Broadcast page")).toBeTruthy());
});

test("booking the rematch is announced to screen readers", async () => {
  api.createBattle.mockReturnValue(new Promise(() => {}));
  show(record);
  const card = screen.getByRole("region", { name: "Next challenger: moose" });
  expect(card.textContent).toContain("one-on-one test fights");
  expect(within(card).getByRole("status").textContent).toBe("");
  fireEvent.click(screen.getByRole("button", { name: "Fight them!" }));
  expect(within(card).getByRole("status").textContent).toContain(
    "Ringing the bell",
  );
  expect(
    screen.getByRole("button", { name: "Ringing the bell…" }),
  ).toBeTruthy();
});

test("'Fight them!' failing keeps the card and says so", async () => {
  api.createBattle.mockRejectedValue(new Error("offline"));
  show(record);
  fireEvent.click(screen.getByRole("button", { name: "Fight them!" }));
  await waitFor(() =>
    expect(screen.getByRole("alert").textContent).toContain("couldn't book"),
  );
  expect(screen.getByRole("button", { name: "Fight them!" })).toBeTruthy();
});

test("a draw shows the odds but no winner and no next challenger", () => {
  show({ ...record, result: { ...record.result!, outcome: "draw" } });
  const verdict = screen.getByRole("region", { name: "It's a draw" });
  expect(verdict.textContent).toContain("38% - range 35-41%");
  expect(verdict.textContent).toContain("Draw7%");
  expect(screen.queryByText(/Winner/)).toBeNull();
  expect(screen.queryByRole("region", { name: /Next challenger/ })).toBeNull();
  expect(screen.queryByRole("button", { name: "Fight them!" })).toBeNull();
});

test("no contest: shows the explainer, no percentages, and no fair fight", () => {
  const result = {
    ...record.result!,
    outcome: "no_contest" as const,
    win_prob: [0, 0] as [number, number],
    draw_prob: 0,
  };
  show({ ...record, result });
  const verdict = screen.getByRole("region", { name: "No contest" });
  expect(verdict.textContent).toContain(result.deciding_factor_explainer);
  expect(verdict.textContent).not.toMatch(/%/);
  expect(screen.queryByRole("region", { name: /fair fight/i })).toBeNull();
  expect(screen.queryByRole("region", { name: /Next challenger/ })).toBeNull();
});

test("an unknown battle says 'Battle not found'", () => {
  show(null, NOT_FOUND);
  const alert = screen.getByRole("alert");
  expect(alert.textContent).toContain("Battle not found");
  expect(screen.queryByRole("status")?.textContent ?? "").not.toContain(
    "Tallying",
  );
});

test("a network error is shown and the ticker stops", () => {
  show(null, "We lost the feed. Check your connection.");
  expect(screen.getByRole("alert").textContent).toContain("lost the feed");
  expect(screen.queryByRole("region", { name: "Sources" })).toBeNull();
});

test("headings are in order: page, sections, then one per fighter", () => {
  show(record);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
    `Results: ${record.matchup.raw_text}`,
  );
  const h2 = screen
    .getAllByRole("heading", { level: 2 })
    .map((h) => h.textContent);
  expect(h2).toEqual([
    "Winner: 6 gray wolves",
    "Tale of the tape",
    "Fair fight",
    "Next challenger: moose",
    "Sources",
  ]);
  const h3 = screen
    .getAllByRole("heading", { level: 3 })
    .map((h) => h.textContent);
  expect(h3).toEqual(record.stat_sheets.map((s) => s.display_name));
});

test("while the battle is still running, the ticker says the scorecards are coming", () => {
  show({ ...record, status: "running", result: null, stat_sheets: [] });
  expect(screen.getByRole("status").textContent).toContain(
    "Tallying the scorecards",
  );
  expect(screen.queryByRole("region", { name: "Sources" })).toBeNull();
});

test("a called-off fight says so", () => {
  show({ ...record, status: "failed", result: null });
  expect(screen.getByRole("alert").textContent).toContain("called off");
});
