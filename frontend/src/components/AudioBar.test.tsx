// The sound controls: nothing plays until asked; play/pause, mute, and volume reach every track.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import AudioBar from "./AudioBar.tsx";

// jsdom has no media playback; record what the bar asks for instead.
const play = vi.fn(() => Promise.resolve());
const pause = vi.fn();
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(play);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(pause);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  play.mockClear();
  pause.mockClear();
});

const tracks = () => Array.from(document.querySelectorAll("audio"));

test("no tracks: no controls at all", () => {
  const { container } = render(<AudioBar narration={null} music={null} />);
  expect(container.innerHTML).toBe("");
});

test("nothing plays on its own; Play sound starts both tracks and Pause stops them", async () => {
  render(<AudioBar narration="/media/a.mp3" music="/media/m.mp3" />);
  expect(play).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Play sound" }));
  fireEvent.click(await screen.findByRole("button", { name: "Pause sound" }));
  expect(play).toHaveBeenCalledTimes(2);
  expect(pause).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button", { name: "Play sound" })).toBeTruthy();
});

test("the browser refusing to play: no error, and the button stays on Play sound", async () => {
  play.mockImplementationOnce(() => Promise.reject(new Error("blocked")));
  render(<AudioBar narration="/media/a.mp3" music={null} />);
  fireEvent.click(screen.getByRole("button", { name: "Play sound" }));
  await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
  await new Promise((r) => setTimeout(r, 0)); // let the refusal settle
  expect(screen.getByRole("button", { name: "Play sound" })).toBeTruthy();
});

test("one track refused, the other playing: the button offers Pause sound", async () => {
  play.mockImplementationOnce(() => Promise.reject(new Error("blocked")));
  render(<AudioBar narration="/media/a.mp3" music="/media/m.mp3" />);
  fireEvent.click(screen.getByRole("button", { name: "Play sound" }));
  expect(
    await screen.findByRole("button", { name: "Pause sound" }),
  ).toBeTruthy();
});

test("the announcer finishing on its own puts the button back to Play sound", async () => {
  render(<AudioBar narration="/media/a.mp3" music={null} />);
  fireEvent.click(screen.getByRole("button", { name: "Play sound" }));
  await screen.findByRole("button", { name: "Pause sound" });
  fireEvent.ended(tracks()[0]);
  expect(screen.getByRole("button", { name: "Play sound" })).toBeTruthy();
});

test("the announcer finishing while the music loops on keeps Pause sound", async () => {
  render(<AudioBar narration="/media/a.mp3" music="/media/m.mp3" />);
  fireEvent.click(screen.getByRole("button", { name: "Play sound" }));
  await screen.findByRole("button", { name: "Pause sound" });
  const [voice, song] = tracks();
  Object.defineProperty(song, "paused", { value: false }); // jsdom never really plays
  fireEvent.ended(voice);
  expect(screen.getByRole("button", { name: "Pause sound" })).toBeTruthy();
});

test("leaving the page stops the sound, even for tracks that arrived after the bar", async () => {
  const view = render(<AudioBar narration={null} music={null} />);
  view.rerender(<AudioBar narration="/media/a.mp3" music="/media/m.mp3" />);
  fireEvent.click(screen.getByRole("button", { name: "Play sound" }));
  await screen.findByRole("button", { name: "Pause sound" });
  for (const t of tracks())
    Object.defineProperty(t, "paused", { value: false }); // jsdom never really plays
  pause.mockClear();
  view.unmount();
  expect(pause).toHaveBeenCalledTimes(2);
});

test("a track changing while the sound plays puts the button back to Play sound", async () => {
  const { rerender } = render(
    <AudioBar narration="/media/a.mp3" music={null} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Play sound" }));
  await screen.findByRole("button", { name: "Pause sound" });
  rerender(<AudioBar narration="/media/b.mp3" music={null} />);
  expect(screen.getByRole("button", { name: "Play sound" })).toBeTruthy();
});

test("Mute is a toggle that mutes every track", () => {
  render(<AudioBar narration="/media/a.mp3" music="/media/m.mp3" />);
  const mute = screen.getByRole("button", { name: "Mute" });
  expect(mute.getAttribute("aria-pressed")).toBe("false");
  fireEvent.click(mute);
  expect(mute.getAttribute("aria-pressed")).toBe("true");
  expect(tracks().every((t) => t.muted)).toBe(true);
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
