#!/usr/bin/env node
// npm run doctor: checks that this computer is ready to work on Battle Royale, with a plain-English fix for each problem.
// Runs the same on Windows and Mac. Never prints .env values.

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { checkEnv } from "./check-env.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const isWindows = process.platform === "win32";

// Run a fixed command (no user input) and return its exit code and trimmed output.
function sh(command, args = []) {
  const r = spawnSync(command, args, { cwd: root, encoding: "utf8", shell: isWindows });
  return { ok: r.status === 0, out: `${r.stdout ?? ""}${r.stderr ?? ""}`.trim() };
}

// First line of a command's --version output, or null if the command isn't installed.
function version(command) {
  const r = sh(command, ["--version"]);
  return r.ok ? r.out.split(/\r?\n/)[0] : null;
}

// Pick the install hint for this operating system.
const os = (windows, mac) => (isWindows ? windows : mac);

// Each check returns { status: "ok" | "warn" | "fail", label, fix? }.
const checks = [
  () => {
    const v = version("git");
    return v
      ? { status: "ok", label: v }
      : { status: "fail", label: "Git is not installed", fix: os("Install Git for Windows: https://git-scm.com/download/win", "Run: xcode-select --install") };
  },
  () => {
    if (!version("gh")) {
      return { status: "fail", label: "GitHub CLI (gh) is not installed", fix: os("Run: winget install GitHub.cli", "Run: brew install gh") + "  Then: gh auth login" };
    }
    return sh("gh", ["auth", "status"]).ok
      ? { status: "ok", label: "GitHub CLI is logged in" }
      : { status: "fail", label: "GitHub CLI is not logged in", fix: "Run: gh auth login  (choose GitHub.com, HTTPS, and log in with a web browser)" };
  },
  () => {
    const v = version("claude");
    return v
      ? { status: "ok", label: `Claude Code ${v}` }
      : {
          status: "warn",
          label: "Claude Code command-line tool not found",
          fix: "Fine if you use Claude Code in the Claude desktop app. To use it in a terminal too, see https://docs.claude.com/en/docs/claude-code/setup",
        };
  },
  () => {
    const want = readFileSync(join(root, ".nvmrc"), "utf8").trim().replace(/^v/, "");
    const have = process.versions.node;
    return have.split(".")[0] === want.split(".")[0]
      ? { status: "ok", label: `Node ${have}` }
      : {
          status: "fail",
          label: `Node ${have}, but this project needs Node ${want}`,
          fix: `Install Node ${want} (LTS) from https://nodejs.org, then close and reopen your terminal. With fnm: fnm install ${want} && fnm use ${want}`,
        };
  },
  () => {
    const v = version("uv");
    return v
      ? { status: "ok", label: v }
      : { status: "fail", label: "uv is not installed", fix: os("Run: winget install astral-sh.uv", "Run: brew install uv") + "  Then close and reopen your terminal." };
  },
  () => {
    const v = version("gitleaks");
    return v
      ? { status: "ok", label: `gitleaks ${v}` }
      : {
          status: "warn",
          label: "gitleaks (optional secret scanner) is not installed",
          fix: `The commit guard still works without it (DECISIONS D-08). To install: ${os("winget install gitleaks", "brew install gitleaks")}`,
        };
  },
  () => {
    const name = sh("git", ["config", "user.name"]);
    const email = sh("git", ["config", "user.email"]);
    return name.ok && email.ok && name.out && email.out
      ? { status: "ok", label: "Git name and email are set" }
      : {
          status: "fail",
          label: "Git doesn't know your name and email",
          fix: 'Run: git config --global user.name "Your Name"  and  git config --global user.email "you@example.com"  (use your GitHub email)',
        };
  },
  () => {
    if (sh("git", ["config", "core.hooksPath"]).out === ".githooks") {
      return { status: "ok", label: "Secret guard (commit hook) is on" };
    }
    return sh("git", ["config", "core.hooksPath", ".githooks"]).ok
      ? { status: "ok", label: "Secret guard (commit hook) was off, so I turned it on" }
      : { status: "fail", label: "Couldn't turn on the secret guard", fix: "Run: npm run setup  (it turns the guard on)" };
  },
  () => envStep(),
  () => {
    const r = sh("git", ["ls-files", "--cached", "--ignored", "--exclude-standard"]);
    return r.ok && r.out === ""
      ? { status: "ok", label: "No ignored files are committed" }
      : {
          status: "fail",
          label: "Some files that should never be committed are tracked by Git",
          fix: "Tell Mike before doing anything else. Run: git ls-files --cached --ignored --exclude-standard  to see which ones.",
        };
  },
];

// The .env part of the doctor: reuses check-env, keeps only its status lines, and never prints values.
export function envStep({ envPath, examplePath } = {}) {
  const lines = [];
  const capture = (msg = "") => lines.push(...String(msg).split("\n"));
  const code = checkEnv({ envPath, examplePath, log: capture, error: capture });
  const detail = lines.filter((l) => /^\s+(ok|--|!!) /.test(l) || l.startsWith("In .env but not"));
  return code === 0
    ? { status: "ok", label: ".env has every required value", detail }
    : {
        status: "fail",
        label: ".env is missing or incomplete",
        detail,
        fix: "In your own terminal (never in a chat), run: npm run env:setup  Then check with: npm run env:check",
      };
}

// Run every check, print the checklist, and return 0 when nothing failed.
export function runDoctor(log = console.log) {
  const marks = { ok: "  ok ", warn: "  -- ", fail: "  !! " };
  log("Battle Royale setup check\n");
  let failed = 0;
  for (const check of checks) {
    const r = check();
    log(`${marks[r.status]}${r.label}`);
    for (const d of r.detail ?? []) if (r.status !== "ok") log(`      ${d.trim()}`);
    if (r.fix) log(`      Fix: ${r.fix}`);
    if (r.status === "fail") failed++;
  }
  log(failed ? `\n${failed} thing(s) to fix. Fix them, then run npm run doctor again.` : "\nAll set. You're ready to work.");
  return failed ? 1 : 0;
}

// Run as a command only when called directly (not when imported by tests).
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(runDoctor());
}
