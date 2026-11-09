#!/usr/bin/env node
// Tests for the Claude Code hooks: pipes fake tool-input JSON into each hook and checks
// whether it blocks (exit 2) or allows (exit 0). Uses throwaway git repos in the temp
// folder and decoy file names only; never touches the real .env.
// Run: node .claude/hooks/test-hooks.mjs
import { spawnSync, execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const GUARD = path.join(here, "guard-shell.mjs");
const ENSURE = path.join(here, "ensure-hookspath.mjs");
const FORMAT = path.join(here, "format-on-edit.mjs");

// Make a throwaway repo whose current branch is `branch`.
function tempRepo(branch) {
  const dir = mkdtempSync(path.join(tmpdir(), "hooktest-"));
  execFileSync("git", ["init", "-q", "-b", branch, dir]);
  return dir;
}

const onMain = tempRepo("main");
const onFeature = tempRepo("feature");

// Run a hook with raw stdin text; return its exit code and stderr.
function runHook(script, stdin, env = {}) {
  const r = spawnSync(process.execPath, [script], {
    input: stdin,
    encoding: "utf8",
    env: { ...process.env, ...env },
  });
  return { code: r.status, stderr: r.stderr, stdout: r.stdout };
}

// Tool input JSON for a shell command run in `cwd`.
const shell = (command, cwd = onFeature, tool = "Bash") =>
  JSON.stringify({ tool_name: tool, tool_input: { command }, cwd });

let passed = 0;
const failures = [];

// Assert that a hook blocks (2) or allows (0) the input.
function expect(name, script, stdin, want, opts = {}) {
  const { code, stderr } = runHook(script, stdin, opts.env);
  const ok = code === want && (!opts.message || stderr.includes(opts.message));
  if (ok) passed++;
  else failures.push(`${name}: wanted exit ${want}${opts.message ? ` with "${opts.message}"` : ""}, got ${code} ${stderr.trim()}`);
}

const SECRET = "secret files";
const block = (cmd, cwd, message) => expect(`block: ${cmd}`, GUARD, shell(cmd, cwd), 2, { message });
const allow = (cmd, cwd) => expect(`allow: ${cmd}`, GUARD, shell(cmd, cwd), 0);

try {
  // --- git commit
  block("git commit -m x", onMain, "no commit on main");
  block('git commit -m "wip"', onMain, "no commit on main");
  block("git commit --no-verify -m x");
  block("git commit -n -m x");
  block("git commit -anm x");
  block("git commit --no-verif -m x");
  block("git -c core.hooksPath=/dev/null commit -m x");
  // --- git push
  block("git push origin main");
  block("git push origin HEAD:main");
  block("git push origin feature:refs/heads/main");
  block("git push", onMain);
  block("git push origin", onMain);
  block("git push origin HEAD", onMain);
  block("git push --force");
  block("git push -f origin feature");
  block("git push --force-with-lease");
  block("git push --force-with-lease=origin/feature origin feature");
  block("git push -uf origin feature");
  block("git push origin +feature");
  block("git push --delete origin feature");
  block("git push -d origin feature");
  block("git push origin :feature");
  block("git push --all origin");
  // --- git add / reset / clean / branch / config / checkout / restore
  block("git add -f notes.txt");
  block("git add --force notes.txt");
  block("git add . -f");
  block("git add -Af");
  block("git reset --hard");
  block("git reset --hard HEAD~1");
  block("git clean -fd");
  block("git clean -xdf");
  block("git clean -n");
  block("git branch -D feature");
  block("git branch --delete --force feature");
  block("git config core.hooksPath /dev/null");
  block("git config --local core.hookspath x");
  block("git checkout -- notes.txt");
  block("git checkout .");
  block("git restore notes.txt");
  block("git restore --staged --worktree notes.txt");
  // --- recursive deletes
  block("rm -rf build");
  block("rm -fr build");
  block("rm -r -f build");
  block("rm --recursive --force build");
  block("rm -Rf build");
  block("sudo rm -rf build");
  block("Remove-Item -Recurse -Force build");
  block("Remove-Item build -recurse");
  block("ri -r build");
  // --- secret files (decoy names only)
  block("cat .env", undefined, SECRET);
  block("type backend\\.env", undefined, SECRET);
  block("Get-Content .env.local", undefined, SECRET);
  block("echo x > .env", undefined, SECRET);
  block("echo x >.env", undefined, SECRET);
  block("echo x >> .env.production", undefined, SECRET);
  block("cat < .env", undefined, SECRET);
  block("cat hook-test/decoy.env", undefined, SECRET);
  block("cat certs/server.pem", undefined, SECRET);
  block("cat secrets/id.key", undefined, SECRET);
  block("grep KEY .env", undefined, SECRET);
  block("head -5 backend/.env.development", undefined, SECRET);
  block("cp .env copy.txt", undefined, SECRET);
  block("node -e x --env-file=.env", undefined, SECRET);
  block('echo "$(cat .env)"', undefined, SECRET);
  // --- environment dumps
  block("printenv");
  block("printenv COURSE_API_KEY");
  block("env");
  block("env -0");
  block("Get-ChildItem env:");
  block("gci env:");
  block("echo $env:COURSE_API_KEY");
  // --- chains, nesting, and line continuations
  block("git status && git push --force");
  block("echo hi; rm -rf build");
  block("ls | git push -f");
  block('bash -c "git push --force"');
  block("powershell -Command \"Remove-Item -Recurse build\"");
  block("git push \\\n  --force");
  // --- PowerShell tool uses the same guard
  expect("block (PowerShell tool): Get-Content .env", GUARD, shell("Get-Content .env", onFeature, "PowerShell"), 2, { message: SECRET });

  // --- allowed
  allow("cat .env.example");
  allow("Get-Content .env.example");
  allow("cat .env.sample");
  allow("node scripts/check-env.mjs");
  allow("gh issue create --title x --body-file .claude/tmp/x.md");
  allow('git commit -m "fix .env loading docs"');
  allow('git commit -m "env: mention printenv in docs"');
  allow("git commit -F .claude/tmp/msg.txt");
  allow("git status");
  allow("git diff --staged");
  allow("git log --oneline -5");
  allow("git add .");
  allow("git add -A");
  allow("git push -u origin feature");
  allow("git push");
  allow("git push origin issue-12-count-clamp");
  allow("git restore --staged notes.txt");
  allow("git restore -S notes.txt");
  allow("git switch -c issue-1-x");
  allow("git switch main");
  allow("git checkout main");
  allow("git branch -d merged-branch");
  allow("git pull");
  allow("rm notes.txt");
  allow("rm -r build");
  allow("npm run check");
  allow("uv run --directory backend pytest");
  allow("gh pr merge 5 --squash --delete-branch");
  allow("env FOO=1 npm test");
  allow("cat README.md | grep env");
  allow("cat <<'EOF' > .claude/tmp/x.md\ngit push --force is banned\ncat .env\nEOF");

  // --- guard errors fail closed
  expect("guard-shell: malformed JSON blocks", GUARD, "{not json", 2, { message: "guard error" });
  expect("guard-shell: missing command blocks", GUARD, JSON.stringify({ tool_input: {} }), 2, { message: "guard error" });
  expect("guard-shell: unterminated quote blocks", GUARD, shell('echo "oops'), 2, { message: "guard error" });

  // --- ensure-hookspath
  const ensureRepo = tempRepo("feature");
  const env = { CLAUDE_PROJECT_DIR: ensureRepo };
  expect("ensure-hookspath: non-commit allowed", ENSURE, shell("git status", ensureRepo), 0, { env });
  expect("ensure-hookspath: commit allowed", ENSURE, shell("git commit -m x", ensureRepo), 0, { env });
  const set = execFileSync("git", ["-C", ensureRepo, "config", "core.hooksPath"], { encoding: "utf8" }).trim();
  if (set === ".githooks") passed++;
  else failures.push(`ensure-hookspath: wanted core.hooksPath .githooks, got "${set}"`);
  expect("ensure-hookspath: malformed JSON blocks", ENSURE, "{not json", 2, { env, message: "guard error" });
  expect("ensure-hookspath: missing command blocks", ENSURE, JSON.stringify({ tool_input: {} }), 2, { env, message: "guard error" });
  rmSync(ensureRepo, { recursive: true, force: true });

  // --- format-on-edit never blocks
  expect("format-on-edit: malformed JSON never blocks", FORMAT, "{not json", 0);
  expect("format-on-edit: missing file never blocks", FORMAT, JSON.stringify({ tool_input: { file_path: "nope.py" } }), 0);
} finally {
  rmSync(onMain, { recursive: true, force: true });
  rmSync(onFeature, { recursive: true, force: true });
}

const total = passed + failures.length;
for (const f of failures) console.log(`FAIL ${f}`);
console.log(`${total} cases, ${passed} passed, ${failures.length} failed`);
process.exit(failures.length ? 1 : 0);
