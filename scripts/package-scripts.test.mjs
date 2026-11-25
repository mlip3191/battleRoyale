// Tests that the instructor's start path runs the server through Python, not the uvicorn.exe
// launcher that Windows Smart App Control blocks in a fresh .venv (#366).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const scripts = JSON.parse(readFileSync(join(here, "..", "package.json"), "utf8")).scripts;

test("setup turns the commit guard on through a step that skips it in a ZIP copy (#597)", () => {
  assert.match(scripts.setup, /&& node scripts\/git-hooks\.mjs$/);
  assert.doesNotMatch(scripts.setup, /git config/);
});

for (const name of ["start", "dev:backend"]) {
  test(`${name} starts uvicorn with python -m (#366)`, () => {
    assert.match(scripts[name], /uv run --directory backend python -m uvicorn app\.main:app /);
    assert.doesNotMatch(scripts[name], /--directory backend uvicorn/);
  });
}
