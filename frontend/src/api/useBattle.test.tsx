import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import running from "../fixtures/battle-record-running.json";
import done from "../fixtures/battle-record-done.json";
import { POLL_MS, useBattle } from "./useBattle.ts";

// A stand-in EventSource that records what it opened and can fail on demand.
class FakeEventSource {
  static last: FakeEventSource | undefined;
  onmessage: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.last = this;
  }
  close() {
    this.closed = true;
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  FakeEventSource.last = undefined;
});

test("listens for live updates over Server-Sent Events", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(running)));
  const { result } = renderHook(() => useBattle("b-7f3k2q"));
  await waitFor(() => expect(result.current.battle?.status).toBe("running"));
  await waitFor(() =>
    expect(FakeEventSource.last?.url).toBe("/api/battles/b-7f3k2q/events"),
  );
});

test("falls back to polling every second when the live connection fails", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal("EventSource", FakeEventSource);
  const fetchMock = vi
    .fn()
    .mockImplementationOnce(() => Promise.resolve(Response.json(running)))
    .mockImplementationOnce(() => Promise.resolve(Response.json(running)))
    .mockImplementation(() => Promise.resolve(Response.json(done)));
  vi.stubGlobal("fetch", fetchMock);

  const { result } = renderHook(() => useBattle("b-7f3k2q"));
  await waitFor(() => expect(FakeEventSource.last).toBeDefined());

  FakeEventSource.last!.onerror!();
  expect(FakeEventSource.last!.closed).toBe(true);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

  await vi.advanceTimersByTimeAsync(POLL_MS);
  await waitFor(() => expect(result.current.battle?.status).toBe("done"));
  expect(fetchMock).toHaveBeenCalledTimes(3);

  await vi.advanceTimersByTimeAsync(POLL_MS * 3);
  expect(fetchMock).toHaveBeenCalledTimes(3); // stops once the battle is done
});
