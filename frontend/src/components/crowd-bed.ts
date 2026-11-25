// The waiting room's crowd (#592): a quiet arena murmur until the show starts. It is made in the
// browser (Web Audio), so there is no sound file to license: pink noise through the band of
// far-off voices, with slow random swells and short fades. Browsers only let sound start from a
// click, so the clicks that start a battle ("Start the fight!", "Fight them!") and the Sound on
// button wake the page's audio; while the browser keeps it suspended, the crowd stays silent.
import { useCallback, useEffect, useRef, useState } from "react";

// Its one loudness knob: swells peak near -30 dBFS, some 10 dB under the announcer.
export const CROWD_LEVEL = 0.3;
export const FADE_S = 0.5; // fade in and fade out
export const BAND_HZ = [300, 1500] as const; // the murmur's band
const NOISE_S = 4; // seconds of noise, looped
const SWELL_MS = [1500, 3500] as const; // how often the crowd swells or settles
const SWELL_LEVELS = [0.45, 1] as const; // how far it swells
const SWELL_S = 0.6; // how gently a swell moves

type MakeContext = () => AudioContext | null;

// The browser's audio, if it has any (older Safari calls it webkitAudioContext).
const browserAudio: MakeContext = () => {
  const old = window as Window & { webkitAudioContext?: typeof AudioContext };
  const Audio = window.AudioContext ?? old.webkitAudioContext;
  return Audio ? new Audio() : null;
};

let makeContext = browserAudio;
let shared: AudioContext | null = null; // made by a click, kept for the visit

// Tests swap in a fake audio context; with no argument, the browser's again. Starts over.
export function setContextMaker(make: MakeContext = browserAudio) {
  makeContext = make;
  shared = null;
}

// Inside a click: make (or resume) the page's audio, so the crowd may play later. No sound.
export function wakeCrowd() {
  try {
    if (!shared || shared.state === "closed") shared = makeContext();
    void shared?.resume().catch(() => {});
  } catch {
    /* no Web Audio here, or it refused: the wait stays silent */
  }
}

// Whether the page's audio runs, resuming it if the browser lets it; a refusal is a no.
const running = (ctx: AudioContext) =>
  Promise.resolve()
    .then(() => (ctx.state === "running" ? undefined : ctx.resume()))
    .then(
      () => ctx.state === "running",
      () => false,
    );

// A random number between two.
const between = (
  [low, high]: readonly [number, number],
  random: () => number,
) => low + (high - low) * random();

// Seconds of pink noise (Paul Kellet's economy filter), scaled to a peak of 1, to loop.
function pinkNoise(ctx: AudioContext, random: () => number) {
  const length = Math.floor(ctx.sampleRate * NOISE_S);
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  let [b0, b1, b2, peak] = [0, 0, 0, 0];
  for (let i = 0; i < length; i++) {
    const white = random() * 2 - 1;
    b0 = 0.99765 * b0 + white * 0.099046;
    b1 = 0.963 * b1 + white * 0.2965164;
    b2 = 0.57 * b2 + white * 1.0526913;
    data[i] = b0 + b1 + b2 + white * 0.1848;
    peak = Math.max(peak, Math.abs(data[i]));
  }
  for (let i = 0; i < length; i++) data[i] /= peak || 1;
  return buffer;
}

// Keep a level where it is right now, dropping what was scheduled after.
function hold(param: AudioParam, now: number) {
  const level = param.value;
  param.cancelScheduledValues(now);
  param.setValueAtTime(level, now);
}

export interface CrowdBed {
  stop: () => void; // fade out, then let go of the sound
}

// Start the murmur, fading in to CROWD_LEVEL.
export function startCrowd(ctx: AudioContext, random = Math.random): CrowdBed {
  const source = ctx.createBufferSource();
  source.buffer = pinkNoise(ctx, random);
  source.loop = true;
  const band = ctx.createBiquadFilter();
  band.type = "bandpass";
  band.frequency.value = Math.sqrt(BAND_HZ[0] * BAND_HZ[1]); // the band's middle, ~670 Hz
  band.Q.value = band.frequency.value / (BAND_HZ[1] - BAND_HZ[0]);
  const swell = ctx.createGain();
  const out = ctx.createGain();
  source.connect(band).connect(swell).connect(out).connect(ctx.destination);
  out.gain.setValueAtTime(0, ctx.currentTime);
  out.gain.linearRampToValueAtTime(CROWD_LEVEL, ctx.currentTime + FADE_S);
  source.start();

  // Every couple of seconds the crowd swells or settles a little, at random.
  let timer: ReturnType<typeof setTimeout>;
  const swellNext = () => {
    const to = between(SWELL_LEVELS, random);
    swell.gain.setTargetAtTime(to, ctx.currentTime, SWELL_S);
    timer = setTimeout(swellNext, between(SWELL_MS, random));
  };
  swellNext();

  let stopped = false;
  return {
    stop: () => {
      if (stopped) return;
      stopped = true;
      clearTimeout(timer);
      const now = ctx.currentTime;
      hold(out.gain, now);
      out.gain.linearRampToValueAtTime(0, now + FADE_S);
      source.onended = () => out.disconnect();
      source.stop(now + FADE_S);
    },
  };
}

// Play the crowd while `on`, once a click has woken the page's audio. `playing` says whether it
// really plays; `wake` (inside a click) wakes the audio and tries again.
export function useCrowdBed(on: boolean) {
  const [playing, setPlaying] = useState(false);
  const [tries, setTries] = useState(0);
  const bed = useRef<CrowdBed | null>(null);

  // Start once the audio runs; fade out when turned off or when the bar goes away.
  useEffect(() => {
    const ctx = shared;
    if (!on || !ctx) return;
    let gone = false;
    void running(ctx).then((ok) => {
      if (gone || !ok) return;
      bed.current = startCrowd(ctx);
      setPlaying(true);
    });
    return () => {
      gone = true;
      bed.current?.stop();
      bed.current = null;
      setPlaying(false);
    };
  }, [on, tries]);

  const wake = useCallback(() => {
    wakeCrowd();
    setTries((n) => n + 1);
  }, []);
  return { playing: on && playing, wake };
}
