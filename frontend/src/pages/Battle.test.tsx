// The Battle page's visible states, with useBattle mocked so each state is set directly:
// the show flow, caption sync, Skip to verdict, and each degraded mode (D07).
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
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

// Press a show button the way a keyboard viewer does: focus it, then activate it.
const press = (name: string) => {
  const b = button(name);
  b.focus();
  fireEvent.click(b);
};
const verdictHeading = () => screen.getByRole("heading", { level: 2 });

test("keyboard: Skip to verdict moves focus to the verdict's heading", () => {
  show(done);
  press("Skip to verdict");
  expect(document.activeElement).toBe(verdictHeading());
  expect(verdictHeading().getAttribute("tabindex")).toBe("-1");
});

test("keyboard: Skip to verdict during the fight moves focus to the verdict's heading", () => {
  show(done);
  startFight();
  press("Skip to verdict");
  expect(document.activeElement).toBe(verdictHeading());
});

test("keyboard: Start the fight hands focus to the stage's Play/Pause, once", () => {
  show(done);
  press("Start the fight");
  expect(stageProps().claimFocus!()).toBe(true);
  expect(stageProps().claimFocus!()).toBe(false);
});

test("keyboard: the intro running out under Pause captions hands focus to the stage", () => {
  vi.useFakeTimers();
  show(done);
  button("Pause captions").focus();
  act(() => vi.advanceTimersByTime(lineMs(intro[0].text)));
  act(() => vi.advanceTimersByTime(lineMs(intro[1].text)));
  expect(stageProps().claimFocus!()).toBe(true);
});

test("keyboard: the outro's last line moves focus from Pause captions to the verdict", () => {
  vi.useFakeTimers();
  show(done);
  fireEvent.click(button("Skip to verdict"));
  button("Pause captions").focus();
  act(() => vi.advanceTimersByTime(lineMs(outro[0].text)));
  expect(screen.queryByRole("button", { name: "Pause captions" })).toBeNull();
  expect(document.activeElement).toBe(verdictHeading());
});

test("keyboard: focus is never moved when the viewer wasn't on a show button", () => {
  vi.useFakeTimers();
  show(done);
  act(() => vi.advanceTimersByTime(lineMs(intro[0].text)));
  act(() => vi.advanceTimersByTime(lineMs(intro[1].text)));
  expect(stageProps().claimFocus!()).toBe(false);
  act(() => stageProps().onFinish!());
  expect(document.activeElement).toBe(document.body);
});

test("keyboard: the ticker ending under Pause ticker moves focus to Start the fight", () => {
  const view = show(running);
  button("Pause ticker").focus();
  state.value = { battle: done, error: null };
  view.rerender(page("/battle/b1"));
  expect(screen.queryByRole("button", { name: "Pause ticker" })).toBeNull();
  expect(document.activeElement).toBe(button("Start the fight"));
});

test("keyboard: a fight called off under Pause ticker moves focus to the way home", () => {
  const view = show(running);
  button("Pause ticker").focus();
  state.value = { battle: { ...running, status: "failed" }, error: null };
  view.rerender(page("/battle/b1"));
  expect(screen.queryByRole("button", { name: "Pause ticker" })).toBeNull();
  expect(document.activeElement).toBe(backHome());
});

test("keyboard: focus given up on purpose is not pulled back by the next caption", () => {
  vi.useFakeTimers();
  show(done);
  button("Pause captions").focus();
  act(() => button("Pause captions").blur()); // a click on a blank part of the page
  act(() => vi.advanceTimersByTime(lineMs(intro[0].text)));
  expect(captions().textContent).toContain(intro[1].text);
  expect(document.activeElement).toBe(document.body);
});

test("a caption pause belongs to its part of the show: the outro starts unpaused", () => {
  vi.useFakeTimers();
  show(done);
  fireEvent.click(button("Pause captions"));
  fireEvent.click(button("Skip to verdict"));
  expect(button("Pause captions")).toBeTruthy();
  act(() => vi.advanceTimersByTime(lineMs(outro[0].text)));
  expect(captions().textContent).toContain(outro[1].text);
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

// The done battle with one narration file per script (A07), minus any scripts named.
const perScript = (...missing: Asset["script_kind"][]) => {
  const record = without("narration_audio");
  const kinds = (["intro", "play_by_play", "outro"] as const).filter(
    (k) => !missing.includes(k),
  );
  const voices = kinds.map((k): Asset => ({
    asset_id: `narration-${k}`,
    kind: "narration_audio",
    url: `/media/audio/b1-${k}.mp3`,
    prompt_hash: k,
    fallback: false,
    script_kind: k,
  }));
  return { ...record, assets: [...record.assets, ...voices] };
};
// The sources of the sound bar's tracks right now (none when it is hidden).
const trackSources = () =>
  Array.from(
    screen
      .queryByRole("group", { name: "Sound controls" })
      ?.querySelectorAll("audio") ?? [],
  ).map((t) => t.getAttribute("src"));
const MUSIC = "/media/music/retro-broadcast.mp3";

test("audio: each part of the show plays its own announcer file, under the same music", () => {
  show(perScript());
  expect(trackSources()).toEqual(["/media/audio/b1-intro.mp3", MUSIC]);
  startFight();
  expect(trackSources()).toEqual(["/media/audio/b1-play_by_play.mp3", MUSIC]);
  act(() => stageProps().onFinish!());
  expect(trackSources()).toEqual(["/media/audio/b1-outro.mp3", MUSIC]);
});

test("audio: a part with no announcer file is silent; the rest of the show goes on", () => {
  show(perScript("play_by_play"));
  expect(trackSources()).toEqual(["/media/audio/b1-intro.mp3", MUSIC]);
  startFight();
  expect(trackSources()).toEqual([MUSIC]);
  expect(screen.getByText("Music only")).toBeTruthy();
  act(() => stageProps().onFinish!());
  expect(trackSources()).toEqual(["/media/audio/b1-outro.mp3", MUSIC]);
  expect(captions().textContent).toContain(outro[0].text);
});

test("audio: an older record's single announcer file plays in every part", () => {
  const old = "/media/audio/b-7f3k2q-narration.mp3";
  show(done);
  expect(trackSources()).toEqual([old, MUSIC]);
  startFight();
  expect(trackSources()).toEqual([old, MUSIC]);
  act(() => stageProps().onFinish!());
  expect(trackSources()).toEqual([old, MUSIC]);
});

test("audio: sound turned on in the intro carries into the fight's announcer file", async () => {
  const play = vi
    .spyOn(HTMLMediaElement.prototype, "play")
    .mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  try {
    show(perScript());
    expect(play).not.toHaveBeenCalled(); // nothing plays until asked
    fireEvent.click(button("Play sound"));
    await screen.findByRole("button", { name: "Pause sound" });
    play.mockClear();
    startFight();
    await waitFor(() => expect(play).toHaveBeenCalledTimes(2));
    const started = play.mock.contexts as unknown as HTMLAudioElement[];
    expect(started.map((t) => t.getAttribute("src"))).toEqual([
      "/media/audio/b1-play_by_play.mp3",
      MUSIC,
    ]);
    expect(button("Pause sound")).toBeTruthy();
  } finally {
    vi.restoreAllMocks();
  }
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
