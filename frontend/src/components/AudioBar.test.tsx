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
  localStorage.clear();
  vi.restoreAllMocks();
  play.mockClear();
  pause.mockClear();
});

const tracks = () => Array.from(document.querySelectorAll("audio"));

test("no tracks: no controls at all", () => {
  const { container } = render(<AudioBar narration={null} music={null} />);
  expect(container.innerHTML).toBe("");
});

test("nothing plays on its own; Sound off starts both tracks and Pause stops them", async () => {
  render(<AudioBar narration="/media/a.mp3" music="/media/m.mp3" />);
  expect(play).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Sound off" }));
  fireEvent.click(await screen.findByRole("button", { name: "Sound on" }));
  expect(play).toHaveBeenCalledTimes(2);
  expect(pause).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button", { name: "Sound off" })).toBeTruthy();
});

test("the browser refusing to play: no error, and the button stays on Sound off", async () => {
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
  expect(localStorage.getItem("battle-royale-sound-off")).toBeNull();
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
