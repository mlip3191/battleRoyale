// The Battle page's visible states, with useBattle mocked so each state is set directly.
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import running from "../fixtures/battle-record-running.json";
import done from "../fixtures/battle-record-done.json";
import type { BattleRecord } from "../api/client.ts";
import { NOT_FOUND, RETRYING } from "../api/useBattle.ts";
import Battle from "./Battle.tsx";
import Results from "./Results.tsx";

const state = vi.hoisted(() => ({
  value: { battle: null as unknown, error: null as string | null },
}));
vi.mock("../api/useBattle.ts", async (original) => ({
  ...(await original<typeof import("../api/useBattle.ts")>()),
  useBattle: () => state.value,
}));

// The real stage loads Phaser (no canvas in jsdom); a stand-in shows what it was given.
vi.mock("../game/PhaserStage.tsx", () => ({
  default: (props: { result: { representative_log: unknown[] } }) => (
    <div data-testid="phaser-stage">
      {props.result.representative_log.length} events
    </div>
  ),
}));

afterEach(cleanup);

// The app's routes for battle b1, opened at the given address.
const page = (path: string) => (
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/battle/:id" element={<Battle />} />
      <Route path="/battle/:id/results" element={<Results />} />
    </Routes>
  </MemoryRouter>
);

// Show the page for battle b1 with the given hook result.
function show(
  battle: unknown,
  error: string | null = null,
  path = "/battle/b1",
) {
  state.value = { battle, error };
  return render(page(path));
}

const asRecord = (r: unknown) => r as BattleRecord;
const backHome = () => screen.getByRole("link", { name: "Back to the studio" });

test("loading: shows the warm-up ticker", () => {
  show(null);
  expect(screen.getByRole("status").textContent).toContain(
    "Warming up the studio lights",
  );
});

test("error before any battle loads: shows the error and a way home", () => {
  show(null, RETRYING);
  expect(screen.getByRole("alert").textContent).toContain(RETRYING);
  expect(backHome().getAttribute("href")).toBe("/");
});

test("unknown battle: says not found and links home", () => {
  show(null, NOT_FOUND);
  expect(
    screen.getByRole("heading", { name: "Battle not found" }),
  ).toBeTruthy();
  expect(backHome().getAttribute("href")).toBe("/");
});

test("running: the ticker shows the running stage's detail", () => {
  show(running);
  const detail = asRecord(running).stages.find(
    (s) => s.status === "running",
  )?.detail;
  expect(detail).toBeTruthy();
  expect(screen.getByRole("status").textContent).toContain(detail!);
});

test("running without a detail: the ticker falls back to 'Researching the …'", () => {
  const record = asRecord(running);
  show({
    ...record,
    stages: record.stages.map((s) => ({ ...s, detail: null })),
  });
  expect(screen.getByRole("status").textContent).toContain(
    "Researching the grizzly bear",
  );
});

test("failed: says the fight was called off and links home", () => {
  show({ ...asRecord(running), status: "failed" });
  expect(screen.getByRole("alert").textContent).toContain("called off");
  expect(backHome().getAttribute("href")).toBe("/");
});

test("failed with an error too: shows only one alert", () => {
  show({ ...asRecord(running), status: "failed" }, RETRYING);
  const alerts = screen.getAllByRole("alert");
  expect(alerts).toHaveLength(1);
  expect(alerts[0].textContent).toContain("called off");
  expect(backHome().getAttribute("href")).toBe("/");
});

test("the ticker's status region stays mounted while the battle loads and runs", () => {
  const { rerender } = show(null);
  const region = screen.getByRole("status");
  state.value = { battle: running, error: null };
  rerender(page("/battle/b1"));
  expect(screen.getByRole("status")).toBe(region);
  state.value = { battle: done, error: null };
  rerender(page("/battle/b1"));
  expect(screen.getByRole("status")).toBe(region);
  expect(region.textContent).toBe("");
});

test("done: links to this battle's results", () => {
  show(done);
  const link = screen.getByRole("link", { name: "See the results" });
  expect(link.getAttribute("href")).toBe("/battle/b1/results");
});

test("done: plays the fight replay from the battle's result", () => {
  show(done);
  expect(screen.getByTestId("phaser-stage").textContent).toBe(
    `${asRecord(done).result!.representative_log.length} events`,
  );
});

test("running or done without a result: no replay stage", () => {
  show(running);
  expect(screen.queryByTestId("phaser-stage")).toBeNull();
  cleanup();
  show({ ...asRecord(done), result: null });
  expect(screen.queryByTestId("phaser-stage")).toBeNull();
});

test("the page has a heading for screen readers", () => {
  show(done);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
    asRecord(done).matchup.raw_text,
  );
});

test("screen readers hear the matchup once: the banner is decorative", () => {
  show(done);
  const copies = screen.getAllByText(asRecord(done).matchup.raw_text);
  const heard = copies.filter((el) => !el.closest('[aria-hidden="true"]'));
  expect(copies).toHaveLength(2);
  expect(heard).toHaveLength(1);
  expect(heard[0].tagName).toBe("H1");
});

test("results page links back to this battle's broadcast", () => {
  show(done, null, "/battle/b1/results");
  const link = screen.getByRole("link", { name: "Back to the broadcast" });
  expect(link.getAttribute("href")).toBe("/battle/b1");
});
