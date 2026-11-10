// Tests for the doctor's .env step, using a decoy settings file in a temp folder (never the real .env).
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { envStep } from "./setup-check.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const examplePath = join(here, "..", ".env.example");
const MARKER = "decoymarker7731";

// Write a settings file (named so no guard mistakes it for .env) with every example variable set to a marker value.
function decoyFile({ blank = [] } = {}) {
  const names = [...readFileSync(examplePath, "utf8").matchAll(/^([A-Z0-9_]+)\s*=/gm)].map((m) => m[1]);
  const lines = names.map((name) => {
    if (blank.includes(name)) return `${name}=`;
    if (name === "PROVIDER_MODE") return `${name}=live`;
    return name.endsWith("_URL") ? `${name}=https://${MARKER}.invalid:9000` : `${name}=${MARKER}`;
  });
  lines.push(`EXTRA_${MARKER.toUpperCase()}_API_KEY=${MARKER}`);
  const path = join(mkdtempSync(join(tmpdir(), "doctor-test-")), "settings-under-test.txt");
  writeFileSync(path, lines.join("\n") + "\n");
  return { path, names };
}

// Everything the step would print, as one string.
const printed = (r) => [r.label, r.fix ?? "", ...(r.detail ?? [])].join("\n");

test("env step passes on a complete decoy file and never prints the marker", () => {
  const { path } = decoyFile();
  const r = envStep({ envPath: path, examplePath });
  assert.equal(r.status, "ok");
  assert.ok(!printed(r).includes(MARKER), "marker value leaked into output");
});

test("env step fails with a fix when a required value is blank, still without the marker", () => {
  const required = [...readFileSync(examplePath, "utf8").matchAll(/\[required\][^\n]*\n([A-Z0-9_]+)\s*=/g)].map((m) => m[1]);
  assert.ok(required.length > 0, ".env.example has no [required] variables to test with");
  const { path } = decoyFile({ blank: [required[0]] });
  const r = envStep({ envPath: path, examplePath });
  assert.equal(r.status, "fail");
  assert.match(r.fix, /npm run env:setup/);
  assert.ok(r.detail.some((l) => l.includes(required[0]) && l.includes("EMPTY")));
  assert.ok(!printed(r).includes(MARKER), "marker value leaked into output");
});

test("env step fails with a fix when the settings file does not exist", () => {
  const missing = join(mkdtempSync(join(tmpdir(), "doctor-test-")), "nothing-here.txt");
  const r = envStep({ envPath: missing, examplePath });
  assert.equal(r.status, "fail");
  assert.match(r.fix, /npm run env:setup/);
});
