// Tests for setup-env.mjs, using decoy values and temporary files only (never the real .env).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { MODELS, SERVICE_PORTS, buildEnv, isValidKey, normalizeHost, run } from "./setup-env.mjs";

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
