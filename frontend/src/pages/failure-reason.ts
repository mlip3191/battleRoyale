// Why a battle was called off, for the Battle and Results pages (#206). The backend puts a
// plain-English reason in the failed stage's `detail`; anything that isn't one is never shown.
import type { StageStatus } from "../api/client.ts";

// Today's message, kept for a failed battle with no usable reason.
export const CALLED_OFF = "This fight was called off. Try another matchup.";

// Longest reason we show; matches how the API client caps an error's detail.
const MAX_REASON = 300;

// Text that reads like code, not a sentence: snake_case, exception names, tracebacks, module paths.
const CODE_STYLE = [
  /\w_\w/,
  /\b[A-Z]\w*(Error|Exception)\b/,
  /Traceback/,
  /\b[a-z_]+\.[a-z_]+\.[a-z_]+\b/,
  /[\r\n]/,
];

// Whether a stage detail is a plain-English sentence we can show the viewer.
export function isUsableReason(detail: string | null | undefined): boolean {
  if (typeof detail !== "string") return false;
  const text = detail.trim();
  if (!text || detail.length > MAX_REASON) return false;
  if (text.toLowerCase() === "stub") return false;
  if (!/\s/.test(text)) return false; // a single token, e.g. "stub" or "timeout"
  return !CODE_STYLE.some((pattern) => pattern.test(text));
}

// The first failed stage's usable reason, or null when there isn't one.
export function failureReason(stages: readonly StageStatus[]): string | null {
  const failed = stages.find(
    (s) => s.status === "failed" && isUsableReason(s.detail),
  );
  return failed?.detail ? failed.detail.trim() : null;
}

// What the "called off" alert says: the reason under a "called off" heading, else today's message.
export function calledOff(stages: readonly StageStatus[]): {
  title?: string;
  message: string;
} {
  const reason = failureReason(stages);
  return reason
    ? { title: "This fight was called off", message: reason }
    : { message: CALLED_OFF };
}
