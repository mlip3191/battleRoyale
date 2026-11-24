// Tests for setup's last step, which turns on the commit guard only in a git checkout (#597).
// Folders are made in a temp directory; git itself is never run on a real checkout here.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { SKIPPED, setHooks } from "./git-hooks.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const tempDir = () => mkdtempSync(join(tmpdir(), "git-hooks-test-"));

// A stand-in for spawnSync that records each call and answers with the given exit code.
function fakeRun(status = 0) {
  const calls = [];
  const run = (command, args, options) => {
    calls.push({ command, args, cwd: options?.cwd });
    return { status };
  };
  return { run, calls };
}

test("a ZIP copy finishes setup with a note instead of a git error (#597)", () => {
  const zip = join(tempDir(), "battleRoyale-main");
  mkdirSync(join(zip, "scripts"), { recursive: true });
  copyFileSync(join(here, "git-hooks.mjs"), join(zip, "scripts", "git-hooks.mjs"));
  const r = spawnSync(process.execPath, [join("scripts", "git-hooks.mjs")], { cwd: zip, encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /Not a git checkout/);
  assert.doesNotMatch(`${r.stdout}${r.stderr}`, /fatal/);
});

test("a ZIP unzipped inside another checkout never touches that checkout's git settings", () => {
  const outer = tempDir();
  mkdirSync(join(outer, ".git"));
  const zip = join(outer, "battleRoyale-main");
  mkdirSync(zip);
  const { run, calls } = fakeRun();
  const notes = [];
  assert.equal(setHooks(zip, run, (line) => notes.push(line)), 0);
  assert.deepEqual(calls, []);
  assert.deepEqual(notes, [SKIPPED]);
});

test("a clone turns the commit guard on", () => {
  const clone = tempDir();
  mkdirSync(join(clone, ".git"));
  const { run, calls } = fakeRun();
  assert.equal(setHooks(clone, run, () => {}), 0);
  assert.deepEqual(calls, [{ command: "git", args: ["config", "core.hooksPath", ".githooks"], cwd: clone }]);
});

test("a git worktree, whose .git is a file, turns the commit guard on", () => {
  const worktree = tempDir();
  writeFileSync(join(worktree, ".git"), "gitdir: /somewhere/else\n");
  const { run, calls } = fakeRun();
  assert.equal(setHooks(worktree, run, () => {}), 0);
  assert.equal(calls.length, 1);
});

test("a git error inside a checkout still fails setup, and says so when git is missing", () => {
  const clone = tempDir();
  mkdirSync(join(clone, ".git"));
  assert.equal(setHooks(clone, fakeRun(128).run, () => {}), 128);
  const notes = [];
  const missingGit = () => ({ status: null, error: new Error("spawn git ENOENT") });
  assert.equal(setHooks(clone, missingGit, (line) => notes.push(line)), 1);
  assert.match(notes.join("\n"), /Couldn't run git.*ENOENT/);
});

// Copy the step into a folder laid out like the repo, so running it there acts on that folder.
function withScript(dir) {
  mkdirSync(join(dir, "scripts"), { recursive: true });
  copyFileSync(join(here, "git-hooks.mjs"), join(dir, "scripts", "git-hooks.mjs"));
  return dir;
}
const git = (dir, ...args) => spawnSync("git", ["-C", dir, ...args], { encoding: "utf8" });
const hooksPath = (dir) => git(dir, "config", "--local", "core.hooksPath").stdout.trim();

test("in a real clone reached through a symlink or junction, setup still turns the guard on", () => {
  const repo = withScript(join(tempDir(), "repo"));
  assert.equal(git(repo, "init", "-q").status, 0);
  const link = join(tempDir(), "link");
  symlinkSync(repo, link, "junction");
  const r = spawnSync(process.execPath, [join(link, "scripts", "git-hooks.mjs")], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  assert.equal(hooksPath(repo), ".githooks");
});

test("a real ZIP copy inside a real checkout leaves that checkout's settings alone", () => {
  const outer = tempDir();
  assert.equal(git(outer, "init", "-q").status, 0);
  const zip = withScript(join(outer, "battleRoyale-main"));
  const r = spawnSync(process.execPath, [join("scripts", "git-hooks.mjs")], { cwd: zip, encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /Not a git checkout/);
  assert.equal(hooksPath(outer), "");
});
