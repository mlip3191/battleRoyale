#!/usr/bin/env node
// PostToolUse hook for Edit and Write.
// Formats the edited file: ruff for .py, prettier for files under frontend/.
// Skips quietly when the formatter isn't installed yet; never blocks.
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

// Read all of stdin as text.
async function readStdin() {
  let data = "";
  for await (const chunk of process.stdin) data += chunk;
  return data;
}

// Run a formatter, ignoring any failure (formatting is a convenience, not a guard).
function run(cmd, args, cwd) {
  try {
    execFileSync(cmd, args, { cwd, stdio: "ignore", timeout: 30_000 });
  } catch {
    // formatter missing or failed: leave the file as written
  }
}

try {
  const input = JSON.parse(await readStdin());
  const file = input?.tool_input?.file_path;
  const root = process.env.CLAUDE_PROJECT_DIR || input?.cwd || process.cwd();
  if (typeof file === "string" && existsSync(file)) {
    const rel = path.relative(root, path.resolve(root, file)).split(path.sep).join("/");
    const backend = path.join(root, "backend");
    const prettier = path.join(root, "frontend", "node_modules", "prettier", "bin", "prettier.cjs");
    if (rel.endsWith(".py") && existsSync(path.join(backend, "pyproject.toml"))) {
      run("uv", ["run", "--directory", backend, "ruff", "format", path.resolve(root, file)], root);
    } else if (rel.startsWith("frontend/") && !rel.includes("node_modules/") && existsSync(prettier)) {
      run(process.execPath, [prettier, "--write", "--ignore-unknown", path.resolve(root, file)], path.join(root, "frontend"));
    }
  }
} catch {
  // malformed input: nothing to format
}
process.exit(0);
