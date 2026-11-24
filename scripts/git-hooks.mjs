#!/usr/bin/env node
// npm run setup's last step: turns on the commit guard (.githooks blocks keys and .env files).
// A ZIP copy isn't a git checkout and doesn't need it, so setup skips it there with a note (#597).

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

export const SKIPPED =
  "Not a git checkout (a ZIP copy?), so the commit guard was skipped. It only matters for changing the code. Setup is done.";

// A clone has a .git folder here and a worktree a .git file; a ZIP has neither, even when it was
// unzipped inside another checkout (asking git would find that outer checkout and change it).
const isCheckout = (dir) => existsSync(join(dir, ".git"));

// Turn the guard on in a checkout, or say why it was skipped. Returns the exit code for setup.
export function setHooks(dir = root, run = spawnSync, log = console.log) {
  if (!isCheckout(dir)) {
    log(SKIPPED);
    return 0;
  }
  const r = run("git", ["config", "core.hooksPath", ".githooks"], { cwd: dir, stdio: "inherit" });
  return r.status ?? 1;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(setHooks());
}
