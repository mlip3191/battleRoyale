// Picking why a battle was called off: only a plain-English failed-stage detail is ever shown.
import { describe, expect, test } from "vitest";
import type { StageStatus } from "../api/client.ts";
import {
  CALLED_OFF,
  calledOff,
  failureReason,
  isUsableReason,
} from "./failure-reason.ts";

const REASON =
  "We don't have a stat sheet for 'king cobra' yet. For now, pick one of our ready-made fighters.";

// A stage list where research failed with the given detail.
const failedWith = (detail: string | null): StageStatus[] => [
  { stage: "intake", status: "done", detail: null },
  { stage: "research", status: "failed", detail },
  { stage: "simulate", status: "pending", detail: null },
];

describe("isUsableReason", () => {
  test("a plain-English sentence is usable", () => {
    expect(isUsableReason(REASON)).toBe(true);
    expect(
      isUsableReason(
        "Something went wrong behind the scenes. Please try again.",
      ),
    ).toBe(true);
  });

  test.each([
    ["missing", undefined],
    ["null", null],
    ["empty", ""],
    ["whitespace only", "   \t "],
    ["the stub marker", "stub"],
    ["the stub marker, padded and capitalised", "  Stub "],
    ["a single token", "timeout"],
    ["a snake_case identifier", "research_failed"],
    ["snake_case inside a sentence", "stage research_failed after retries"],
    ["an exception name", "ValueError: bad input"],
    ["an exception class in a sentence", "raised KeyError while loading"],
    ["an Exception suffix", "ProviderException was raised"],
    ["a traceback", "Traceback (most recent call last): boom"],
    ["a multi-line message", "line one\nline two"],
    ["a module path", "failed in app.pipeline.stages for this battle"],
    ["over 300 characters", `${"a fighter ".repeat(30)}x`],
  ])("%s is not usable", (_, detail) => {
    expect(isUsableReason(detail)).toBe(false);
  });

  test("exactly 300 characters is still usable", () => {
    const text = `${"a fighter ".repeat(29)}abcdefghij`;
    expect(text).toHaveLength(300);
    expect(isUsableReason(text)).toBe(true);
  });
});

describe("failureReason", () => {
  test("returns the failed stage's detail, trimmed", () => {
    expect(failureReason(failedWith(`  ${REASON} `))).toBe(REASON);
  });

  test("ignores details on stages that did not fail", () => {
    const stages: StageStatus[] = [
      { stage: "simulate", status: "running", detail: "Running 1000 fights" },
      { stage: "script", status: "done", detail: "stub" },
    ];
    expect(failureReason(stages)).toBeNull();
  });

  test("is null when the failed stage's detail is not usable", () => {
    expect(failureReason(failedWith(null))).toBeNull();
    expect(failureReason(failedWith("stub"))).toBeNull();
    expect(failureReason(failedWith("RuntimeError"))).toBeNull();
  });

  test("skips an unusable failed stage for a usable one", () => {
    const stages: StageStatus[] = [
      { stage: "research", status: "failed", detail: "stub" },
      { stage: "simulate", status: "failed", detail: REASON },
    ];
    expect(failureReason(stages)).toBe(REASON);
  });
});

describe("calledOff", () => {
  test("shows the reason under a called-off heading", () => {
    expect(calledOff(failedWith(REASON))).toEqual({
      title: "This fight was called off",
      message: REASON,
    });
  });

  test("falls back to today's generic message", () => {
    expect(calledOff(failedWith(null))).toEqual({ message: CALLED_OFF });
    expect(calledOff([])).toEqual({ message: CALLED_OFF });
  });
});
