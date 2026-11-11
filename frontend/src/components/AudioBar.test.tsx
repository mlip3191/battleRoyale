// The sound controls: nothing plays until asked; play/pause, mute, and volume reach every track.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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

test("nothing plays on its own; Play sound starts both tracks and Pause stops them", () => {
  render(<AudioBar narration="/media/a.mp3" music="/media/m.mp3" />);
  expect(play).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Play sound" }));
  expect(play).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole("button", { name: "Pause sound" }));
  expect(pause).toHaveBeenCalledTimes(2);
});

test("a track the browser refuses to play stays quiet without breaking the page", async () => {
  play.mockImplementationOnce(() => Promise.reject(new Error("blocked")));
  render(<AudioBar narration="/media/a.mp3" music={null} />);
  fireEvent.click(screen.getByRole("button", { name: "Play sound" }));
  await Promise.resolve();
  expect(screen.getByRole("button", { name: "Pause sound" })).toBeTruthy();
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
