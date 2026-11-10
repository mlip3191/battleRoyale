// Tests for the env check's hints, using a path in a temp folder (never the real .env).
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { checkEnv } from "./check-env.mjs";

test("a missing settings file points people at npm run env:setup first", () => {
  const missing = join(mkdtempSync(join(tmpdir(), "check-env-test-")), "nothing-here.txt");
  const errors = [];
  const code = checkEnv({ envPath: missing, log: () => {}, error: (line) => errors.push(line) });
  assert.equal(code, 1);
  const text = errors.join("\n");
  assert.match(text, /npm run env:setup/);
  assert.ok(text.indexOf("env:setup") < text.indexOf("copy .env.example"), "env:setup should come before the by-hand route");
});
