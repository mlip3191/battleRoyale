#!/usr/bin/env node
// Checks your .env against .env.example WITHOUT printing any values.
// Usage (from the repo root, Windows or Mac):  node scripts/check-env.mjs
// Exit code 0 = ready for live mode, 1 = something to fix.
// Other scripts (npm run doctor) import checkEnv() and pass their own paths and logger.

import { readFileSync, existsSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

// Parse KEY=value lines; remember whether the comment just above says [required].
function parse(text, trackRequired) {
  const vars = new Map();
  let required = false;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (line.startsWith("#")) {
      if (line.includes("[required]")) required = true;
      continue;
    }
    const m = line.match(/^([A-Z0-9_]+)\s*=\s*(.*)$/);
    if (m) {
      let value = m[2].trim();
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      }
      vars.set(m[1], { value, required: trackRequired && required });
    }
    if (!line.startsWith("#")) required = false;
  }
  return vars;
}

// Compare an env file with the example and report each variable's status (never its value); returns 0 or 1.
export function checkEnv({
  envPath = join(root, ".env"),
  examplePath = join(root, ".env.example"),
  log = console.log,
  error = console.error,
} = {}) {
  if (!existsSync(examplePath)) {
    error("Can't find .env.example. Run this from the repo root.");
    return 1;
  }
  if (!existsSync(envPath)) {
    error("No .env file yet.");
    error("  Easiest: run  npm run env:setup  in your own terminal (it asks for the host and key).");
    error("  By hand: copy .env.example .env (Windows) or cp .env.example .env (Mac),");
    error("           then fill in the lines marked [required].");
    error("Then run this again.");
    return 1;
  }

  const example = parse(readFileSync(examplePath, "utf8"), true);
  const env = parse(readFileSync(envPath, "utf8"), false);

  const rows = [];
  let problems = 0;
  for (const [name, { required }] of example) {
    const entry = env.get(name);
    let status;
    if (!entry) status = required ? "MISSING" : "not set (optional)";
    else if (entry.value === "") status = required ? "EMPTY" : "blank (optional)";
    else if (entry.value.includes("replace-me")) status = required ? "PLACEHOLDER" : "placeholder (optional)";
    else if (name.endsWith("_URL") && !/^https?:\/\/[^\s/:]+(:\d+)?(\/.*)?$/.test(entry.value)) status = "NOT A URL";
    else status = "ok";
    if (["MISSING", "EMPTY", "PLACEHOLDER", "NOT A URL"].includes(status)) problems++;
    rows.push([name, required ? "required" : "", status]);
  }

  const extras = [...env.keys()].filter((k) => !example.has(k) && !/_API_KEY$/.test(k));

  const w = Math.max(...rows.map((r) => r[0].length));
  log("Checking .env against .env.example (values are never shown)\n");
  for (const [name, req, status] of rows) {
    log(`${status === "ok" ? "  ok " : status.startsWith("not") || status.startsWith("blank") || status.startsWith("placeholder (") ? "  -- " : "  !! "}${name.padEnd(w)}  ${req.padEnd(8)}  ${status}`);
  }
  if (extras.length) {
    log(`\nIn .env but not in .env.example (typo?): ${extras.join(", ")}`);
  }
  const mode = env.get("PROVIDER_MODE")?.value || "mock";
  log(`\nPROVIDER_MODE is "${mode}".${mode === "mock" ? " Set it to live to use the course endpoints." : ""}`);
  if (problems) {
    log(`\n${problems} required item(s) to fix. Open .env, fill them in, and run this again.`);
    return 1;
  }
  log("\nAll required values are filled in.");
  return 0;
}

// Run as a command only when called directly (not when imported).
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(checkEnv());
}
