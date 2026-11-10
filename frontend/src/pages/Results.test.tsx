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
  expect(verdict.textContent).toContain("38% (35–41%)");
  expect(verdict.textContent).toContain("55% (52–58%)");
  expect(verdict.textContent).toContain("Draw7%");
  expect(verdict.textContent).toContain(
    record.result!.deciding_factor_explainer,
  );
});

test("fair fight: shows the count", () => {
  show(record);
  const card = screen.getByRole("region", { name: "Fair fight" });
  expect(card.textContent).toContain(record.fair_fight!.message);
  expect(card.textContent).toContain(
    "Tested with 4 × gray wolf: 49% win chance.",
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

test("'Fight them!' failing keeps the card and says so", async () => {
  api.createBattle.mockRejectedValue(new Error("offline"));
  show(record);
  fireEvent.click(screen.getByRole("button", { name: "Fight them!" }));
  await waitFor(() =>
    expect(screen.getByRole("alert").textContent).toContain("couldn't book"),
  );
  expect(screen.getByRole("button", { name: "Fight them!" })).toBeTruthy();
});

test("a draw has no winner to send on, so no 'Fight them!' button", () => {
  show({ ...record, result: { ...record.result!, outcome: "draw" } });
  expect(screen.getByRole("heading", { name: "It's a draw" })).toBeTruthy();
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
