// The waiting room's crowd (#592): how the sound is made, and when the bar plays and stops it.
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { savedOff, saveOff } from "./AudioBar.tsx";
import CrowdBar from "./CrowdBar.tsx";
import {
  BAND_HZ,
  CROWD_LEVEL,
  FADE_S,
  setContextMaker,
  startCrowd,
  wakeCrowd,
} from "./crowd-bed.ts";
import { FakeAudioContext } from "./fake-audio-context.ts";

let fake: FakeAudioContext;
const maker = vi.fn(() => fake as unknown as AudioContext);
beforeEach(() => {
  fake = new FakeAudioContext();
  setContextMaker(maker);
});
afterEach(() => {
  cleanup();
  setContextMaker();
  sessionStorage.clear();
  maker.mockClear();
  vi.useRealTimers();
});

const settle = () => act(() => Promise.resolve()); // let the audio wake up
const button = (name: string) => screen.getByRole("button", { name });
// The crowd fades out from now, over FADE_S, and stops there.
const fadedOut = () => {
  expect(fake.sources[0].stoppedAt).toBe(fake.currentTime + FADE_S);
  expect(fake.output()?.gain.calls.at(-1)).toMatchObject({
    kind: "ramp",
    value: 0,
  });
};

test("the sound: looped pink noise through a 300-1500 Hz band, fading in to a low level", () => {
  startCrowd(fake as unknown as AudioContext);
  const [source] = fake.sources;
  const noise = source.buffer!.getChannelData(0);
  expect(source.loop && source.started).toBe(true);
  expect(Math.max(...noise.map(Math.abs))).toBeCloseTo(1); // scaled to a peak of 1
  const [band] = fake.filters;
  expect(band.type).toBe("bandpass");
  expect(band.frequency.value).toBeGreaterThan(BAND_HZ[0]);
  expect(band.frequency.value).toBeLessThan(BAND_HZ[1]);
  expect(fake.output()?.gain.calls).toEqual([
    { kind: "set", value: 0, at: fake.currentTime },
    { kind: "ramp", value: CROWD_LEVEL, at: fake.currentTime + FADE_S },
  ]);
  // Its swells peak near -30 dBFS: quiet, some 10 dB under the announcer.
  expect(CROWD_LEVEL).toBeLessThanOrEqual(0.3);
});

test("the crowd swells at random, and stops swelling once it fades out", () => {
  vi.useFakeTimers();
  const bed = startCrowd(fake as unknown as AudioContext);
  vi.advanceTimersByTime(20_000);
  const swell = fake.gains.find((g) => g !== fake.output())!.gain;
  const levels = new Set(swell.calls.map((c) => c.value));
  expect(levels.size).toBeGreaterThan(3);
  bed.stop();
  fadedOut();
  const swells = swell.calls.length;
  vi.advanceTimersByTime(20_000);
  expect(swell.calls.length).toBe(swells);
});

test("once a click woke the audio, it plays (no slider: one level); Sound off fades it out for the visit", async () => {
  wakeCrowd(); // the home card's "Start the fight!" click
  render(<CrowdBar />);
  await settle();
  expect(fake.playing()).toBe(true);
  expect(fake.output()?.gain.calls[1].value).toBe(CROWD_LEVEL);
  expect(screen.queryByRole("slider")).toBeNull();
  fireEvent.click(button("Sound on"));
  fadedOut();
  expect(savedOff()).toBe(true);
  expect(button("Sound off")).toBeTruthy();
});

test("sound switched off this visit: silent until Sound on, which starts it", async () => {
  saveOff(true);
  wakeCrowd();
  render(<CrowdBar />);
  await settle();
  expect(fake.sources).toHaveLength(0);
  fireEvent.click(button("Sound off"));
  await settle();
  expect(fake.playing()).toBe(true);
  expect(savedOff()).toBe(false);
});

test("no click woke the audio (a direct link): silent until Sound on wakes it", async () => {
  render(<CrowdBar />);
  await settle();
  expect(maker).not.toHaveBeenCalled();
  fireEvent.click(button("Sound off"));
  await settle();
  expect(maker).toHaveBeenCalledTimes(1);
  expect(fake.playing()).toBe(true);
});

test("a browser that keeps the audio suspended: silent, no error, the button stays on Sound off", async () => {
  fake = new FakeAudioContext(false);
  wakeCrowd();
  render(<CrowdBar />);
  fireEvent.click(button("Sound off"));
  await settle();
  expect(fake.resume).toHaveBeenCalled();
  expect(fake.sources).toHaveLength(0);
  expect(button("Sound off")).toBeTruthy();
});

test("leaving the wait (the bar goes away) fades the crowd out", async () => {
  wakeCrowd();
  const { unmount } = render(<CrowdBar />);
  await settle();
  unmount();
  fadedOut();
});

test("a second click wakes the same audio again instead of making more", () => {
  wakeCrowd();
  wakeCrowd();
  expect(maker).toHaveBeenCalledTimes(1);
  expect(fake.resume).toHaveBeenCalledTimes(2);
});
