// Tests for setup-env.mjs, using decoy values and temporary files only (never the real .env).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  MODELS,
  SERVICE_PORTS,
  buildEnv,
  cleanPath,
  isValidKey,
  normalizeHost,
  parseEndpointList,
  run,
  runImport,
} from "./setup-env.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const script = join(here, "setup-env.mjs");
const example = join(here, "..", ".env.example");
const DECOY_HOST = "decoy-host.invalid";
const DECOY_KEY = "decoy0000";

// A temp folder with a settings file path inside it (named so no guard mistakes it for .env).
function tempEnvPath() {
  return join(mkdtempSync(join(tmpdir(), "env-setup-test-")), "settings-under-test.txt");
}

// Drive run() with scripted answers; returns the exit code, the file text, and everything logged.
async function runWith(answers, envPath = tempEnvPath()) {
  const queue = [...answers];
  const output = [];
  const code = await run({
    envPath,
    examplePath: example,
    ask: async (q) => (output.push(q), queue.shift()),
    askHidden: async (q) => (output.push(q), queue.shift()),
    log: (text) => output.push(text),
  });
  const text = (() => {
    try {
      return readFileSync(envPath, "utf8");
    } catch {
      return null;
    }
  })();
  return { code, text, output: output.join("\n"), envPath };
}

test("normalizeHost keeps only scheme and host name", () => {
  assert.equal(normalizeHost(DECOY_HOST), `http://${DECOY_HOST}`);
  assert.equal(normalizeHost(`http://${DECOY_HOST}:9001/v1`), `http://${DECOY_HOST}`);
  assert.equal(normalizeHost(`https://${DECOY_HOST}`), `https://${DECOY_HOST}`);
  for (const bad of ["", "   ", "not a host", "http://", "host;rm"]) assert.equal(normalizeHost(bad), null);
});

test("isValidKey rejects empty keys and keys with spaces", () => {
  assert.ok(isValidKey(DECOY_KEY));
  for (const bad of ["", "two words", "line\nbreak"]) assert.equal(isValidKey(bad), false);
});

test("buildEnv sets every endpoint, model, key, and live mode, keeping other lines", () => {
  const base = "# comment\nCOURSE_API_KEY=replace-me\nCHAT_LLM_URL=http://replace-me-host:9001\nSIM_RUNS=42\n";
  const text = buildEnv(base, { origin: `http://${DECOY_HOST}`, key: DECOY_KEY });
  assert.match(text, /^# comment$/m);
  assert.match(text, /^SIM_RUNS=42$/m);
  assert.match(text, new RegExp(`^COURSE_API_KEY=${DECOY_KEY}$`, "m"));
  for (const [name, port] of Object.entries(SERVICE_PORTS)) {
    assert.match(text, new RegExp(`^${name}=http://${DECOY_HOST}:${port}$`, "m"));
  }
  for (const [name, model] of Object.entries(MODELS)) assert.ok(text.includes(`\n${name}=${model}\n`));
  assert.match(text, /^PROVIDER_MODE=live$/m);
  assert.equal(text.match(/^CHAT_LLM_URL=/gm).length, 1);
});

test("run fills a new file from .env.example, never prints the key or host, and locks the file", async () => {
  const { code, text, output, envPath } = await runWith([DECOY_HOST, DECOY_KEY]);
  assert.equal(code, 0);
  assert.match(text, new RegExp(`^COURSE_API_KEY=${DECOY_KEY}$`, "m"));
  assert.match(text, /^SIM_RUNS=1000$/m); // other settings come from the template
  assert.ok(!output.includes(DECOY_KEY), "the key must never be printed");
  assert.ok(!output.includes(DECOY_HOST), "the host must never be printed");
  if (process.platform !== "win32") assert.equal(statSync(envPath).mode & 0o777, 0o600);
});

test("run asks before replacing real values, and changes nothing on no", async () => {
  const envPath = tempEnvPath();
  const original = `COURSE_API_KEY=${DECOY_KEY}\nCHAT_LLM_URL=http://${DECOY_HOST}:9001\n`;
  writeFileSync(envPath, original);
  const { code, text } = await runWith(["n"], envPath);
  assert.equal(code, 0);
  assert.equal(text, original);
});

test("run rejects a bad host or key and writes nothing", async () => {
  assert.equal((await runWith(["not a host"])).text, null);
  const badKey = await runWith([DECOY_HOST, "two words"]);
  assert.equal(badKey.code, 1);
  assert.equal(badKey.text, null);
});

test("the command refuses values on the command line, without echoing them", () => {
  const result = spawnSync(process.execPath, [script, DECOY_HOST, DECOY_KEY], { encoding: "utf8" });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /doesn't take values on the command line/);
  assert.ok(!(result.stdout + result.stderr).includes(DECOY_KEY));
});

test("the command refuses to run without a real terminal (e.g. from Claude)", () => {
  const result = spawnSync(process.execPath, [script], { encoding: "utf8", input: `${DECOY_HOST}\n${DECOY_KEY}\n` });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /must run in your own terminal window/);
});

// A decoy course endpoint list in the published layout (one block per service).
function decoyList({ host = DECOY_HOST, key = DECOY_KEY, chatModel = "decoy/chat-model", skip = [] } = {}) {
  const services = [
    ["Hermes Primary Model", 9000, "/v1", "decoy/hermes"],
    ["Hermes Auxiliary Vision Model / Classification LLM", 9001, "/v1", chatModel],
    ["Text Embeddings", 9002, "", "decoy/embed-model"],
    ["Multimodal Embeddings", 9003, "/v1", "decoy/mm-embed"],
    ["Multimodal Reranking", 9004, "", "decoy/rerank"],
    ["Document Parsing", 9005, "/v1", "decoy/ocr"],
    ["Image Generation and Editing", 9006, "/v1", "decoy/image"],
    ["Music Generation", 9007, "", "decoy/music"],
    ["Text-to-Speech and Voice Cloning", 9018, "", "Decoy Voice V1"],
    ["Speech-to-Text", 9009, "/v1", "decoy/stt"],
    ["Structured Decisions", 9010, "", "decoy/decision-model"],
    ["Video Generation", 9011, "/v1", "decoy/video"],
  ].filter(([title]) => !skip.includes(title));
  const blocks = services.map(
    ([title, port, path, model]) =>
      `${title} — ${port}\nUsage: decoy.\nBase URL: http://${host}:${port}${path}\nAPI Key: ${key}\nModel: ${model}\nLicense: MIT\n`,
  );
  return `Class Model API Endpoints\n\n${blocks.join("\n")}\nNotes for agents\n\nEndpoint routing: Port 9000 is reserved.\n- vLLM (9000–9005): https://docs.invalid/\n`;
}

// A temp project folder plus a list file saved outside it.
function importSetup(listText = decoyList()) {
  const projectRoot = mkdtempSync(join(tmpdir(), "env-import-project-"));
  const listPath = join(mkdtempSync(join(tmpdir(), "env-import-list-")), "course endpoints.txt");
  writeFileSync(listPath, listText);
  return { projectRoot, listPath, envPath: join(projectRoot, "settings-under-test.txt") };
}

// Drive runImport() with scripted answers.
async function importWith(answers, { projectRoot, envPath }) {
  const queue = [...answers];
  const output = [];
  const code = await runImport({
    envPath,
    examplePath: example,
    projectRoot,
    ask: async (q) => (output.push(q), queue.shift()),
    log: (text) => output.push(text),
  });
  let text = null;
  try {
    text = readFileSync(envPath, "utf8");
  } catch {}
  return { code, text, output: output.join("\n") };
}

test("parseEndpointList maps services by title, with ports and models from the file", () => {
  const list = parseEndpointList(decoyList());
  assert.deepEqual(list.problems, []);
  assert.equal(list.origin, `http://${DECOY_HOST}`);
  assert.equal(list.key, DECOY_KEY);
  assert.equal(list.ports.TTS_URL, 9018); // a changed port is picked up from the file
  assert.equal(list.ports.HERMES_URL, 9000);
  assert.equal(list.ports.CHAT_LLM_URL, 9001);
  assert.equal(list.models.CHAT_LLM_MODEL, "decoy/chat-model");
  assert.equal(list.models.STRUCTURED_LLM_MODEL, "decoy/decision-model");
  assert.equal(list.models.EMBEDDINGS_MODEL, "decoy/embed-model");
  assert.deepEqual(list.missing, []);
  assert.deepEqual(list.ignored, ["Video Generation"]);
});

test("parseEndpointList keeps built-in ports for missing services and flags mixed hosts or keys", () => {
  const partial = parseEndpointList(decoyList({ skip: ["Music Generation"] }));
  assert.deepEqual(partial.missing, ["MUSIC_URL"]);
  assert.equal(partial.ports.MUSIC_URL, SERVICE_PORTS.MUSIC_URL);
  const mixed = parseEndpointList(decoyList() + decoyList({ host: "other.invalid", key: "decoy1111" }));
  assert.equal(mixed.problems.length, 2);
  assert.ok(!mixed.problems.join(" ").includes(DECOY_KEY));
  assert.ok(parseEndpointList("just some text").problems.length > 0);
});

test("cleanPath handles drag-and-drop quoting and ~", () => {
  assert.equal(cleanPath(" '/a/b c.txt' "), "/a/b c.txt");
  assert.equal(cleanPath('"/a/b c.txt"'), "/a/b c.txt");
  if (process.platform !== "win32") assert.equal(cleanPath("/a/b\\ c.txt"), "/a/b c.txt");
  assert.ok(!cleanPath("~/x.txt").startsWith("~"));
});

test("runImport applies every setting from the file and never prints the key or host", async () => {
  const setup = importSetup();
  const { code, text, output } = await importWith([setup.listPath], setup);
  assert.equal(code, 0);
  assert.match(text, new RegExp(`^COURSE_API_KEY=${DECOY_KEY}$`, "m"));
  assert.match(text, new RegExp(`^TTS_URL=http://${DECOY_HOST}:9018$`, "m"));
  assert.match(text, /^CHAT_LLM_MODEL=decoy\/chat-model$/m);
  assert.match(text, /^PROVIDER_MODE=live$/m);
  assert.match(text, /^SIM_RUNS=1000$/m);
  assert.ok(!output.includes(DECOY_KEY), "the key must never be printed");
  assert.ok(!output.includes(DECOY_HOST), "the host must never be printed");
  if (process.platform !== "win32") assert.equal(statSync(setup.envPath).mode & 0o777, 0o600);
});

test("runImport refuses a list file inside the project folder and writes nothing", async () => {
  const setup = importSetup();
  mkdirSync(join(setup.projectRoot, "notes"));
  const inside = join(setup.projectRoot, "notes", "endpoints.txt");
  writeFileSync(inside, decoyList());
  const { code, text, output } = await importWith([inside], setup);
  assert.equal(code, 1);
  assert.equal(text, null);
  assert.match(output, /inside the project folder/);
});

test("runImport rejects a missing or unusable file and writes nothing", async () => {
  const setup = importSetup("no services here");
  assert.equal((await importWith([join(setup.projectRoot, "nope.txt")], setup)).text, null);
  const bad = await importWith([setup.listPath], setup);
  assert.equal(bad.code, 1);
  assert.equal(bad.text, null);
});

test("the import command also refuses to run without a real terminal", () => {
  const result = spawnSync(process.execPath, [script, "--from-file"], { encoding: "utf8", input: "/x\n" });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /must run in your own terminal window/);
});
