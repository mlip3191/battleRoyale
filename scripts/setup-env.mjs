#!/usr/bin/env node
// Fills in the course endpoint settings in .env by asking for the host and API key in YOUR
// terminal. The key is typed hidden and never printed; nothing about the host or key is stored
// in the repo. Usage (from the repo root, Windows or Mac, in your own terminal window):
//   npm run env:setup
// It refuses to run without a real terminal or with command-line values, so Claude (or a
// script) can't feed it a key and the key never lands in shell history.

import { chmodSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { createInterface } from "node:readline/promises";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

// Course services by port (course endpoint list, updated 2026-09-30). Ports and model names
// aren't secret; the host and key are, so only the user's own .env ever holds them.
export const SERVICE_PORTS = {
  CHAT_LLM_URL: 9001,
  STRUCTURED_LLM_URL: 9010,
  EMBEDDINGS_URL: 9002,
  RERANK_URL: 9004,
  DOC_PARSE_URL: 9005,
  IMAGE_URL: 9006,
  TTS_URL: 9008,
  MUSIC_URL: 9007,
  STT_URL: 9009,
  MM_EMBEDDINGS_URL: 9003,
  HERMES_URL: 9000,
};
export const MODELS = {
  CHAT_LLM_MODEL: "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit",
  STRUCTURED_LLM_MODEL: "internlm/Intern-Decision-4B",
  EMBEDDINGS_MODEL: "nvidia/Nemotron-3-Embed-1B-BF16",
};

// Accept "host", "http://host", or a full URL from the sheet; keep only scheme + host name.
export function normalizeHost(input) {
  const text = String(input ?? "").trim();
  const match = text.match(/^(?:(https?):\/\/)?([A-Za-z0-9.-]+)(?::\d+)?(?:\/.*)?$/);
  if (!match || !/[A-Za-z0-9]/.test(match[2])) return null;
  return `${match[1] ?? "http"}://${match[2]}`;
}

// A key is one line of visible characters with no spaces.
export function isValidKey(key) {
  return typeof key === "string" && /^[\x21-\x7e]+$/.test(key);
}

// Set (or add) the managed lines in the .env text, keeping every other line as it was.
export function buildEnv(baseText, { origin, key }) {
  const values = {
    COURSE_API_KEY: key,
    ...Object.fromEntries(Object.entries(SERVICE_PORTS).map(([name, port]) => [name, `${origin}:${port}`])),
    ...MODELS,
    PROVIDER_MODE: "live",
  };
  const lines = baseText.replace(/\r\n/g, "\n").split("\n");
  for (const [name, value] of Object.entries(values)) {
    const index = lines.findIndex((line) => new RegExp(`^\\s*${name}\\s*=`).test(line));
    if (index >= 0) lines[index] = `${name}=${value}`;
    else lines.splice(lines.at(-1) === "" ? lines.length - 1 : lines.length, 0, `${name}=${value}`);
  }
  return lines.join("\n").replace(/\n*$/, "\n");
}

// True when .env already holds a real (non-placeholder) course key or URL.
function hasRealValues(text) {
  return /^(COURSE_API_KEY|CHAT_LLM_URL)=(?!.*replace-me)\S+/m.test(text);
}

// The whole flow, with input/output passed in so tests can drive it with decoy values.
export async function run({ envPath, examplePath, ask, askHidden, log, afterWrite }) {
  log("Course endpoint setup. Your answers are written only to your own .env file.\n");
  const base = existsSync(envPath) ? readFileSync(envPath, "utf8") : readFileSync(examplePath, "utf8");
  if (hasRealValues(base)) {
    const answer = await ask("Your .env already has course settings. Replace them? (y/N) ");
    if (!/^y(es)?$/i.test(answer.trim())) {
      log("Nothing changed.");
      return 0;
    }
  }

  const origin = normalizeHost(await ask("Course host (from the course endpoint list, e.g. the part after http://): "));
  if (!origin) {
    log("That doesn't look like a host name. Nothing changed; run npm run env:setup again.");
    return 1;
  }
  const key = (await askHidden("Course API key (hidden while you type or paste; press Enter): ")).trim();
  if (!isValidKey(key)) {
    log("That doesn't look like a key (it's empty or has spaces). Nothing changed.");
    return 1;
  }

  writeFileSync(envPath, buildEnv(base, { origin, key }), { encoding: "utf8", mode: 0o600 });
  if (process.platform !== "win32") chmodSync(envPath, 0o600);
  log("\nSaved to .env (only you can read it). PROVIDER_MODE is now live.\n");
  return afterWrite ? afterWrite() : 0;
}

// Ask a question with the answer shown.
async function ask(question) {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  try {
    return await rl.question(question);
  } finally {
    rl.close();
  }
}

// Ask a question without echoing what is typed or pasted.
function askHidden(question) {
  return new Promise((resolve) => {
    const stdin = process.stdin;
    let value = "";
    process.stdout.write(question);
    stdin.setRawMode(true);
    stdin.setEncoding("utf8");
    stdin.resume();
    const finish = () => {
      stdin.removeListener("data", onData);
      stdin.setRawMode(false);
      stdin.pause();
      process.stdout.write("\n");
    };
    function onData(chunk) {
      for (const ch of chunk) {
        if (ch === "\r" || ch === "\n") return finish(), resolve(value);
        if (ch === "\u0003") return finish(), process.exit(130); // Ctrl+C
        if (ch === "\u007f" || ch === "\b") value = value.slice(0, -1);
        else value += ch;
      }
    }
    stdin.on("data", onData);
  });
}

// Command-line entry: only for a person at a real terminal, with no arguments.
async function main() {
  if (process.argv.length > 2) {
    console.error("env:setup doesn't take values on the command line (they'd end up in shell history).");
    console.error("Run it with no arguments and answer the questions: npm run env:setup");
    return 1;
  }
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    console.error("env:setup must run in your own terminal window, so your key is never typed into a chat.");
    console.error("Open Terminal (Mac), PowerShell (Windows), or VS Code > Terminal > New Terminal,");
    console.error("go to the project folder, and run: npm run env:setup");
    return 1;
  }
  return run({
    envPath: join(root, ".env"),
    examplePath: join(root, ".env.example"),
    ask,
    askHidden,
    log: (text) => console.log(text),
    afterWrite: () => spawnSync(process.execPath, [join(root, "scripts", "check-env.mjs")], { stdio: "inherit" }).status ?? 1,
  });
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  process.exitCode = await main();
}
