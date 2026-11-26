// The sound controls: nothing plays until asked; play/pause, mute, and volume reach every track.
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import AudioBar, {
  FINISH_WAIT_MS,
  type AudioBarHandle,
  type AudioBarProps,
  type VoiceCue,
} from "./AudioBar.tsx";

// jsdom has no media playback; record what the bar asks for instead.
const play = vi.fn(() => Promise.resolve());
const pause = vi.fn();
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(play);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(pause);
});
afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  vi.restoreAllMocks();
  play.mockClear();
  pause.mockClear();
});

const tracks = () => Array.from(document.querySelectorAll("audio"));

test("no tracks: no controls at all", () => {
  const { container } = render(<AudioBar narration={null} music={null} />);
  expect(container.innerHTML).toBe("");
});

test("nothing plays on its own; clicking Sound off starts both tracks, and clicking Sound on stops them", async () => {
  render(<AudioBar narration="/media/a.mp3" music="/media/m.mp3" />);
  expect(play).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  fireEvent.click(await screen.findByRole("button", { name: "Sound on" }));
  expect(play).toHaveBeenCalledTimes(2);
  expect(pause).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button", { name: "Sound off" })).toBeTruthy();
});

test("the browser refusing to play: no error, and the button stays on Sound off (no retry later)", async () => {
  play.mockImplementationOnce(() => Promise.reject(new Error("blocked")));
  render(<AudioBar narration="/media/a.mp3" music={null} />);
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
  await new Promise((r) => setTimeout(r, 0)); // let the refusal settle
  expect(screen.getByRole("button", { name: "Sound off" })).toBeTruthy();
});

test("one track refused, the other playing: the button offers Sound on", async () => {
  play.mockImplementationOnce(() => Promise.reject(new Error("blocked")));
  render(<AudioBar narration="/media/a.mp3" music="/media/m.mp3" />);
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  expect(await screen.findByRole("button", { name: "Sound on" })).toBeTruthy();
});

test("the announcer finishing on its own puts the button back to Sound off", async () => {
  render(<AudioBar narration="/media/a.mp3" music={null} />);
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  await screen.findByRole("button", { name: "Sound on" });
  fireEvent.ended(tracks()[0]);
  expect(screen.getByRole("button", { name: "Sound off" })).toBeTruthy();
});

test("the announcer finishing while the music loops on keeps Sound on", async () => {
  render(<AudioBar narration="/media/a.mp3" music="/media/m.mp3" />);
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  await screen.findByRole("button", { name: "Sound on" });
  const [voice, song] = tracks();
  Object.defineProperty(song, "paused", { value: false }); // jsdom never really plays
  fireEvent.ended(voice);
  expect(screen.getByRole("button", { name: "Sound on" })).toBeTruthy();
});

test("leaving the page stops the sound, even for tracks that arrived after the bar", async () => {
  const view = render(<AudioBar narration={null} music={null} />);
  view.rerender(<AudioBar narration="/media/a.mp3" music="/media/m.mp3" />);
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  await screen.findByRole("button", { name: "Sound on" });
  for (const t of tracks())
    Object.defineProperty(t, "paused", { value: false }); // jsdom never really plays
  pause.mockClear();
  view.unmount();
  expect(pause).toHaveBeenCalledTimes(2);
});

// The elements play() was called on, in order.
const played = () => play.mock.contexts as unknown as HTMLAudioElement[];

test("the announcer's track changing while the sound is on: the next track plays", async () => {
  const { rerender } = render(
    <AudioBar narration="/media/a.mp3" music="/media/m.mp3" />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  await screen.findByRole("button", { name: "Sound on" });
  play.mockClear();
  rerender(<AudioBar narration="/media/b.mp3" music="/media/m.mp3" />);
  await waitFor(() => expect(play).toHaveBeenCalledTimes(2));
  expect(played().map((t) => t.getAttribute("src"))).toEqual([
    "/media/b.mp3",
    "/media/m.mp3",
  ]);
  expect(screen.getByRole("button", { name: "Sound on" })).toBeTruthy();
});

test("the announcer's track changing while the sound is off: nothing starts", async () => {
  const { rerender } = render(
    <AudioBar narration="/media/a.mp3" music={null} />,
  );
  rerender(<AudioBar narration="/media/b.mp3" music={null} />);
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  fireEvent.click(await screen.findByRole("button", { name: "Sound on" }));
  play.mockClear();
  rerender(<AudioBar narration="/media/c.mp3" music={null} />);
  await new Promise((r) => setTimeout(r, 0)); // give a wrong start the chance to happen
  expect(play).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Sound off" })).toBeTruthy();
});

test("a part of the show with no announcer: the music plays on", async () => {
  const { rerender } = render(
    <AudioBar narration="/media/a.mp3" music="/media/m.mp3" />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  await screen.findByRole("button", { name: "Sound on" });
  play.mockClear();
  rerender(<AudioBar narration={null} music="/media/m.mp3" />);
  await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
  expect(played()[0].getAttribute("src")).toBe("/media/m.mp3");
  expect(screen.getByRole("button", { name: "Sound on" })).toBeTruthy();
});

test("a part of the show with nothing to play goes quiet; the next track picks the sound back up", async () => {
  const { rerender } = render(
    <AudioBar narration="/media/a.mp3" music={null} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  await screen.findByRole("button", { name: "Sound on" });
  const [voice] = tracks();
  Object.defineProperty(voice, "paused", { value: false }); // jsdom never really plays
  pause.mockClear();
  rerender(<AudioBar narration={null} music={null} />);
  expect(pause).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("group", { name: "Sound controls" })).toBeNull();
  play.mockClear();
  rerender(<AudioBar narration="/media/c.mp3" music={null} />);
  expect(await screen.findByRole("button", { name: "Sound on" })).toBeTruthy();
  expect(played().map((t) => t.getAttribute("src"))).toEqual(["/media/c.mp3"]);
});

test("the browser refusing the next track while there is no music: back to Sound off", async () => {
  const { rerender } = render(
    <AudioBar narration="/media/a.mp3" music={null} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  await screen.findByRole("button", { name: "Sound on" });
  play.mockImplementationOnce(() => Promise.reject(new Error("blocked")));
  rerender(<AudioBar narration="/media/b.mp3" music={null} />);
  expect(await screen.findByRole("button", { name: "Sound off" })).toBeTruthy();
});

test("the fight starting turns the sound on, with no button press (#499)", async () => {
  const view = render(
    <AudioBar narration="/media/a.mp3" music="/media/m.mp3" />,
  );
  expect(play).not.toHaveBeenCalled();
  view.rerender(
    <AudioBar narration="/media/b.mp3" music="/media/m.mp3" startSound />,
  );
  expect(await screen.findByRole("button", { name: "Sound on" })).toBeTruthy();
  expect(play).toHaveBeenCalledTimes(2);
});

test("switching the sound off is remembered: the next fight starts silent (#499)", async () => {
  const first = render(
    <AudioBar narration="/media/a.mp3" music={null} startSound />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Sound on" }));
  expect(screen.getByRole("button", { name: "Sound off" })).toBeTruthy();
  first.unmount();
  play.mockClear();
  render(<AudioBar narration="/media/a.mp3" music={null} startSound />);
  await new Promise((r) => setTimeout(r, 0)); // give a wrong start the chance to happen
  expect(play).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Sound off" })).toBeTruthy();
  // Switching it back on forgets the "off".
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  await screen.findByRole("button", { name: "Sound on" });
  expect(sessionStorage.getItem("battle-royale-sound-off")).toBeNull();
});

test("an off left browser-wide by an older version doesn't silence a new visit (#579)", async () => {
  localStorage.setItem("battle-royale-sound-off", "1"); // saved for the whole browser before
  render(<AudioBar narration="/media/a.mp3" music={null} startSound />);
  expect(await screen.findByRole("button", { name: "Sound on" })).toBeTruthy();
  expect(play).toHaveBeenCalledTimes(1);
});

test("switching the sound off lasts this visit: later fights start silent, a new visit starts with sound (#579)", async () => {
  const first = render(
    <AudioBar narration="/media/a.mp3" music={null} startSound />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Sound on" }));
  expect(sessionStorage.getItem("battle-royale-sound-off")).toBe("1");
  expect(localStorage.getItem("battle-royale-sound-off")).toBeNull(); // nothing beyond this visit
  first.unmount();
  play.mockClear();
  const later = render(
    <AudioBar narration="/media/a.mp3" music={null} startSound />,
  ); // a later fight in the same visit
  await new Promise((r) => setTimeout(r, 0)); // give a wrong start the chance to happen
  expect(play).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Sound off" })).toBeTruthy();
  later.unmount();
  sessionStorage.clear(); // a new visit (a new tab) starts with an empty session
  render(<AudioBar narration="/media/a.mp3" music={null} startSound />);
  expect(await screen.findByRole("button", { name: "Sound on" })).toBeTruthy();
  expect(play).toHaveBeenCalledTimes(1);
});

test("a browser that refuses the automatic start leaves the button on Sound off", async () => {
  play.mockImplementationOnce(() => Promise.reject(new Error("blocked")));
  render(<AudioBar narration="/media/a.mp3" music={null} startSound />);
  await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
  await new Promise((r) => setTimeout(r, 0));
  expect(screen.getByRole("button", { name: "Sound off" })).toBeTruthy();
});

test("Volume sets the announcer's level and keeps the music underneath", () => {
  render(<AudioBar narration="/media/a.mp3" music="/media/m.mp3" />);
  fireEvent.change(screen.getByRole("slider", { name: "Volume" }), {
    target: { value: "50" },
  });
  const [voice, song] = tracks();
  expect(voice.volume).toBeCloseTo(0.5);
  expect(song.volume).toBeCloseTo(0.2);
});

test("music alone plays at the full chosen level, on a loop", () => {
  render(<AudioBar narration={null} music="/media/m.mp3" />);
  const [song] = tracks();
  expect(song.loop).toBe(true);
  expect(song.volume).toBeCloseTo(0.8);
  expect(screen.getByText("Music only")).toBeTruthy();
});

test("at 5x and 10x the announcer waits, then picks up when the fight slows down (#577)", async () => {
  const view = render(
    <AudioBar narration="/media/a.mp3" music={null} startSound />,
  );
  await screen.findByRole("button", { name: "Sound on" });
  expect(play).toHaveBeenCalledTimes(1);
  view.rerender(
    <AudioBar narration="/media/a.mp3" music={null} startSound hold />,
  );
  expect(pause).toHaveBeenCalled();
  expect(screen.getByText("Announcer waits at this speed")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Sound on" })).toBeTruthy(); // still wanted
  view.rerender(<AudioBar narration="/media/a.mp3" music={null} startSound />);
  await waitFor(() => expect(play).toHaveBeenCalledTimes(2));
  expect(screen.getByText("Announcer only")).toBeTruthy();
});

test("switching the sound on while held waits for the fight to slow; switched off, it stays off", async () => {
  const view = render(<AudioBar narration="/media/a.mp3" music={null} hold />);
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  expect(await screen.findByRole("button", { name: "Sound on" })).toBeTruthy();
  // Nothing talks over a 10x fight: the only play is the muted unlock, paused at once (#601).
  expect(play).toHaveBeenCalledTimes(1);
  expect(voiceTrack().muted).toBe(false);
  view.rerender(<AudioBar narration="/media/a.mp3" music={null} />);
  await waitFor(() => expect(play).toHaveBeenCalledTimes(2));

  view.rerender(<AudioBar narration="/media/a.mp3" music={null} hold />);
  fireEvent.click(screen.getByRole("button", { name: "Sound on" })); // off, while held
  view.rerender(<AudioBar narration="/media/a.mp3" music={null} />);
  await new Promise((r) => setTimeout(r, 0));
  expect(play).toHaveBeenCalledTimes(2); // off stays off
});

test("picking 5x or 10x while the voice is still loading doesn't switch the sound off (#577)", async () => {
  // A browser rejects a play() that is still loading with AbortError when pause() cuts it short.
  let abort: (() => void) | null = null;
  play.mockImplementation(
    () =>
      new Promise<void>((_, reject) => {
        abort = () => reject(new DOMException("", "AbortError"));
      }),
  );
  pause.mockImplementation(() => {
    abort?.();
    abort = null;
  });
  try {
    const view = render(
      <AudioBar narration="/media/a.mp3" music={null} startSound />,
    );
    await waitFor(() => expect(play).toHaveBeenCalledTimes(1)); // still loading
    view.rerender(
      <AudioBar narration="/media/a.mp3" music={null} startSound hold />,
    );
    await new Promise((r) => setTimeout(r, 0)); // let the cut-short load settle
    play.mockImplementation(() => Promise.resolve());
    view.rerender(
      <AudioBar narration="/media/a.mp3" music={null} startSound />,
    );
    await waitFor(() => expect(play).toHaveBeenCalledTimes(2)); // the voice picks up again
    expect(
      await screen.findByRole("button", { name: "Sound on" }),
    ).toBeTruthy();
  } finally {
    play.mockImplementation(() => Promise.resolve());
    pause.mockImplementation(() => undefined);
  }
});

test("held at 10x when the fight ends: the outro still plays (#577)", async () => {
  const view = render(
    <AudioBar narration="/media/fight.mp3" music={null} startSound hold />,
  );
  await screen.findByRole("button", { name: "Sound on" });
  expect(play).not.toHaveBeenCalled();
  view.rerender(
    <AudioBar narration="/media/outro.mp3" music={null} startSound />,
  );
  await waitFor(() => expect(play).toHaveBeenCalled());
  expect(tracks()[0].getAttribute("src")).toBe("/media/outro.mp3");
});

// --- in sync with the fight (#576) ----------------------------------------------------------------

const voiceTrack = () => tracks()[0];
const cueOf = (at: number, start: number, end: number) => ({ at, start, end });

test("in sync, the announcer plays each moment's lines from their start and stops at their end", async () => {
  const view = render(
    <AudioBar narration="/media/pbp.wav" music={null} startSound cue={null} />,
  );
  // Sound is on, but nothing is said before the first line's moment.
  expect(await screen.findByRole("button", { name: "Sound on" })).toBeTruthy();
  expect(play).not.toHaveBeenCalled();
  view.rerender(
    <AudioBar
      narration="/media/pbp.wav"
      music={null}
      startSound
      cue={cueOf(0, 0, 1.4)}
    />,
  );
  await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
  expect(voiceTrack().currentTime).toBe(0);
  voiceTrack().currentTime = 1.5; // the lines are done
  fireEvent.timeUpdate(voiceTrack());
  expect(pause).toHaveBeenCalledTimes(1);
  view.rerender(
    <AudioBar
      narration="/media/pbp.wav"
      music={null}
      startSound
      cue={cueOf(7, 1.8, 3.2)}
    />,
  );
  await waitFor(() => expect(play).toHaveBeenCalledTimes(2));
  expect(voiceTrack().currentTime).toBe(1.8); // jumped to the next moment's lines
});

test("in sync, a re-render of the same moment never restarts its lines", async () => {
  const view = render(
    <AudioBar
      narration="/media/pbp.wav"
      music={null}
      startSound
      cue={cueOf(3, 2, 4)}
    />,
  );
  await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
  view.rerender(
    <AudioBar
      narration="/media/pbp.wav"
      music={null}
      startSound
      cue={cueOf(3, 2, 4)}
    />,
  );
  await new Promise((r) => setTimeout(r, 0));
  expect(play).toHaveBeenCalledTimes(1);
});

test("in sync, the announcer waits with the fight and finishes only lines not yet done", async () => {
  const view = render(
    <AudioBar
      narration="/media/pbp.wav"
      music={null}
      startSound
      cue={cueOf(0, 0, 2)}
    />,
  );
  await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
  view.rerender(
    <AudioBar
      narration="/media/pbp.wav"
      music={null}
      startSound
      cue={cueOf(0, 0, 2)}
      hold
    />,
  );
  expect(pause).toHaveBeenCalled();
  voiceTrack().currentTime = 0.5; // paused mid-line
  view.rerender(
    <AudioBar
      narration="/media/pbp.wav"
      music={null}
      startSound
      cue={cueOf(0, 0, 2)}
    />,
  );
  await waitFor(() => expect(play).toHaveBeenCalledTimes(2)); // finishes the line
  view.rerender(
    <AudioBar
      narration="/media/pbp.wav"
      music={null}
      startSound
      cue={cueOf(0, 0, 2)}
      hold
    />,
  );
  voiceTrack().currentTime = 2; // that line was done before the pause
  view.rerender(
    <AudioBar
      narration="/media/pbp.wav"
      music={null}
      startSound
      cue={cueOf(0, 0, 2)}
    />,
  );
  await new Promise((r) => setTimeout(r, 0));
  expect(play).toHaveBeenCalledTimes(2); // nothing more to say until the next moment
});

test("in sync, the announcer talks at the fight's speed", async () => {
  const view = render(
    <AudioBar
      narration="/media/pbp.wav"
      music={null}
      startSound
      cue={cueOf(0, 0, 2)}
      rate={2}
    />,
  );
  await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
  expect(voiceTrack().playbackRate).toBe(2);
  view.rerender(
    <AudioBar
      narration="/media/pbp.wav"
      music={null}
      startSound
      cue={cueOf(0, 0, 2)}
      rate={1}
    />,
  );
  expect(voiceTrack().playbackRate).toBe(1);
});

test("the wait note can say why the announcer waits", () => {
  render(
    <AudioBar
      narration="/media/pbp.wav"
      music={null}
      hold
      holdNote="Announcer paused with the fight"
    />,
  );
  expect(screen.getByText("Announcer paused with the fight")).toBeTruthy();
});

// --- unlocking the voice inside the viewer's click, and stopping on time (#579, #584) -------------

// What the tracks were told, in order: "play" (heard), "muted play" (the silent unlock), "pause".
const told: string[] = [];
const listen = () => {
  play.mockImplementation(function (this: HTMLMediaElement) {
    told.push(this.muted ? "muted play" : "play");
    return Promise.resolve();
  });
  pause.mockImplementation(() => {
    told.push("pause");
  });
};
afterEach(() => {
  told.length = 0;
  play.mockImplementation(() => Promise.resolve());
  pause.mockImplementation(() => undefined);
});

// jsdom never really plays: make a track look like it is playing.
const playingNow = (track: HTMLAudioElement) => {
  Object.defineProperty(track, "paused", {
    configurable: true,
    get: () => false,
  });
  return track;
};

// Let the bar's play() promises settle without moving the (fake) clock.
const settle = () =>
  act(async () => {
    for (let i = 0; i < 10; i += 1) await Promise.resolve();
  });

test("unlock: the voice plays muted and pauses at once, inside the call, and the sound stays off (#579, #584)", () => {
  listen();
  const bar = createRef<AudioBarHandle>();
  render(<AudioBar ref={bar} narration="/media/intro.wav" music={null} />);
  bar.current!.unlock();
  expect(told).toEqual(["muted play", "pause"]); // nothing is heard
  expect(voiceTrack().muted).toBe(false);
  expect(screen.getByRole("button", { name: "Sound off" })).toBeTruthy();
});

// Node's process reports promise rejections nobody handled (jsdom's window doesn't see them).
type Listener = (reason: unknown) => void;
const node = (
  globalThis as unknown as {
    process: {
      on: (event: string, f: Listener) => void;
      off: (event: string, f: Listener) => void;
    };
  }
).process;

test("unlock: a browser that refuses the play: nothing thrown or left unhandled, and the button stays on Sound off (#584)", async () => {
  const unhandled = vi.fn();
  node.on("unhandledRejection", unhandled);
  // A plain function, not a vi.fn: a mock would handle the rejection itself and hide a miss.
  const spy = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = () =>
    Promise.reject(new DOMException("", "NotAllowedError"));
  try {
    const bar = createRef<AudioBarHandle>();
    render(<AudioBar ref={bar} narration="/media/intro.wav" music={null} />);
    expect(() => bar.current!.unlock()).not.toThrow();
    await new Promise((r) => setTimeout(r, 0)); // let the refusal settle
    expect(unhandled).not.toHaveBeenCalled();
    expect(pause).toHaveBeenCalledTimes(1);
    expect(voiceTrack().muted).toBe(false);
    expect(screen.getByRole("button", { name: "Sound off" })).toBeTruthy();
  } finally {
    HTMLMediaElement.prototype.play = spy;
    node.off("unhandledRejection", unhandled);
  }
});

test("unlock: an older browser whose play() throws: the voice is still paused and unmuted (#584)", () => {
  play.mockImplementationOnce(() => {
    throw new DOMException("", "NotAllowedError");
  });
  const bar = createRef<AudioBarHandle>();
  render(<AudioBar ref={bar} narration="/media/intro.wav" music={null} />);
  expect(() => bar.current!.unlock()).not.toThrow();
  expect(pause).toHaveBeenCalledTimes(1);
  expect(voiceTrack().muted).toBe(false);
  expect(screen.getByRole("button", { name: "Sound off" })).toBeTruthy();
});

test("unlock: a remembered off, or sound already on, leaves the voice alone (#579)", async () => {
  listen();
  const bar = createRef<AudioBarHandle>();
  sessionStorage.setItem("battle-royale-sound-off", "1");
  const view = render(
    <AudioBar ref={bar} narration="/media/intro.wav" music={null} />,
  );
  bar.current!.unlock();
  expect(told).toEqual([]);
  view.unmount();
  sessionStorage.clear();
  render(<AudioBar ref={bar} narration="/media/intro.wav" music={null} />);
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  await screen.findByRole("button", { name: "Sound on" });
  told.length = 0;
  bar.current!.unlock(); // the viewer's own click already started it
  expect(told).toEqual([]);
});

test("in sync, Sound on before the first line unlocks the voice inside the click, then waits for its cue (#584)", async () => {
  listen();
  render(<AudioBar narration="/media/pbp.wav" music={null} cue={null} />);
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  expect(told).toEqual(["muted play", "pause"]); // during the click itself
  expect(screen.getByRole("button", { name: "Sound on" })).toBeTruthy();
  await settle();
  expect(told).toEqual(["muted play", "pause"]); // nothing to say yet
});

test("in sync, Sound on partway through a moment finishes its lines (#584)", async () => {
  listen();
  render(
    <AudioBar narration="/media/pbp.wav" music={null} cue={cueOf(4, 1.5, 3)} />,
  );
  expect(told).toEqual([]); // sound off: the lines are only lined up
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  await waitFor(() => expect(told).toEqual(["muted play", "pause", "play"]));
  expect(voiceTrack().currentTime).toBe(1.5); // from the start of the moment's lines
  expect(screen.getByRole("button", { name: "Sound on" })).toBeTruthy();
});

test("in sync, Sound on after a moment's lines are done waits for the next moment (#584)", async () => {
  listen();
  render(
    <AudioBar narration="/media/pbp.wav" music={null} cue={cueOf(4, 1.5, 3)} />,
  );
  voiceTrack().currentTime = 3; // already said
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  await settle();
  expect(told).toEqual(["muted play", "pause"]);
  expect(screen.getByRole("button", { name: "Sound on" })).toBeTruthy();
});

test("in sync, Sound on while the fight is paused waits for it, then finishes the lines (#584)", async () => {
  listen();
  const view = render(
    <AudioBar
      narration="/media/pbp.wav"
      music={null}
      cue={cueOf(4, 1.5, 3)}
      hold
    />,
  );
  told.length = 0;
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  await settle();
  // Nothing is heard while held: the click only unlocks the voice, a muted play and pause, so
  // Safari needs no second click when the fight moves on (#601).
  expect(told).toEqual(["muted play", "pause"]);
  told.length = 0;
  view.rerender(
    <AudioBar narration="/media/pbp.wav" music={null} cue={cueOf(4, 1.5, 3)} />,
  );
  await waitFor(() => expect(told).toEqual(["play"])); // the rest of the moment's lines
  expect(voiceTrack().currentTime).toBe(1.5);
});

// Fake only the timers the bar uses to stop the voice; promises still settle.
const fakeClock = () =>
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });

test("in sync, a timer stops the voice where the cued lines end, with no timeupdate needed (#584)", async () => {
  fakeClock();
  try {
    render(
      <AudioBar
        narration="/media/pbp.wav"
        music={null}
        startSound
        cue={cueOf(0, 0, 2)}
      />,
    );
    const voice = playingNow(voiceTrack());
    await settle();
    expect(play).toHaveBeenCalledTimes(1);
    act(() => vi.advanceTimersByTime(1999));
    expect(pause).not.toHaveBeenCalled();
    voice.currentTime = 2; // the lines are said; no timeupdate event comes
    act(() => vi.advanceTimersByTime(1));
    expect(pause).toHaveBeenCalledTimes(1);
  } finally {
    vi.useRealTimers();
  }
});

test("in sync at 2x, the stop timer is half as long (#584)", async () => {
  fakeClock();
  try {
    render(
      <AudioBar
        narration="/media/pbp.wav"
        music={null}
        startSound
        cue={cueOf(0, 0, 2)}
        rate={2}
      />,
    );
    const voice = playingNow(voiceTrack());
    await settle();
    act(() => vi.advanceTimersByTime(999));
    expect(pause).not.toHaveBeenCalled();
    voice.currentTime = 2;
    act(() => vi.advanceTimersByTime(1));
    expect(pause).toHaveBeenCalledTimes(1);
  } finally {
    vi.useRealTimers();
  }
});

test("in sync, a voice that fell behind (still loading) is not cut short by the stop timer (#584)", async () => {
  fakeClock();
  try {
    render(
      <AudioBar
        narration="/media/pbp.wav"
        music={null}
        startSound
        cue={cueOf(0, 0, 2)}
      />,
    );
    const voice = playingNow(voiceTrack());
    await settle();
    voice.currentTime = 1; // it stalled for a second
    act(() => vi.advanceTimersByTime(2000));
    expect(pause).not.toHaveBeenCalled();
    voice.currentTime = 2;
    act(() => vi.advanceTimersByTime(1000)); // the rest of its lines
    expect(pause).toHaveBeenCalledTimes(1);
  } finally {
    vi.useRealTimers();
  }
});

test("in sync, a pause, a new moment or Sound off clears the stop timer (#584)", async () => {
  fakeClock();
  try {
    const at = (cue: VoiceCue, hold = false) => (
      <AudioBar
        narration="/media/pbp.wav"
        music={null}
        startSound
        cue={cue}
        hold={hold}
      />
    );
    const view = render(at(cueOf(0, 0, 2)));
    const voice = playingNow(voiceTrack());
    await settle();
    // The fight pauses: the announcer stops there, and the old timer does nothing later.
    view.rerender(at(cueOf(0, 0, 2), true));
    expect(pause).toHaveBeenCalledTimes(1);
    voice.currentTime = 2;
    act(() => vi.advanceTimersByTime(5000));
    expect(pause).toHaveBeenCalledTimes(1);

    // A new moment starts its own timer, from its own lines.
    view.rerender(at(cueOf(5, 4, 5)));
    await settle();
    expect(voice.currentTime).toBe(4);
    act(() => vi.advanceTimersByTime(999));
    expect(pause).toHaveBeenCalledTimes(1);
    voice.currentTime = 5;
    act(() => vi.advanceTimersByTime(1));
    expect(pause).toHaveBeenCalledTimes(2);

    // Sound off mid-line clears it too.
    view.rerender(at(cueOf(9, 6, 8)));
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Sound on" }));
    expect(pause).toHaveBeenCalledTimes(3);
    voice.currentTime = 8;
    act(() => vi.advanceTimersByTime(5000));
    expect(pause).toHaveBeenCalledTimes(3);
  } finally {
    vi.useRealTimers();
  }
});

test("in sync, leaving the page mid-line clears the stop timer (#584)", async () => {
  fakeClock();
  try {
    const view = render(
      <AudioBar
        narration="/media/pbp.wav"
        music={null}
        startSound
        cue={cueOf(0, 0, 2)}
      />,
    );
    const voice = playingNow(voiceTrack());
    await settle();
    expect(vi.getTimerCount()).toBe(1); // the stop at the end of the lines
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
    const stops = pause.mock.calls.length; // leaving the page stops the voice once
    voice.currentTime = 2;
    act(() => vi.advanceTimersByTime(5000));
    expect(pause).toHaveBeenCalledTimes(stops);
  } finally {
    vi.useRealTimers();
  }
});

test("in sync, a new announcer file mid-line clears the old stop timer (#584)", async () => {
  fakeClock();
  try {
    const view = render(
      <AudioBar
        narration="/media/pbp.wav"
        music={null}
        startSound
        cue={cueOf(0, 0, 2)}
      />,
    );
    const voice = playingNow(voiceTrack());
    await settle();
    expect(vi.getTimerCount()).toBe(1);
    // The fight ends mid-line: the verdict's file plays on the same track, whole.
    view.rerender(
      <AudioBar narration="/media/outro.wav" music={null} startSound />,
    );
    await settle();
    expect(voiceTrack().getAttribute("src")).toBe("/media/outro.wav");
    expect(vi.getTimerCount()).toBe(0); // the old timer never fires on the new file
    const stops = pause.mock.calls.length;
    voice.currentTime = 2;
    act(() => vi.advanceTimersByTime(5000));
    expect(pause).toHaveBeenCalledTimes(stops);
  } finally {
    vi.useRealTimers();
  }
});

// A bar in sync with the fight, showing the given moment.
const syncedAt = (cue: VoiceCue | null, extra: Partial<AudioBarProps> = {}) => (
  <AudioBar
    narration="/media/pbp.wav"
    music={null}
    startSound
    cue={cue}
    {...extra}
  />
);

test("in sync, a moment that arrives while lines are talking waits its turn, then plays whole (#601)", async () => {
  fakeClock();
  try {
    const view = render(syncedAt(cueOf(0, 0, 3)));
    const voice = playingNow(voiceTrack());
    await settle();
    expect(play).toHaveBeenCalledTimes(1);
    view.rerender(syncedAt(cueOf(1, 5, 7))); // arrives while the first lines still talk
    await settle();
    expect(voice.currentTime).toBe(0); // not cut off, not jumped
    expect(play).toHaveBeenCalledTimes(1);
    voice.currentTime = 3; // the first lines are said
    act(() => vi.advanceTimersByTime(3000));
    await settle();
    expect(voice.currentTime).toBe(5); // the waiting moment starts from its own first line
    expect(play).toHaveBeenCalledTimes(2);
    voice.currentTime = 7;
    act(() => vi.advanceTimersByTime(2000));
    expect(pause).toHaveBeenCalledTimes(2); // each stretch stopped where it ends
  } finally {
    vi.useRealTimers();
  }
});

test("in sync, several moments that arrive while lines talk play one after another in order (#601)", async () => {
  fakeClock();
  try {
    const view = render(syncedAt(cueOf(0, 0, 2)));
    const voice = playingNow(voiceTrack());
    await settle();
    view.rerender(syncedAt(cueOf(1, 4, 6)));
    await settle();
    view.rerender(syncedAt(cueOf(2, 8, 10)));
    await settle();
    expect(voice.currentTime).toBe(0);
    voice.currentTime = 2;
    act(() => vi.advanceTimersByTime(2000));
    await settle();
    expect(voice.currentTime).toBe(4);
    voice.currentTime = 6;
    act(() => vi.advanceTimersByTime(2000));
    await settle();
    expect(voice.currentTime).toBe(8);
    expect(play).toHaveBeenCalledTimes(3);
  } finally {
    vi.useRealTimers();
  }
});

test("in sync, a moment that arrives while the voice is silent replaces the one before it, as it always did (#601)", async () => {
  const view = render(syncedAt(cueOf(0, 0, 2), { hold: true }));
  await settle();
  view.rerender(syncedAt(cueOf(1, 4, 6), { hold: true }));
  await settle();
  expect(voiceTrack().currentTime).toBe(4); // nothing was talking, so nothing waits
});

test("finishing: the bar says the last lines first, then settles (#601)", async () => {
  fakeClock();
  try {
    const onSettled = vi.fn();
    const view = render(syncedAt(cueOf(0, 0, 3), { onSettled }));
    const voice = playingNow(voiceTrack());
    await settle();
    view.rerender(syncedAt(cueOf(0, 0, 3), { onSettled, finishing: true }));
    expect(onSettled).not.toHaveBeenCalled(); // still talking
    voice.currentTime = 3;
    act(() => vi.advanceTimersByTime(3000));
    expect(onSettled).toHaveBeenCalledTimes(1);
  } finally {
    vi.useRealTimers();
  }
});

test("finishing: a voice that stalls holds the show for the speech left plus the slack, no longer (#601)", async () => {
  fakeClock();
  try {
    const onSettled = vi.fn();
    const view = render(syncedAt(cueOf(0, 0, 3), { onSettled }));
    playingNow(voiceTrack());
    await settle();
    view.rerender(syncedAt(cueOf(0, 0, 3), { onSettled, finishing: true }));
    const speechLeftMs = 3000; // the lines are 3 s long and the voice never moves
    act(() => vi.advanceTimersByTime(speechLeftMs + FINISH_WAIT_MS - 1));
    expect(onSettled).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onSettled).toHaveBeenCalledTimes(1);
  } finally {
    vi.useRealTimers();
  }
});

test("finishing with nothing being said settles at once: sound off, held, or no lines (#601)", async () => {
  const off = vi.fn();
  sessionStorage.setItem("battle-royale-sound-off", "1");
  const first = render(
    syncedAt(cueOf(0, 0, 3), { onSettled: off, finishing: true }),
  );
  await settle();
  expect(off).toHaveBeenCalledTimes(1);
  first.unmount();
  sessionStorage.clear();

  const held = vi.fn();
  render(
    syncedAt(cueOf(0, 0, 3), { onSettled: held, finishing: true, hold: true }),
  );
  await settle();
  expect(held).toHaveBeenCalledTimes(1);
});

test("finishing: the viewer switching the sound off settles it too (#601)", async () => {
  fakeClock();
  try {
    const onSettled = vi.fn();
    const view = render(syncedAt(cueOf(0, 0, 3), { onSettled }));
    playingNow(voiceTrack());
    await settle();
    view.rerender(syncedAt(cueOf(0, 0, 3), { onSettled, finishing: true }));
    fireEvent.click(screen.getByRole("button", { name: "Sound on" }));
    expect(onSettled).toHaveBeenCalledTimes(1);
  } finally {
    vi.useRealTimers();
  }
});

test("a replay (no moment) cancels the stop timer and stops the old lines (#601)", async () => {
  fakeClock();
  try {
    const view = render(syncedAt(cueOf(5, 2, 4)));
    const voice = playingNow(voiceTrack());
    await settle();
    view.rerender(syncedAt(null)); // Replay: the fight starts over
    expect(pause).toHaveBeenCalledTimes(1); // the old lines end with it
    voice.currentTime = 4;
    act(() => vi.advanceTimersByTime(10_000));
    expect(pause).toHaveBeenCalledTimes(1); // the old timer did nothing later
  } finally {
    vi.useRealTimers();
  }
});

test("finishing: a backlog of lines is said in full, because the wait covers all the speech lined up (#601)", async () => {
  fakeClock();
  try {
    const onSettled = vi.fn();
    // Three 4 s moments pile up (12 s of speech, more than the 8 s of slack), as after a fast replay.
    const view = render(syncedAt(cueOf(0, 0, 4), { onSettled }));
    const voice = playingNow(voiceTrack());
    await settle();
    view.rerender(syncedAt(cueOf(1, 5, 9), { onSettled }));
    await settle();
    view.rerender(syncedAt(cueOf(2, 10, 14), { onSettled }));
    await settle();
    view.rerender(syncedAt(cueOf(2, 10, 14), { onSettled, finishing: true }));
    expect(onSettled).not.toHaveBeenCalled();
    voice.currentTime = 4;
    act(() => vi.advanceTimersByTime(4000)); // the first moment ends; the second starts
    await settle();
    expect(onSettled).not.toHaveBeenCalled();
    voice.currentTime = 9;
    act(() => vi.advanceTimersByTime(4000)); // the second ends; the third starts: 8 s in, still going
    await settle();
    expect(onSettled).not.toHaveBeenCalled();
    voice.currentTime = 14;
    act(() => vi.advanceTimersByTime(4000)); // the closing lines are said: now it settles
    expect(onSettled).toHaveBeenCalledTimes(1);
  } finally {
    vi.useRealTimers();
  }
});

test("finishing: a slow voice that keeps moving gets the slack again each time it moves on (#601)", async () => {
  fakeClock();
  try {
    const onSettled = vi.fn();
    const view = render(syncedAt(cueOf(0, 0, 4), { onSettled }));
    const voice = playingNow(voiceTrack());
    await settle();
    view.rerender(syncedAt(cueOf(1, 5, 9), { onSettled }));
    await settle();
    // 8 s of speech are lined up, so the first wait is 8 s + the 8 s of slack = 16 s.
    view.rerender(syncedAt(cueOf(1, 5, 9), { onSettled, finishing: true }));
    act(() => vi.advanceTimersByTime(10_000)); // the voice is slow: the first lines are not done yet
    voice.currentTime = 4;
    act(() => vi.advanceTimersByTime(2000)); // t = 12 s: they end, and the second moment starts
    await settle();
    expect(voice.currentTime).toBe(5);
    voice.currentTime = 6;
    act(() => vi.advanceTimersByTime(5000)); // t = 17 s: past the first 16 s, but the voice moved on
    expect(onSettled).not.toHaveBeenCalled();
    voice.currentTime = 9;
    act(() => vi.advanceTimersByTime(3000)); // the closing lines are said: now it settles
    expect(onSettled).toHaveBeenCalledTimes(1);
  } finally {
    vi.useRealTimers();
  }
});

test("finishing: holding the fight (5x or 10x) during the wait settles at once, not after the full wait (#601)", async () => {
  fakeClock();
  try {
    const onSettled = vi.fn();
    const view = render(syncedAt(cueOf(0, 0, 4), { onSettled }));
    playingNow(voiceTrack());
    await settle();
    view.rerender(syncedAt(cueOf(0, 0, 4), { onSettled, finishing: true }));
    expect(onSettled).not.toHaveBeenCalled(); // still talking
    view.rerender(
      syncedAt(cueOf(0, 0, 4), { onSettled, finishing: true, hold: true }),
    );
    expect(onSettled).toHaveBeenCalledTimes(1); // the viewer sped it up: nothing left to wait for
  } finally {
    vi.useRealTimers();
  }
});

test("a replay forgets the old lines, so releasing the hold afterwards does not resume them (#601)", async () => {
  fakeClock();
  try {
    let paused = false;
    pause.mockImplementation(() => {
      paused = true;
    });
    const view = render(syncedAt(cueOf(5, 2, 4)));
    const voice = voiceTrack();
    Object.defineProperty(voice, "paused", {
      configurable: true,
      get: () => paused,
    });
    await settle(); // the lines start
    play.mockClear();
    view.rerender(syncedAt(null)); // Replay: the fight starts over, the old lines stop
    view.rerender(syncedAt(null, { hold: true })); // the stage reloads and is not moving yet
    view.rerender(syncedAt(null, { hold: false })); // the new game starts playing
    await settle();
    expect(play).not.toHaveBeenCalled(); // the old closing line does not come back
  } finally {
    vi.useRealTimers();
  }
});

test("finishing: changing the speed during the wait works the wait out again (#601)", async () => {
  fakeClock();
  try {
    const onSettled = vi.fn();
    const view = render(syncedAt(cueOf(0, 0, 4), { onSettled, rate: 2 }));
    playingNow(voiceTrack());
    await settle();
    view.rerender(
      syncedAt(cueOf(0, 0, 4), { onSettled, rate: 2, finishing: true }),
    );
    // At 2x the 4 s of speech take 2 s, so the wait is 2 s + the 8 s of slack.
    act(() => vi.advanceTimersByTime(5000));
    expect(onSettled).not.toHaveBeenCalled();
    view.rerender(
      syncedAt(cueOf(0, 0, 4), { onSettled, rate: 1, finishing: true }),
    );
    // At 1x the speech takes 4 s: the wait starts over at 4 s + 8 s = 12 s, so it is not over at 10 s.
    act(() => vi.advanceTimersByTime(11_900));
    expect(onSettled).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(200));
    expect(onSettled).toHaveBeenCalledTimes(1);
  } finally {
    vi.useRealTimers();
  }
});
