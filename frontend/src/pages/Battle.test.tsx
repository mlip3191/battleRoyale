// The Battle page's visible states, with useBattle mocked so each state is set directly:
// the show flow, caption sync, Skip to verdict, and each degraded mode (D07).
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import running from "../fixtures/battle-record-running.json";
import done from "../fixtures/battle-record-done.json";
import type { Asset, BattleRecord } from "../api/client.ts";
import { NOT_FOUND, RETRYING } from "../api/useBattle.ts";
import Battle from "./Battle.tsx";
import Results from "./Results.tsx";
import { layoutStage } from "../game/layout.ts";
import type { PhaserStageProps } from "../game/PhaserStage.tsx";
import { linesOf, lineMs } from "./broadcast-flow.ts";

const state = vi.hoisted(() => ({
  value: { battle: null as unknown, error: null as string | null },
}));
vi.mock("../api/useBattle.ts", async (original) => ({
  ...(await original<typeof import("../api/useBattle.ts")>()),
  useBattle: () => state.value,
}));

// The real stage loads Phaser (no canvas in jsdom); a stand-in shows what it was given and keeps
// its props so tests can play events (onEvent) and end the fight (onFinish) themselves.
const stage = vi.hoisted(() => ({ props: null as unknown }));
vi.mock("../game/PhaserStage.tsx", () => ({
  default: (props: { result: { representative_log: unknown[] } }) => {
    stage.props = props;
    return (
      <div data-testid="phaser-stage">
        {props.result.representative_log.length} events
      </div>
    );
  },
}));
const stageProps = () => stage.props as PhaserStageProps;

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  stage.props = null;
});

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

const doneRecord = asRecord(done);
const intro = linesOf(doneRecord.scripts, "intro");
const outro = linesOf(doneRecord.scripts, "outro");
const pbp = linesOf(doneRecord.scripts, "play_by_play");
const captions = () => screen.getByRole("region", { name: "Captions" });
const button = (name: string) => screen.getByRole("button", { name });
const startFight = () => fireEvent.click(button("Start the fight"));

test("done: the verdict links to this battle's results", () => {
  show(done);
  fireEvent.click(button("Skip to verdict"));
  const link = screen.getByRole("link", { name: "See the full results" });
  expect(link.getAttribute("href")).toBe("/battle/b1/results");
});

test("done: after the intro, the fight replay plays the battle's result", () => {
  show(done);
  expect(screen.queryByTestId("phaser-stage")).toBeNull();
  startFight();
  expect(screen.getByTestId("phaser-stage").textContent).toBe(
    `${doneRecord.result!.representative_log.length} events`,
  );
  expect(stageProps().autoPlay).toBe(true);
});

test("intro: a title card with both fighters and the intro lines as timed captions", () => {
  vi.useFakeTimers();
  show(done);
  const card = screen.getByRole("region", { name: "Tonight's matchup" });
  expect(card.textContent).toContain(doneRecord.stat_sheets[0].display_name);
  expect(card.textContent).toContain("6 gray wolves");
  expect(captions().textContent).toContain(intro[0].text);
  expect(captions().textContent).toContain("Announcer:");
  act(() => vi.advanceTimersByTime(lineMs(intro[0].text)));
  expect(captions().textContent).toContain(intro[1].text);
  act(() => vi.advanceTimersByTime(lineMs(intro[1].text)));
  expect(screen.getByTestId("phaser-stage")).toBeTruthy();
});

test("intro: Pause captions holds the line until resumed (timing adjustable)", () => {
  vi.useFakeTimers();
  show(done);
  fireEvent.click(button("Pause captions"));
  act(() => vi.advanceTimersByTime(60_000));
  expect(captions().textContent).toContain(intro[0].text);
  fireEvent.click(button("Resume captions"));
  act(() => vi.advanceTimersByTime(lineMs(intro[0].text)));
  expect(captions().textContent).toContain(intro[1].text);
});

test("outro: the captions control goes away once the last line is up", () => {
  vi.useFakeTimers();
  show(done);
  fireEvent.click(button("Skip to verdict"));
  expect(button("Pause captions")).toBeTruthy();
  act(() => vi.advanceTimersByTime(lineMs(outro[0].text)));
  expect(captions().textContent).toContain(outro[1].text);
  expect(screen.queryByRole("button", { name: "Pause captions" })).toBeNull();
});

test("fight: captions change on onEvent(index) according to ScriptLine.at_event", () => {
  show(done);
  startFight();
  expect(captions().textContent).toBe("");
  const log = doneRecord.result!.representative_log;
  for (let i = 0; i < log.length; i += 1) {
    act(() => stageProps().onEvent!(i));
    const latest = Math.max(
      ...pbp.filter((l) => l.at_event! <= i).map((l) => l.at_event!),
    );
    const expected = pbp.filter((l) => l.at_event === latest);
    for (const line of expected)
      expect(captions().textContent).toContain(line.text);
  }
});

test("the captions are one live region that stays mounted through the whole show", () => {
  show(done);
  const region = captions();
  expect(region.getAttribute("aria-live")).toBe("polite");
  startFight();
  act(() => stageProps().onFinish!());
  expect(captions()).toBe(region);
});

test("verdict: the fight's end reveals the winner, the outro, and the results button", () => {
  show(done);
  startFight();
  act(() => stageProps().onFinish!());
  const verdict = screen.getByRole("heading", { level: 2 });
  expect(verdict.textContent).toBe("Winner: 6 gray wolves!");
  expect(screen.getByText(/Win chance 55% - range 52-58%/)).toBeTruthy();
  expect(captions().textContent).toContain(outro[0].text);
  expect(
    screen.getByRole("link", { name: "See the full results" }),
  ).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Skip to verdict" })).toBeNull();
});

test("Replay goes back to the fight captions and keeps the verdict up", () => {
  show(done);
  startFight();
  act(() => stageProps().onEvent!(10));
  act(() => stageProps().onFinish!());
  act(() => stageProps().onReplay!());
  expect(captions().textContent).toBe("");
  act(() => stageProps().onEvent!(0));
  expect(captions().textContent).toContain(pbp[0].text);
  expect(screen.getByRole("heading", { level: 2 })).toBeTruthy();
});

test("Skip to verdict: hidden before the result, shown as soon as it exists, jumps straight there", () => {
  show(running);
  expect(screen.queryByRole("button", { name: "Skip to verdict" })).toBeNull();
  cleanup();
  show({ ...doneRecord, status: "running", scripts: [], assets: [] });
  expect(screen.getByRole("status").textContent).not.toBe("");
  fireEvent.click(button("Skip to verdict"));
  expect(screen.getByRole("heading", { level: 2 }).textContent).toBe(
    "Winner: 6 gray wolves!",
  );
  expect(screen.getByRole("status").textContent).toBe("");
});

// The done battle with some assets removed.
const without = (...kinds: Asset["kind"][]) => ({
  ...doneRecord,
  assets: doneRecord.assets.filter((a) => !kinds.includes(a.kind)),
});

test("audio: narration and music get one set of labelled sound controls", () => {
  show(done);
  const bar = screen.getByRole("group", { name: "Sound controls" });
  expect(bar.querySelectorAll("audio")).toHaveLength(2);
  expect(within(bar).getByRole("button", { name: "Play sound" })).toBeTruthy();
  expect(within(bar).getByRole("slider", { name: "Volume" })).toBeTruthy();
});

test("degraded: no audio means captions only (no sound controls)", () => {
  show(without("narration_audio", "music"));
  expect(screen.queryByRole("group", { name: "Sound controls" })).toBeNull();
  expect(captions().textContent).toContain(intro[0].text);
});

test("degraded: no music means no music track; the announcer still plays", () => {
  show(without("music"));
  const bar = screen.getByRole("group", { name: "Sound controls" });
  const tracks = Array.from(bar.querySelectorAll("audio"));
  expect(tracks.map((t) => t.getAttribute("src"))).toEqual([
    "/media/audio/b-7f3k2q-narration.mp3",
  ]);
  expect(bar.textContent).toContain("Announcer only");
});

test("degraded: no images means the stage gets no pictures and draws placeholders", () => {
  show(without("sprite", "battlefield"));
  startFight();
  const assets = stageProps().assets!;
  expect(assets.some((a) => a.kind === "sprite")).toBe(false);
  const layouts = layoutStage(doneRecord.matchup.fighters, assets);
  expect(layouts.map((l) => l.spriteUrl)).toEqual([null, null]);
  expect(layouts.every((l) => l.placeholder !== null)).toBe(true);
});

test('degraded: "some effects unavailable" shows whenever a stage is fallback, and only then', () => {
  show(done);
  expect(screen.getByText("Some effects unavailable: music.")).toBeTruthy();
  cleanup();
  show({
    ...doneRecord,
    stages: doneRecord.stages.map((s) => ({ ...s, status: "done" })),
  });
  expect(screen.queryByText(/Some effects unavailable/)).toBeNull();
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
