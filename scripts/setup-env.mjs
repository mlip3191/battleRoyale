#!/usr/bin/env node
// Fills in the course endpoint settings in .env by asking for the host and API key in YOUR
// terminal. The key is typed hidden and never printed; nothing about the host or key is stored
// in the repo. Usage (from the repo root, Windows or Mac, in your own terminal window):
//   npm run env:setup    answer two questions (host, then key)
//   npm run env:import   point it at a saved copy of the course endpoint list file instead
// It refuses to run without a real terminal or with command-line values, so Claude (or a
// script) can't feed it a key and the key never lands in shell history.

import { chmodSync, existsSync, readFileSync, realpathSync, statSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
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
export function buildEnv(baseText, { origin, key, ports = SERVICE_PORTS, models = MODELS }) {
  const values = {
    COURSE_API_KEY: key,
    ...Object.fromEntries(Object.entries(ports).map(([name, port]) => [name, `${origin}:${port}`])),
    ...models,
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

// How each course service's title in the endpoint list maps to our setting names.
export const SERVICE_TITLES = {
  CHAT_LLM_URL: /classification llm/i,
  STRUCTURED_LLM_URL: /structured decisions/i,
  EMBEDDINGS_URL: /^text embeddings/i,
  RERANK_URL: /reranking/i,
  DOC_PARSE_URL: /document parsing/i,
  IMAGE_URL: /image generation/i,
  TTS_URL: /text-to-speech/i,
  MUSIC_URL: /music generation/i,
  STT_URL: /speech-to-text/i,
  MM_EMBEDDINGS_URL: /multimodal embeddings/i,
  HERMES_URL: /hermes primary/i,
};

// Read the course endpoint list text into settings. Errors and notes name services, never values.
export function parseEndpointList(text) {
  const blocks = [];
  for (const raw of String(text).replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trim();
    const heading = line.match(/^(.+?)\s+[—–-]+\s*(\d{2,5})$/);
    if (heading) blocks.push({ title: heading[1].trim(), port: Number(heading[2]) });
    const field = line.match(/^(Base URL|API Key|Model):\s*(.*)$/i);
    if (field && blocks.length) blocks.at(-1)[field[1].toLowerCase()] = field[2].trim();
  }

  const ports = {};
  const models = {};
  const origins = new Set();
  const keys = new Set();
  const ignored = [];
  const problems = [];
  for (const block of blocks) {
    const name = Object.keys(SERVICE_TITLES).find((setting) => SERVICE_TITLES[setting].test(block.title));
    if (!name) {
      ignored.push(block.title);
      continue;
    }
    const origin = normalizeHost(block["base url"]);
    const urlPort = String(block["base url"] ?? "").match(/:(\d+)(?:\/|$)/);
    if (!origin) problems.push(`${block.title}: no usable Base URL`);
    else origins.add(origin);
    if (!isValidKey(block["api key"])) problems.push(`${block.title}: no usable API Key`);
    else keys.add(block["api key"]);
    ports[name] = urlPort ? Number(urlPort[1]) : block.port;
    const modelName = name.replace(/_URL$/, "_MODEL");
    if (modelName in MODELS && isValidKey(block.model)) models[modelName] = block.model;
  }
  if (origins.size > 1) problems.push("the services list different hosts (only one host is supported)");
  if (keys.size > 1) problems.push("the services list different API keys (only one key is supported)");
  const missing = Object.keys(SERVICE_PORTS).filter((name) => !(name in ports));
  if (missing.length === Object.keys(SERVICE_PORTS).length) problems.push("no course services found in the file");

  return {
    origin: [...origins][0],
    key: [...keys][0],
    ports: { ...SERVICE_PORTS, ...ports },
    models: { ...MODELS, ...models },
    missing,
    ignored,
    problems,
  };
}

// Turn a typed or dragged-in path into a plain path (drop quotes and drag-and-drop escapes, expand ~).
export function cleanPath(input) {
  let text = String(input ?? "").trim();
  if (/^(['"]).*\1$/.test(text)) text = text.slice(1, -1);
  else if (process.platform !== "win32") text = text.replace(/\\(.)/g, "$1");
  if (text === "~" || text.startsWith("~/")) text = join(homedir(), text.slice(1));
  return text;
}

// Read the endpoint list file, refusing anything inside the project so the key can't be committed.
export function readListFile(input, projectRoot) {
  const path = cleanPath(input);
  if (!path || !existsSync(path) || !statSync(path).isFile()) return { error: "Can't find that file." };
  if (statSync(path).size > 1_000_000) return { error: "That file is too big to be the endpoint list." };
  const inside = relative(realpathSync(projectRoot), realpathSync(resolve(path)));
  if (!inside.startsWith("..") && !isAbsolute(inside)) {
    return { error: "That file is inside the project folder, where it could be committed. Move it outside (e.g. Documents) and try again." };
  }
  return { text: readFileSync(path, "utf8") };
}

// Load the current .env (or the template) and confirm before replacing real values.
async function loadBase({ envPath, examplePath, ask, log }) {
  const base = existsSync(envPath) ? readFileSync(envPath, "utf8") : readFileSync(examplePath, "utf8");
  if (hasRealValues(base)) {
    const answer = await ask("Your .env already has course settings. Replace them? (y/N) ");
    if (!/^y(es)?$/i.test(answer.trim())) {
      log("Nothing changed.");
      return null;
    }
  }
  return base;
}

// Write .env readable only by the user, then run the follow-up check.
function saveEnv(envPath, text, { log, afterWrite }) {
  writeFileSync(envPath, text, { encoding: "utf8", mode: 0o600 });
  if (process.platform !== "win32") chmodSync(envPath, 0o600);
  log("\nSaved to .env (only you can read it). PROVIDER_MODE is now live.\n");
  return afterWrite ? afterWrite() : 0;
}

// The import flow: read a saved course endpoint list file and apply every setting from it.
export async function runImport({ envPath, examplePath, projectRoot, ask, log, afterWrite }) {
  log("Course endpoint import. Settings are written only to your own .env file; no values are shown.\n");
  const base = await loadBase({ envPath, examplePath, ask, log });
  if (base === null) return 0;

  const file = readListFile(await ask("Path to your saved course endpoint list (drag the file here, then press Enter): "), projectRoot);
  if (file.error) {
    log(`${file.error} Nothing changed.`);
    return 1;
  }
  const list = parseEndpointList(file.text);
  if (list.problems.length) {
    log("Couldn't use that file. Nothing changed.");
    for (const problem of list.problems) log(`  - ${problem}`);
    return 1;
  }
  log(`Found ${Object.keys(SERVICE_PORTS).length - list.missing.length} of ${Object.keys(SERVICE_PORTS).length} course services.`);
  for (const name of list.missing) log(`  - ${name}: not in the file; kept the built-in port`);
  for (const title of list.ignored) log(`  - "${title}": not used by the app; skipped`);
  return saveEnv(envPath, buildEnv(base, list), { log, afterWrite });
}

// The whole flow, with input/output passed in so tests can drive it with decoy values.
export async function run({ envPath, examplePath, ask, askHidden, log, afterWrite }) {
  log("Course endpoint setup. Your answers are written only to your own .env file.\n");
  const base = await loadBase({ envPath, examplePath, ask, log });
  if (base === null) return 0;

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

  return saveEnv(envPath, buildEnv(base, { origin, key }), { log, afterWrite });
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

// Command-line entry: only for a person at a real terminal, with no values as arguments.
async function main() {
  const fromFile = process.argv[2] === "--from-file" && process.argv.length === 3;
  if (process.argv.length > 2 && !fromFile) {
    console.error("env:setup doesn't take values on the command line (they'd end up in shell history).");
    console.error("Run it with no arguments and answer the questions: npm run env:setup");
    return 1;
  }
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    console.error("env:setup must run in your own terminal window, so your key is never typed into a chat.");
    console.error("Open Terminal (Mac), PowerShell (Windows), or VS Code > Terminal > New Terminal,");
    console.error("go to the project folder, and run: npm run env:setup (or npm run env:import)");
    return 1;
  }
  const options = {
    envPath: join(root, ".env"),
    examplePath: join(root, ".env.example"),
    projectRoot: root,
    ask,
    askHidden,
    log: (text) => console.log(text),
    afterWrite: () => spawnSync(process.execPath, [join(root, "scripts", "check-env.mjs")], { stdio: "inherit" }).status ?? 1,
  };
  return fromFile ? runImport(options) : run(options);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  process.exitCode = await main();
}
