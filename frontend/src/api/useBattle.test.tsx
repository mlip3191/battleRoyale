import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import running from "../fixtures/battle-record-running.json";
import done from "../fixtures/battle-record-done.json";
import { reset } from "./fixtures.ts";
import { NOT_FOUND, POLL_MS, RETRYING, useBattle } from "./useBattle.ts";

// A stand-in EventSource that records what it opened and lets tests fire its events.
class FakeEventSource {
  static all: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onmessage: (() => void) | null = null;
  onerror: (() => void) | null = null;
  named: Record<string, () => void> = {};
  closed = false;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.all.push(this);
  }
  addEventListener(name: string, fn: () => void) {
    this.named[name] = fn;
  }
  close() {
    this.closed = true;
  }
  static get last() {
    return FakeEventSource.all.at(-1);
  }
}

const reply = (body: unknown, status = 200) =>
  Promise.resolve(Response.json(body, { status }));
// Let pending replies and timers run, inside React's act().
const flush = (ms = 0) => act(() => vi.advanceTimersByTimeAsync(ms));

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.useRealTimers();
  FakeEventSource.all = [];
});

test("listens for live updates and refetches on open, unnamed, and named events", async () => {
  const fetchMock = vi.fn(() => reply(running));
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useBattle("b-7f3k2q"));
  await flush();
  expect(result.current.battle?.status).toBe("running");
  const source = FakeEventSource.last!;
  expect(source.url).toBe("/api/battles/b-7f3k2q/events");

  source.onopen!();
  await flush();
  source.onmessage!();
  await flush();
  source.named.stage();
  await flush();
  expect(fetchMock).toHaveBeenCalledTimes(4);
});

test("closes the stream once an update says the battle is done", async () => {
  const fetchMock = vi.fn(() => reply(running));
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useBattle("b-7f3k2q"));
  await flush();
  fetchMock.mockImplementation(() => reply(done));
  FakeEventSource.last!.named.end();
  await flush();
  expect(result.current.battle?.status).toBe("done");
  expect(FakeEventSource.last!.closed).toBe(true);
});

test("ignores a reply older than the one already shown", async () => {
  const slow: Array<(r: Response) => void> = [];
  const fetchMock = vi
    .fn()
    .mockImplementationOnce(() => reply(running))
    .mockImplementation(
      () => new Promise<Response>((resolve) => slow.push(resolve)),
    );
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useBattle("b-7f3k2q"));
  await flush();

  FakeEventSource.last!.onmessage!(); // request 2 (will answer "running", late)
  FakeEventSource.last!.onmessage!(); // request 3 (answers "done" first)
  await flush();
  slow[1](Response.json(done));
  await flush();
  slow[0](Response.json(running));
  await flush();
  expect(result.current.battle?.status).toBe("done");
});

test("falls back to polling every second when the live connection fails", async () => {
  const fetchMock = vi
    .fn()
    .mockImplementationOnce(() => reply(running))
    .mockImplementationOnce(() => reply(running))
    .mockImplementation(() => reply(done));
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useBattle("b-7f3k2q"));
  await flush();

  FakeEventSource.last!.onerror!();
  expect(FakeEventSource.last!.closed).toBe(true);
  await flush();
  expect(fetchMock).toHaveBeenCalledTimes(2);

  await flush(POLL_MS);
  expect(result.current.battle?.status).toBe("done");
  expect(fetchMock).toHaveBeenCalledTimes(3);

  await flush(POLL_MS * 3);
  expect(fetchMock).toHaveBeenCalledTimes(3); // stops once the battle is done
});

test("a failed fetch while streaming says Retrying and really retries by polling", async () => {
  const fetchMock = vi
    .fn()
    .mockImplementationOnce(() => reply(running))
    .mockImplementationOnce(() => reply({}, 500))
    .mockImplementation(() => reply(running));
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useBattle("b-7f3k2q"));
  await flush();
  FakeEventSource.last!.onmessage!();
  await flush();
  expect(result.current.battle?.status).toBe("running"); // keeps the last good record
  expect(FakeEventSource.last!.closed).toBe(true);
  expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3); // polling started
  expect(result.current.error).toBeNull(); // the retry already succeeded

  fetchMock.mockImplementation(() => reply({}, 500));
  await flush(POLL_MS);
  expect(result.current.error).toBe(RETRYING);
  const calls = fetchMock.mock.calls.length;
  await flush(POLL_MS);
  expect(fetchMock.mock.calls.length).toBe(calls + 1); // still retrying
});

test("an unknown battle shows not-found and stops trying", async () => {
  const fetchMock = vi.fn(() => reply({ detail: "not found" }, 404));
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useBattle("nope"));
  await flush();
  expect(result.current.error).toBe(NOT_FOUND);
  await flush(POLL_MS * 5);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(FakeEventSource.all).toHaveLength(0);
});

test("unmounting closes the stream and stops polling", async () => {
  const fetchMock = vi.fn(() => reply(running));
  vi.stubGlobal("fetch", fetchMock);
  const { unmount } = renderHook(() => useBattle("b-7f3k2q"));
  await flush();
  FakeEventSource.last!.onerror!(); // now polling
  await flush();
  const calls = fetchMock.mock.calls.length;
  unmount();
  expect(FakeEventSource.last!.closed).toBe(true);
  await flush(POLL_MS * 5);
  expect(fetchMock).toHaveBeenCalledTimes(calls);
});

test("changing the id closes the old stream, opens a new one, and never shows the old battle", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => reply(running)),
  );
  const { result, rerender } = renderHook(({ id }) => useBattle(id), {
    initialProps: { id: "first" },
  });
  await flush();
  const first = FakeEventSource.last!;

  rerender({ id: "second" });
  expect(result.current.battle).toBeNull();
  expect(first.closed).toBe(true);
  await flush();
  expect(FakeEventSource.last!.url).toBe("/api/battles/second/events");
});

test("fixtures mode polls without opening a stream and finishes in about 10 seconds", async () => {
  vi.stubEnv("VITE_USE_FIXTURES", "true");
  reset();
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useBattle("demo"));
  await flush(300);
  expect(result.current.battle?.status).toBe("running");
  await flush(11_000);
  expect(result.current.battle?.status).toBe("done");
  expect(FakeEventSource.all).toHaveLength(0);
  expect(fetchMock).not.toHaveBeenCalled();
});
