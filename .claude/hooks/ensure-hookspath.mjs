#!/usr/bin/env node
// PreToolUse hook for the Bash and PowerShell tools.
// Before any git commit, make sure core.hooksPath points at .githooks so the team's
// secret check runs. Any internal error blocks the command (exit 2): fail closed.
import { execFileSync } from "node:child_process";

// Read all of stdin as text.
async function readStdin() {
  let data = "";
  for await (const chunk of process.stdin) data += chunk;
  return data;
}

// Run git in the project folder and return its trimmed output ("" if the key is unset).
function git(dir, args) {
  try {
    return execFileSync("git", ["-C", dir, ...args], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch (err) {
    if (err.status === 1 && args[0] === "config") return "";
    throw err;
  }
}

try {
  const input = JSON.parse(await readStdin());
  const command = input?.tool_input?.command;
  if (typeof command !== "string") throw new Error("no command in tool input");
  if (/\bgit\b[^;&|\n]*\bcommit\b/.test(command)) {
    const dir = process.env.CLAUDE_PROJECT_DIR || input.cwd || process.cwd();
    if (git(dir, ["config", "core.hooksPath"]) !== ".githooks") {
      git(dir, ["config", "core.hooksPath", ".githooks"]);
      const msg = "ensure-hookspath: core.hooksPath was not .githooks; set it so the secret check runs.";
      process.stdout.write(JSON.stringify({ systemMessage: msg }));
    }
  }
  process.exit(0);
} catch (err) {
  process.stderr.write(`guard error — blocked to be safe (${err?.message ?? err})\n`);
  process.exit(2);
}
