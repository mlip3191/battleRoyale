// Tests for the doctor's .env step and its commit-guard step (#598), using a decoy settings file in a temp folder (never the real .env).
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { envStep, guardStep } from "./setup-check.mjs";

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

// A stand-in for the git command that records each call and answers from the given settings.
function fakeGit({ hooksPath = "", setOk = true } = {}) {
  const calls = [];
  const git = (args) => {
    calls.push(args);
    if (args.length === 2) return { ok: true, out: hooksPath };
    return { ok: setOk, out: "" };
  };
  return { git, calls };
}

test("guard step skips a ZIP copy without failing or asking git (#598)", () => {
  const zip = mkdtempSync(join(tmpdir(), "doctor-zip-"));
  const { git, calls } = fakeGit();
  const r = guardStep({ dir: zip, git });
  assert.equal(r.status, "ok");
  assert.match(r.label, /skipped/);
  assert.equal(r.fix, undefined);
  assert.doesNotMatch(printed(r), /npm run setup/);
  assert.deepEqual(calls, []);
});

test("guard step never touches an outer checkout when a ZIP is unzipped inside it (#598)", () => {
  const outer = mkdtempSync(join(tmpdir(), "doctor-outer-"));
  mkdirSync(join(outer, ".git"));
  const zip = join(outer, "battleRoyale-main");
  mkdirSync(zip);
  const { git, calls } = fakeGit();
  assert.equal(guardStep({ dir: zip, git }).status, "ok");
  assert.deepEqual(calls, []);
});

test("guard step in a clone passes when the guard is already on", () => {
  const clone = mkdtempSync(join(tmpdir(), "doctor-clone-"));
  mkdirSync(join(clone, ".git"));
  const { git, calls } = fakeGit({ hooksPath: ".githooks" });
  const r = guardStep({ dir: clone, git });
  assert.equal(r.status, "ok");
  assert.match(r.label, /is on/);
  assert.equal(calls.length, 1);
});

test("guard step in a clone turns the guard on when it is off, and fails with a fix if it can't", () => {
  const clone = mkdtempSync(join(tmpdir(), "doctor-clone-"));
  mkdirSync(join(clone, ".git"));
  const on = fakeGit();
  const turned = guardStep({ dir: clone, git: on.git });
  assert.equal(turned.status, "ok");
  assert.match(turned.label, /turned it on/);
  assert.deepEqual(on.calls.at(-1), ["config", "core.hooksPath", ".githooks"]);
  const stuck = guardStep({ dir: clone, git: fakeGit({ setOk: false }).git });
  assert.equal(stuck.status, "fail");
  assert.match(stuck.fix, /npm run setup/);
});

test("guard step in a worktree (a .git file) still checks the guard", () => {
  const worktree = mkdtempSync(join(tmpdir(), "doctor-worktree-"));
  writeFileSync(join(worktree, ".git"), "gitdir: ../elsewhere\n");
  const { git } = fakeGit({ hooksPath: ".githooks" });
  assert.match(guardStep({ dir: worktree, git }).label, /is on/);
});
