#!/usr/bin/env node
// Copy the backend contract fixtures to frontend/src/fixtures/ so UI work runs offline.
// Removes copies whose backend fixture was deleted. Run with: npm run fixtures:sync
import { copyFileSync, readdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const from = path.join(root, "backend", "tests", "fixtures", "contracts");
const to = path.join(root, "frontend", "src", "fixtures");

const isJson = (name) => name.endsWith(".json");
const sources = readdirSync(from).filter(isJson);

for (const name of readdirSync(to).filter(isJson)) {
  if (!sources.includes(name)) rmSync(path.join(to, name));
}
for (const name of sources) copyFileSync(path.join(from, name), path.join(to, name));

console.log(`Synced ${sources.length} contract fixtures to frontend/src/fixtures/`);
