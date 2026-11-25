// Test helper: a tiny stand-in for the Web Audio parts the waiting room's crowd uses (jsdom has
// none). It records the nodes and every level change, so tests can check what the crowd asked for.
import { vi } from "vitest";

// A level (gain, frequency) that keeps its value and a list of what was scheduled on it.
export class FakeParam {
  value = 0;
  calls: { kind: string; value: number; at: number }[] = [];
  private note(kind: string, value: number, at: number) {
    this.value = value;
    this.calls.push({ kind, value, at });
  }
  setValueAtTime = (v: number, at: number) => this.note("set", v, at);
  linearRampToValueAtTime = (v: number, at: number) => this.note("ramp", v, at);
  setTargetAtTime = (v: number, at: number) => this.note("target", v, at);
  cancelScheduledValues = () => {};
}

// Any node: remembers where it is connected; connect returns the next node, like the real one.
class FakeNode {
  to: unknown[] = [];
  connect<T>(next: T) {
    this.to.push(next);
    return next;
  }
  disconnect() {
    this.to = [];
  }
}

class FakeSource extends FakeNode {
  buffer: { getChannelData: (channel: number) => Float32Array } | null = null;
  loop = false;
  started = false;
  stoppedAt: number | null = null;
  onended: (() => void) | null = null;
  start = () => (this.started = true);
  stop = (at = 0) => (this.stoppedAt = at);
}

export class FakeAudioContext {
  state: AudioContextState;
  currentTime = 10;
  sampleRate = 200; // small, so making the noise is quick
  destination = new FakeNode();
  sources: FakeSource[] = [];
  filters: { type: string; frequency: FakeParam; Q: FakeParam }[] = [];
  gains: (FakeNode & { gain: FakeParam })[] = [];
  allowed: boolean;
  // `allowed`: whether the browser lets this page's audio run (false keeps it suspended).
  constructor(allowed = true) {
    this.allowed = allowed;
    this.state = allowed ? "running" : "suspended";
  }
  resume = vi.fn(async () => {
    if (this.allowed) this.state = "running";
  });
  createBuffer(_channels: number, length: number) {
    const data = new Float32Array(length);
    return { getChannelData: () => data };
  }
  createBufferSource() {
    return this.add(this.sources, new FakeSource());
  }
  createBiquadFilter() {
    const filter = Object.assign(new FakeNode(), {
      type: "lowpass",
      frequency: new FakeParam(),
      Q: new FakeParam(),
    });
    return this.add(this.filters, filter);
  }
  createGain() {
    return this.add(
      this.gains,
      Object.assign(new FakeNode(), { gain: new FakeParam() }),
    );
  }
  private add<T>(list: T[], node: T) {
    list.push(node);
    return node;
  }
  // The gain that feeds the speakers: the crowd's volume and its fades.
  output = () => this.gains.find((g) => g.to.includes(this.destination));
  // Whether the crowd is playing and not fading out.
  playing = () => this.sources.some((s) => s.started && s.stoppedAt === null);
}
