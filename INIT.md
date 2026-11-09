# INIT.md — initialize the Battle Royale project

**Give this one document to Claude Code.** Clone the repo first, open Claude Code **inside the repo folder**, and say:

> Read INIT.md and follow it.

Claude Code only loads the project's rules (`CLAUDE.md`, `.claude/`) from the folder it was started in, so never start it from an empty folder or a parent folder.

This document takes the project from "plan only" to a protected repo with a running skeleton, CI, review tooling, every task filed as a GitHub issue, and the team assigned. It runs **Phase 0 (tasks M01–M08)** one task at a time and stops for Mike's OK at each step. Target: **Mon Nov 9 – Tue Nov 10**; the project is due **Wed Nov 25**.

---

## Part 1 — For Mike, before starting (about 15 minutes, by hand, on the Mac)

1. **Install and sign in:** Git, GitHub CLI, Claude Code (`claude`), Node 24, uv. Optional: `brew install gitleaks` (the git hook uses it when present; otherwise a built-in checker runs).
2. **GitHub CLI scopes:** `gh auth login` as `mlip3191`, then `gh auth refresh -s workflow,project,read:user`. Check with `gh auth status`: the token scopes must include `workflow` (needed to push workflow files in M04/M07), `project` (board in M08), and `read:user` (Pro check in M01).
3. **GitHub Pro** is active (confirmed). M01 double-checks it.
4. **Clone:** `git clone https://github.com/mlip3191/battleRoyale.git` then `cd battleRoyale`.
5. **Create your `.env` with the course endpoints:**
   - `cp .env.example .env` (Windows teammates: `copy .env.example .env`)
   - Open `.env` and fill **every line marked `[required]`**: `COURSE_API_KEY`, each service URL as `http(s)://<host>:<port>` (chat 9001, embeddings 9002, document parsing 9005, image 9006, plus structured decisions, reranking, text-to-speech, and music from the course list), and the model names. A service with its own key gets an extra line `<SERVICE>_API_KEY=` (e.g. `TTS_API_KEY=`).
   - **Leave `PROVIDER_MODE=mock` for now.** M06 tells you when to switch it to `live`.
   - Check it: `node scripts/check-env.mjs` — lists anything missing or malformed and **never prints values**. Repeat until all required values are filled in.
   - Never paste these values into GitHub, a commit, an issue, a PR, or a Claude chat. `.env` is ignored by git.
6. **Start Claude Code in the repo folder** (`claude`) and say "Read INIT.md and follow it." Have a few minutes free during M07 to run `claude setup-token`.

---

## Part 2 — Instructions for Claude Code

You are the build assistant for **Battle Royale: The Science-Backed Fight Simulator**, the MBAX 6418 final project of **Group A**: Mike Lippert (PM, `mlip3191`, runs this on a Mac), Adam Fondale (`afondale`), Gunnar O'Connor (`gunnaroc`), Felipe Cervino (`felcervino`), Dillon Smart (`dilloncsmart`). The four teammates are non-coders on Windows who build later through Claude Code. Mike is the only one with coding experience.

### Progress record (how you resume)

`docs/build-log.md` is the **single source of truth** for Phase 0 progress. It has one line per task in the form `Mxx: <state>`, where state is one of: `not started`, `in progress (branch phase0-mxx)`, `committed — <what's still pending>`, `merged — <what's still pending>`, or `done`. Every task updates its line in the same commit or PR as its work. If a task is interrupted, the line tells you exactly what's left.

### Step 0 — Orient and resume

1. Confirm you are inside a clone of `mlip3191/battleRoyale` (`CLAUDE.md` and `docs/` exist here). If not, stop and tell Mike to clone it and restart Claude Code inside the repo folder.
2. Run `git status` and `git branch --show-current` **before anything else.**
   - If you're on a `phase0-mxx` branch, or there are uncommitted changes, that task was interrupted. Tell Mike what you see and continue that task on that branch. Don't switch branches.
   - Otherwise `git switch main && git pull`.
3. Read `docs/build-log.md`.
   - **It doesn't exist yet:** nothing is committed. If Mike says M01 was already done, re-run only M01 step 7 (the read-back table; it changes nothing) and continue with M02. Otherwise start at M01.
   - **It exists:** find the first line that isn't `done` and resume exactly at what it says is pending. Special case: `M03: merged — live checks pending` means do M03 step 7 (post-restart decoy checks) before M04.
   - Cross-check against GitHub: `gh pr list --state all --limit 50 --json number,title,state,headRefName --jq '.[] | select(.headRefName | startswith("phase0-"))'`. If the log and GitHub disagree, show Mike both and ask.
4. On a fresh start (no build log), read in order: `CLAUDE.md`, `docs/PROJECT_GUIDE.md`, `docs/PRODUCT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/TEAM_PROCESS.md`, `docs/DECISIONS.md`, `docs/plan/LANES.md`, `docs/plan/DELIVERABLES.md`. **Where any document conflicts with INIT.md about Phase 0, INIT.md wins.** Give Mike a 10-line summary and list any remaining contradiction with a recommended fix. Wait for his answers. After a resume, skim instead.
5. Run `node scripts/check-env.mjs`. **Never open, print, or edit `.env` yourself.** If it reports problems, show Mike the report and walk him through Part 1 step 5. Everything before M06 works in mock mode, so you may continue and come back to it before M06.

### Rules for this session

- Do tasks **M01 → M08 strictly in order, one at a time.** For each task:
  1. Say which task you're starting and show its acceptance criteria.
  2. Follow its **Do this** steps exactly, including every confirmation point.
  3. When something must be done by hand (a GitHub setting, a secret, an invite), stop, give Mike a numbered checklist, and wait.
  4. Verify every acceptance criterion and show the evidence.
  5. Update its line in `docs/build-log.md` in the same commit or PR.
  6. Commit:
     - **M01:** nothing to commit (M02 records it).
     - **M02:** one commit directly to `main` (the rules that block this don't exist yet), then the hook test, the light ruleset, and invites.
     - **M03–M07:** work on a branch `phase0-mxx` (e.g. `phase0-m04`), commit there, push, open a PR with `gh pr create --body-file` titled with the task's commit message, wait for the checks that exist so far, then — after Mike confirms — `gh pr merge --squash --delete-branch`. Until M08 the ruleset needs no approvals, so Mike can merge his own Phase 0 PRs. This also gives the instructor the step-by-step history the Final Project Overview asks for.
     - **M08:** changes settings and creates issues; its only file change is the dry-run PR, which also records `M08: done`.
  7. Ask "Ready for the next task?" and wait.
- **Long text goes through files.** For every commit message, PR body, issue body, or comment, write the text to a file in `.claude/tmp/` (gitignored) and pass it with `git commit -F <file>`, `gh pr create --body-file <file>`, `gh issue create --body-file <file>`, or `gh pr comment --body-file <file>`. This keeps the shell guard (M03) from mistaking words in a message for a file path, and keeps messages intact.
- If anything fails, stop, explain it in plain English, and propose a fix. Never skip a guardrail. Never use `--no-verify`, never force push, and never use `git add -f` except in the one decoy test in M02, which says so explicitly.
- **Never read, print, edit, move, or delete `.env`.** Never test a guardrail against the real `.env`; tests use decoy files under `hook-test/` only. Never put endpoint hosts or keys in any file, commit, or message.
- **If Phase 0 slips past Tue Nov 10:** finish M07 and M08 first, and move M06 steps 4–5 (smoke test + live chat adapter) to Wed Nov 11 as a follow-up PR. Teammates' Wave 1 tasks don't depend on them.

---

## Part 3 — Phase 0 tasks (Mike's lane, 14 points)

| ID | Task | Size |
|---|---|---|
| M01 | GitHub repo settings, security, and Actions permissions | S |
| M02 | Line endings, build log, guardrail tests, light ruleset, early invites | S |
| M03 | Claude Code settings, permissions, and hooks (needs one restart) | M |
| M04 | Monorepo skeleton, one-command start, cross-platform files, CI | M |
| M05 | Shared contracts: Pydantic models, JSON Schema, fixtures, TS types | M |
| M06 | Provider layer: interfaces, mocks, config, live chat adapter, smoke test | M |
| M07 | Review tooling: advisory QA bot, Secret scan, critical-files check, CODEOWNERS, PR template | M |
| M08 | Labels, issues, project board, full branch protection, dry run, assignments | M |

### M01 · GitHub repo settings, security, and Actions permissions · S (1)

**Goal:** Configure the repo so it's safe before any code lands.
**Read first:** TEAM_PROCESS Step 0; DECISIONS D-01.

**Do this:** For each change, show Mike the exact `gh` command first and run it only after he confirms. If a command fails or isn't available for this account, stop and give the exact click path in the GitHub web UI instead.

1. Confirm GitHub Pro: `gh api user --jq .plan.name` should print `pro`. If it prints nothing or `null`, the token lacks `read:user`: ask Mike to run `gh auth refresh -s read:user` and retry, or to confirm Pro at github.com/settings/billing. Stop only if Pro is truly inactive.
2. Make the repo private: `gh repo edit mlip3191/battleRoyale --visibility private --accept-visibility-change-consequences`. (Forking settings only exist for organizations; on a private personal repo only collaborators can fork.)
3. Merge settings: squash merge only (disable merge commits and rebase merges); "Automatically delete head branches" on; "Always suggest updating pull request branches" on.
4. Security: Dependabot alerts and Dependabot security updates on. Confirm GitHub secret scanning/push protection is not offered for this private personal repo, and remind Mike that the local git hook and the gitleaks Secret scan (M07) cover secrets.
5. Actions: default workflow permissions read-only; "Allow GitHub Actions to create and approve pull requests" off. Restrict allowed actions to GitHub-made actions plus these patterns: `anthropics/claude-code-action@*`, `oven-sh/setup-bun@*` (used inside the Claude action), `gitleaks/gitleaks-action@*`, `astral-sh/setup-uv@*`.
6. Don't create any ruleset yet; that's M02 (light) and M08 (full).
7. Print a table of every setting with its current value, read back from the API. Keep it for `docs/build-log.md` (M02).

**Acceptance criteria**
- [ ] `gh api user --jq .plan.name` prints `pro` (or Mike confirms Pro in Billing), and `gh repo view mlip3191/battleRoyale --json visibility` shows `PRIVATE`
- [ ] `gh repo view --json squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed,deleteBranchOnMerge` shows `true`, `false`, `false`, `true`, and `gh api repos/mlip3191/battleRoyale --jq .allow_update_branch` shows `true`
- [ ] Dependabot alerts and Dependabot security updates read back as enabled
- [ ] `gh api repos/mlip3191/battleRoyale/actions/permissions/workflow` shows `default_workflow_permissions: read` and `can_approve_pull_request_reviews: false`; the allowed-actions list is GitHub-made actions plus exactly the four patterns in step 5
- [ ] The read-back table of every setting is shown to Mike and kept for the build log

### M02 · Line endings, build log, guardrail tests, light ruleset, early invites · S (1)

**Goal:** Make the git hook safe on Windows, start the progress record, prove the secret guard works without ever touching the real `.env`, lock `main` lightly, and let teammates start installing early.
**Read first:** TEAM_PROCESS Step 8; `.githooks/pre-commit`; DECISIONS team table, D-27.

**Do this:**

*Part A — commit the foundation (directly to `main`):*

1. **Line endings first** (Windows teammates' git would otherwise convert the hook to CRLF and break it): create `.gitattributes` with `* text=auto eol=lf`, `.githooks/* text eol=lf`, `*.sh text eol=lf`, `*.mjs text eol=lf`, `*.bat text eol=crlf`, `*.cmd text eol=crlf`; then `git add --renormalize .`.
2. `git config core.hooksPath .githooks`. Confirm `git ls-files -s .githooks/pre-commit` shows mode `100755`; if not, `git update-index --chmod=+x .githooks/pre-commit`.
3. Run `git ls-files --cached --ignored --exclude-standard` and confirm it prints nothing.
4. Create `docs/build-log.md` with a "Phase 0" heading, today's date, M01's settings table, and the progress lines: `M01: done`, `M02: committed — hook test, light ruleset, invites pending`, `M03: not started` … `M08: not started`.
5. Read `CLAUDE.md` fully; list anything wrong or missing vs. the docs and propose exact edits (update existing sections rather than adding duplicates); apply only what Mike approves.
6. Commit everything from steps 1–5 to `main` with message "Add line endings and build log; review CLAUDE.md (M02)" (via `git commit -F`), and push. The working tree is now clean.

*Part B — prove the hook with decoys only (scratch branch, nothing committed):*

7. `git switch -c phase0-hooktest`.
8. Create `hook-test/fake-key.txt` containing `aws_key = AKIA` followed by **16 characters chosen only from A–Z and 2–7** (the format gitleaks' AWS rule accepts; the built-in checker catches it too). Stage it and try to commit. Show that the commit was **blocked** by the hook's own message and that the key text was **not printed**.
9. Unstage it. Create `hook-test/decoy.env` with the line `DECOY=1`. It's ignored by `.gitignore`, so stage it with `git add -f hook-test/decoy.env` — **the one allowed use of `-f`, for this test only**. Try to commit; show the hook's "secrets file" block message.
10. Unstage, delete the `hook-test/` folder, run `git status` (clean) and `git log --oneline -2` (no new commit), then `git switch main` and, after Mike confirms, `git branch -D phase0-hooktest` (a throwaway branch with no commits; the M03 deny rule doesn't exist yet).

*Part C — light ruleset and early invites:*

11. Create a repository ruleset via `gh api repos/mlip3191/battleRoyale/rulesets` (method POST; show Mike the JSON first) targeting the default branch: require a pull request with **0 required approvals**, block force pushes, block deletions, no bypass actors. Verify with `gh api repos/mlip3191/battleRoyale/rules/branches/main` that the pull-request rule is listed.
12. Invite the teammates: `gh api -X PUT repos/mlip3191/battleRoyale/collaborators/<handle> -f permission=push` for `afondale`, `gunnaroc`, `felcervino`, `dilloncsmart`. (The instructor is not invited during Phase 0; Mike handles that himself later — see "After Phase 0".)
13. Draft a short email/text for Mike to send the team: accept the GitHub invite; follow README "Teammate quick start" steps 1–6 (install, clone, `.env`, `node scripts/check-env.mjs`); read `docs/PROJECT_GUIDE.md`; **don't start a task and don't merge anything until Mike assigns your first issue (Tue/Wed).**
14. The `M02: done` line is written in M03's PR (main now requires a PR). If the session stops before then, Step 0 sees `M02: committed — …` and checks the ruleset and invites through the API before moving on.

**Acceptance criteria**
- [ ] `git log origin/main -1` shows the M02 commit containing `.gitattributes` and `docs/build-log.md`
- [ ] `git ls-files -s .githooks/pre-commit` shows mode `100755`, and `git ls-files --eol .githooks/pre-commit` shows `i/lf`
- [ ] The fake AWS-format key commit is blocked with the hook's own "look like a key" message, and the key string does not appear anywhere in the output
- [ ] The `hook-test/decoy.env` commit is blocked with the hook's own "secrets file" message
- [ ] After the test: `git status` is clean, no new commit exists, `hook-test/` and `phase0-hooktest` are gone, and the real `.env` was never opened or changed
- [ ] `git ls-files --cached --ignored --exclude-standard` prints nothing
- [ ] `gh api repos/mlip3191/battleRoyale/rules/branches/main` lists the pull-request rule (0 approvals), the force-push block, and the deletion block
- [ ] `gh api repos/mlip3191/battleRoyale/invitations` lists `afondale`, `gunnaroc`, `felcervino`, `dilloncsmart`; the team message is drafted for Mike

### M03 · Claude Code settings, permissions, and hooks · M (2) — needs one restart

**Goal:** Enforce the CLAUDE.md rules with settings and hooks, so a non-coder can't accidentally approve something dangerous.
**Read first:** TEAM_PROCESS Step 7. Use the current, documented Claude Code settings and hooks syntax; check the official docs if unsure of a field name.

**Important facts:**
- Permission rules match command **prefixes**, so `git add . -f` can slip past a deny rule. **The hook scripts are the real enforcement;** deny rules are a first line.
- Hook matchers match **tool names** (e.g. the Bash tool, the PowerShell tool), not commands; each script filters commands itself.
- Claude Code loads hooks when a session starts, so hooks written in this session won't run until Claude Code restarts.
- If a hook exits with code 2 it blocks; any other failure lets the command through. So each guard script catches its own errors and exits 2 ("guard error — blocked to be safe"). Node is a prerequisite (Part 1).

**Do this** (on branch `phase0-m03`; first update the build log: `M03: in progress (branch phase0-m03)`, `M02: done`):

1. `.claude/settings.json`:
   - **allow:** Read/Grep/Glob of the repo; project scripts (`npm run setup|dev|start|test|lint|format|typecheck|build|check|gen:api|fixtures:sync|env:check`, `uv run pytest`, `uv run ruff`, `node scripts/check-env.mjs`); `git status|diff|log|branch|switch|checkout|add|commit|pull|fetch|stash|restore --staged`; `git push` of the current branch; read-only `gh pr view|list|diff|checks`, `gh issue view|list`, `gh run list|view`, `gh label list`, `gh secret list`.
   - **ask:** **every** `gh api` call (a read can't be told apart from a write by prefix, and `-f` turns a call into a POST); installing/upgrading packages; edits under `.github/`, `.claude/`, `.githooks/`, `scripts/`, and to `CLAUDE.md`, `INIT.md`, `.gitignore`, `.gitattributes`, `package.json`, `pyproject.toml`; `gh pr create|review|merge|comment|edit`, `gh issue create|edit`, `gh run rerun`, `gh workflow run`, `gh label create`, `gh project …`.
   - **deny:** Read, Edit, and Write of `.env`, `.env.local`, `.env.development`, `.env.production`, `.env.test`, `.env.*.local`, `**/*.pem`, `**/*.key` (list `.env` files by exact name so `.env.example` stays readable); `git push --force`, `git push -f`, `git push --delete`, `git reset --hard`, `git clean`, `git branch -D`, `git add -f`, `git add --force`, `git commit --no-verify`, `git commit -n`, `git config core.hooksPath`, `rm -rf`, `rm -fr`, `Remove-Item -Recurse`, `sudo`, `printenv`, `env`.
   - `permissions.disableBypassPermissionsMode`: `"disable"`.
2. **Hooks** as Node.js scripts in `.claude/hooks/`, registered with commands like `node "$CLAUDE_PROJECT_DIR/.claude/hooks/guard-shell.mjs"` (quoted, because Windows paths often contain spaces), with matchers for **both** the Bash and PowerShell tools:
   - `guard-shell.mjs` (PreToolUse): reads the tool input JSON from stdin; splits the command into segments on `;`, `&&`, `||`, `|`; tokenizes each segment respecting quotes. Blocks with exit code 2 and a plain-English reason on stderr:
     - `git commit` while the current branch is `main`; `git push` whose target is `main`; `git push` with `--delete`, `-d`, or a `:branch` refspec;
     - `-f`/`--force`/`--force-with-lease` anywhere in `git add` or `git push`; `--no-verify` or `-n` anywhere in `git commit`; `git reset --hard`; `git clean` (any form — `-x` deletes `.env`); `git branch -D`; `git config core.hooksPath`; `git checkout -- <path>`, `git checkout .`, and `git restore` without `--staged` (they discard work);
     - `rm` with both recursive and force flags in any order or spelling (`-rf`, `-fr`, `-r -f`); `Remove-Item -Recurse`;
     - **secret paths:** any token **without whitespace** whose last path component is `.env`, `.env.<anything>` other than `.env.example`/`.env.sample`/`.env.template`, ends in `.env` (e.g. `decoy.env`), or ends in `.pem`/`.key` — including after redirections (`>`, `<`, `>>`). Tokens with spaces (message text) are ignored, so `gh issue create --body-file …` and messages that mention `.env` work. Message: "Claude isn't allowed to read or change secret files. Ask the PM.";
     - `printenv`, bare `env`, `Get-ChildItem env:`, `gci env:`, `$env:`;
     - Allowed explicitly: `node scripts/check-env.mjs`; `gh pr merge … --delete-branch` (GitHub's own branch cleanup).
     - Wrap everything in try/catch; on any internal error, exit 2 with "guard error — blocked to be safe".
   - `ensure-hookspath.mjs` (PreToolUse on Bash/PowerShell): if the command contains `git commit` and `git config core.hooksPath` isn't `.githooks`, set it (the script itself runs git, which the deny rule doesn't affect) and say so.
   - `format-on-edit.mjs` (PostToolUse on Edit/Write): ruff format for `.py`, prettier for files under `frontend/`; skip quietly if the formatter isn't installed yet.
3. `.claude/hooks/test-hooks.mjs`: pipes fake tool-input JSON into each hook and asserts block/allow for at least 35 cases: every bypass spelling above, `cat .env`, `type backend\.env`, `Get-Content .env.local`, `echo x > .env`, `cat hook-test/decoy.env`, `.env.example` allowed, `node scripts/check-env.mjs` allowed, `gh issue create --body-file .claude/tmp/x.md` allowed, `git commit -m "fix .env loading docs"` allowed (message text), normal git commands allowed, and malformed JSON → blocked. Run it and show the results. **Never test against the real `.env`.**
4. CLAUDE.md: **update** the existing §10 "Permissions and hooks" (don't add a duplicate) with what's blocked, the "long text goes through `.claude/tmp/` files" rule, and "never suggest bypassing".
5. Set the build log line to `M03: merged — live checks pending`. Commit "Add shared Claude Code settings and hooks (M03)", push, open the PR, merge after Mike confirms.
6. **Restart:** tell Mike: "Type /exit, run `claude` again in this folder, run `/hooks` to review and accept the new hooks, then say: Read INIT.md and resume."
7. **After the restart** (Step 0 sends you here): live checks **with decoys only**:
   - Create `hook-test/decoy.env` containing `DECOY=1` with the Write tool (allowed: the deny rules name the real `.env` files exactly, and this is a decoy). Then try `cat hook-test/decoy.env` and `echo x > hook-test/decoy.env` in the shell: expect the hook's own "secret files" message for both.
   - On `main` with a staged harmless change (e.g. `hook-test/note.txt`), try `git commit -F <file>`: expect the hook's **own** "commit on main" message (git's "nothing to commit" doesn't count as evidence).
   - Read `.env.example` with the Read tool: expect allowed.
   - Clean up `hook-test/` (unstage, delete). Record `M03: done — live checks passed` in M04's first commit.

**Acceptance criteria**
- [ ] `node .claude/hooks/test-hooks.mjs` reports at least 35 cases and 0 failures, including every bypass spelling in step 2, the message-text cases, and malformed input → blocked
- [ ] After the restart: `cat hook-test/decoy.env` and `echo x > hook-test/decoy.env` are blocked with the hook's "secret files" message; a commit on `main` is blocked with the hook's "commit on main" message; reading `.env.example` succeeds
- [ ] `.claude/settings.json` registers the hooks for both the Bash and PowerShell tools using quoted `"$CLAUDE_PROJECT_DIR"` paths, and a test shows each guard exits 2 on an internal error
- [ ] `settings.json`: every `gh api` form is under ask; Read, Edit, and Write of the listed `.env` names, `**/*.pem`, and `**/*.key` are denied; `disableBypassPermissionsMode` is `"disable"`
- [ ] CLAUDE.md §10 is updated in place (no duplicate section); the plain-English permissions table is shown to Mike
- [ ] The build log shows `M03: merged — live checks pending`, and then `M03: done — live checks passed` in M04's PR

### M04 · Monorepo skeleton, one-command start, cross-platform files, CI · M (2)

**Goal:** An empty-but-running backend and front end, commands that work the same on Windows and Mac, `npm start` as the one-command run, and CI that fits the Actions-minutes budget.
**Read first:** ARCHITECTURE §2–3, §10, §13; TEAM_PROCESS Step 6; DECISIONS D-25, D-26.

**Do this** (branch `phase0-m04`; build log: `M03: done — live checks passed`, `M04: in progress`; ask before installing anything not listed):

Backend (`backend/`):
- uv project; Python 3.12 in `backend/.python-version`; `uv.lock` committed.
- Dependencies: fastapi, uvicorn[standard], pydantic, pydantic-settings, httpx, sqlite-vec, plus the ones later lanes are known to need, installed now so teammates don't wait on a critical-file approval: numpy (simulation), pyyaml (safety lists, benchmark). Dev: pytest, pytest-asyncio, hypothesis, ruff.
- `app/config.py`: a `Settings` class (pydantic-settings), the only module that reads environment variables:
  - `REPO_ROOT = Path(__file__).resolve().parents[2]`; `env_file = REPO_ROOT / ".env"` (the root `.env`, even though commands run from `backend/`); `extra="ignore"` (the root `.env` also holds `VITE_*`, `HERMES_URL`, and per-service keys).
  - Relative paths such as `DATA_DIR` resolve against `REPO_ROOT`, not the current folder.
  - Every key is a `SecretStr`, so printing settings never shows a key. Declare optional `<SERVICE>_API_KEY` fields for each service (CHAT_LLM, STRUCTURED_LLM, EMBEDDINGS, RERANK, DOC_PARSE, IMAGE, TTS, MUSIC) next to `COURSE_API_KEY`.
- `app/main.py`: app factory, CORS for `FRONTEND_ORIGIN`, `GET /api/health` → `{"status":"ok"}`. When `frontend/dist` exists, serve it as static files at `/`, with `index.html` as the fallback for front-end routes, so `npm start` needs one process and one port. Set the `httpx` and `httpcore` loggers to WARNING (at INFO they log full request URLs, which include endpoint hosts).
- `tests/conftest.py`: **force `PROVIDER_MODE=mock` and ignore `.env`** for every test (e.g. `Settings(_env_file=None, provider_mode="mock")` via a fixture/override), and a test proving it.
- Empty packages with `__init__.py` + one-line docstring: models, providers, safety, intake, research, simulation, narration, media, pipeline, api, db. Create `backend/prompts/`, `backend/scripts/`, `backend/tests/{unit,contract,golden,property,fixtures}` with a `.gitkeep` in each empty folder.
- ruff (line length 100, import sorting) and pytest config in `pyproject.toml`. One passing test for `/api/health`.

Front end (`frontend/`):
- Scaffold with the current create-vite, non-interactively: `npm create vite@latest frontend -- --template react-ts` (answer any prompt with the defaults; record the create-vite version in the build log). Node 24 pinned in root `.nvmrc` and `engines`; `package-lock.json` committed.
- `vite.config.ts`: `envDir: '..'` so Vite reads the **root** `.env` (only `VITE_*` variables reach the browser); dev proxy for `/api` and `/media` to :8000.
- Add phaser, react-router-dom (D02 needs it), vitest, @testing-library/react, jsdom, eslint, prettier, openapi-typescript.
- Folders `src/api`, `src/pages`, `src/components`, `src/game`, `src/fixtures`. A Home page that calls `/api/health` and shows "Backend: ok". One passing Vitest test.

Root:
- `package.json` scripts (cross-platform; `concurrently` as a root dev dependency):
  - `setup`: `npm ci` (root) + `uv sync --directory backend` + `npm ci --prefix frontend` + `git config core.hooksPath .githooks` (so commits from VS Code or GitHub Desktop are guarded too);
  - `dev` (backend :8000 + frontend :5173 with hot reload); `start` (build the front end, then run the backend serving everything at http://localhost:8000; print the URL); `test`, `lint`, `format`, `typecheck` (`tsc --noEmit`), `build` (`vite build`), `check` (lint + typecheck + test + build for both), `gen:api` and `fixtures:sync` (placeholders now; M05 fills them in), `env:check` (`node scripts/check-env.mjs`).
  - `doctor` is added later by task D01; don't create it now.
- Extend `.gitattributes` (from M02) with binary types: images, audio, fonts. `.editorconfig` (utf-8, lf, final newline, 2 spaces; 4 for `.py`).
- Keep `.gitignore`; don't remove any rule.

CI (`.github/workflows/ci.yml`), designed for the Actions-minutes budget (Pro: 3,000 min/month; Windows ×2, macOS ×10, so one macOS run ≈ 80 billed minutes):
- On `pull_request` and `push` to `main`: jobs `backend` and `frontend`, each on a matrix of `ubuntu-latest` and `windows-latest` → 4 checks that become required in M08.
- On `workflow_dispatch` only: the same jobs on `macos-latest` (an `os` input chooses it). Mike runs it before each milestone with `gh workflow run ci.yml --ref main -f os=macos-latest`. No nightly schedule.
- **No `paths:` filters** on this workflow: a required check that's skipped waits forever and blocks merging.
- `PROVIDER_MODE=mock`; `permissions: contents: read`; concurrency per branch with cancel-in-progress for pull requests only; `actions/setup-node` with `node-version-file: .nvmrc` and npm cache; `astral-sh/setup-uv` with cache.
- Steps: install from lockfiles; lint; typecheck; test; `vite build`; `npm audit --audit-level=high` as a **report-only** step (`continue-on-error: true`).

Finally: run `npm run setup`, `npm run check`, and `npm start` (open http://localhost:8000); show the output. Tell Mike the exact check names that will appear on PRs (expected: `backend (ubuntu-latest)`, `backend (windows-latest)`, `frontend (ubuntu-latest)`, `frontend (windows-latest)` — confirm from the first run). **Update** CLAUDE.md's existing Commands section. Build log: `M04: done`. Commit "Add monorepo skeleton, npm start, and CI (M04)"; PR; merge after the 4 checks pass and Mike confirms.

**Acceptance criteria**
- [ ] On Mike's Mac, with his filled root `.env` present: `npm run setup`, `npm run check`, `npm run dev`, and `npm start` all run without errors
- [ ] http://localhost:5173 (dev) and http://localhost:8000 (`npm start`) each show "Backend: ok"
- [ ] After `npm run setup`, `git config core.hooksPath` prints `.githooks`
- [ ] Tests prove: settings load the root `.env` when run from `backend/`; unknown keys are ignored; `repr(settings)` contains no key value; tests run in mock mode even when `.env` says `PROVIDER_MODE=live`
- [ ] The PR shows exactly four CI checks — `backend (ubuntu-latest)`, `backend (windows-latest)`, `frontend (ubuntu-latest)`, `frontend (windows-latest)` — all green; one manual `gh workflow run ci.yml --ref main -f os=macos-latest` run passes
- [ ] numpy, pyyaml, and react-router-dom are in the lockfiles; every empty `backend/tests/*` folder has a `.gitkeep`
- [ ] CLAUDE.md's Commands section matches the real scripts in `package.json`

### M05 · Shared contracts: Pydantic models, JSON Schema, fixtures, TS types · M (2)

**Goal:** Lock the shapes every lane builds against, so five people can work in parallel.
**Read first:** ARCHITECTURE §5 (normative), §14.

**Do this** (branch `phase0-m05`; build log `M05: in progress`):

1. Implement every model in ARCHITECTURE §5 in `backend/app/models/` (one module per heading: terrain, matchup, stats, simulation, narration, media, battle) with the exact field names, types, and constraints; docstrings explain each field in plain English.
2. Validators: `StatSheet` contains every `StatName`; `is_estimate=True` ⇒ `source=None` and confidence `low`; `method="extracted"` ⇒ source with a non-empty quote; `method="assumption"` only for `aggression_0_1`, `group_tactics_0_1`, `armor_0_1`, with a non-empty `note`; when `low`/`high` are set, `low ≤ value ≤ high`; `Matchup` has exactly 2 fighters; `FighterRequest.size_reference`, when set, is a non-empty entity name (never a number).
3. `backend/scripts/export_schema.py` writes JSON Schema for every model to `backend/app/models/schema/*.json`.
4. One realistic, valid fixture per model in `backend/tests/fixtures/contracts/` ("grizzly bear (adult male)" vs "6 gray wolves" on "forest"; every extracted value has a Wikipedia URL and quote). A `BattleRecord` fixture in "running" and one in "done".
5. `backend/tests/contract/`: every fixture validates; one negative test per validator rule.
6. **TypeScript types for all contracts:** the OpenAPI schema only includes models used by routes, and only `/api/health` exists now. So customize `app.openapi()` in `main.py` to add every contract model to `components.schemas` (Pydantic JSON Schema with `ref_template="#/components/schemas/{model}"`). Make `npm run gen:api` export the OpenAPI JSON from the app (no running server needed) and run openapi-typescript into `frontend/src/api/schema.d.ts`. Make `fixtures:sync` copy contract fixtures to `frontend/src/fixtures/`.
7. CI: a step that runs `gen:api` and `fixtures:sync` and fails if `git diff --exit-code` shows changes (generated files must be committed and current).
8. **Update** the existing CLAUDE.md §6 "Contracts" bullet if anything changed (models/ is critical; changes need a `contract-change` issue and PM approval).
Run `npm run check`; build log `M05: done`; commit "Add shared contracts and fixtures (M05)"; PR; merge.

**Acceptance criteria**
- [ ] Every model and field in ARCHITECTURE §5 exists with the same name, type, and constraints; Claude lists any deviation (expected: none)
- [ ] One valid fixture per model, plus the `BattleRecord` "running" and "done" fixtures; all validate
- [ ] One failing-input test per validator rule in step 2 (at least 8); all pass
- [ ] `backend/app/models/schema/` has a JSON Schema file for every model
- [ ] `frontend/src/api/schema.d.ts` has a type for every model in `backend/app/models/` (the list is compared in the PR); `frontend/src/fixtures/` matches the backend fixtures
- [ ] On a throwaway branch, changing a model without regenerating makes CI fail (shown once, then the branch is discarded)

### M06 · Provider layer: interfaces, mocks, config, live chat adapter, smoke test · M (2)

**Goal:** One clean way to call every course endpoint, a mock for each, and real facts about how the endpoints behave.
**Read first:** ARCHITECTURE §7, §13; `.env.example`.
**Manual prerequisite:** `node scripts/check-env.mjs` passes. Then Mike sets `PROVIDER_MODE=live` in `.env` himself (tests stay in mock mode thanks to the M04 conftest).

**Do this** (branch `phase0-m06`; build log `M06: in progress`):

1. `providers/base.py`: a Protocol per provider — ChatLLM, StructuredLLM, Embedder, Reranker, DocParser, ImageGen, TTS, MusicGen — async methods with type hints and docstrings.
2. `providers/mock/`: a deterministic mock for each (see ARCHITECTURE §7 "Mock behavior"); no network. Canned chat responses as JSON in `backend/tests/fixtures/providers/`, keyed by prompt name.
3. `providers/registry.py`: `get_provider(name)` returns mock or live per `settings.provider_mode`. Use every `.env.example` variable from `Settings`, including `*_MODEL` names. Keys: `<SERVICE>_API_KEY` if set, else `COURSE_API_KEY` (`.get_secret_value()` only at the moment of sending), sent the way the smoke test finds each endpoint expects. Live mode fails fast naming any missing variable (never its value). Never log or print a `Settings` object, a URL with its host, or a header.
4. `backend/scripts/smoke_providers.py`: for each configured service, one tiny request plus discovery paths (`/v1/models`, `/docs`, `/openapi.json`, `/health`); write findings (URL shape with host replaced by `<host>`, auth style, request/response format, latency) to `docs/providers.md`. **Before writing, scan the whole output for every configured host, URL, and key value — including inside response bodies such as an OpenAPI `servers` field or error text — redact any match, and refuse to write if anything remains.** Print only a pass/fail summary to the terminal.
5. `providers/live/chat.py`: live ChatLLM with httpx, 30 s timeout, 2 retries with backoff, optional JSON-schema mode. Assume an OpenAI-compatible `/v1/chat/completions` only if the smoke test confirms it; otherwise stop and show Mike what it found.
6. `GET /api/health`: `provider_mode` and per-provider `mock|up|down` (live: cached 2 s ping).
7. Tests: every mock satisfies its interface; registry returns mocks under test; a test that `repr(settings)` contains no key; live adapters skipped in CI.
Run the smoke script; show Mike `docs/providers.md` and confirm with him that it contains no hosts or keys; `npm run check`; build log `M06: done`; commit "Add provider layer and mocks (M06)"; PR; merge. (If Phase 0 is behind schedule, steps 4–5 may move to a follow-up PR on Nov 11 — mark the log `M06: merged — smoke test + live chat pending`.)

**Acceptance criteria**
- [ ] `providers/base.py` defines all 8 interfaces; each has a mock that passes an interface test; `npm run check` passes with no network
- [ ] `docs/providers.md` covers every configured service (URL shape with `<host>`, auth style, request/response format, latency); the redaction scan reports 0 remaining hosts or keys, and Mike confirms by reading it
- [ ] A live chat call from Mike's Mac returns a valid completion through `providers/live/chat.py` (shown without the host)
- [ ] `GET /api/health` returns `provider_mode` and a status for all 8 providers
- [ ] Tests: `repr(settings)` contains no key; the `httpx` and `httpcore` loggers are at WARNING

### M07 · Review tooling: advisory QA bot, Secret scan, critical-files check, CODEOWNERS, PR template · M (2)

**Goal:** Every PR gets an advisory AI review and a required secret scan, and critical files need the right approver.
**Read first:** TEAM_PROCESS Steps 2, 3, 8, 9; `.claude/skills/review-prs/SKILL.md`; `.claude/agents/code-reviewer.md`; DECISIONS D-04, D-26, D-29, D-30.
**Manual prerequisite:** Mike runs `claude setup-token`, then Settings → Secrets and variables → Actions → New repository secret `CLAUDE_CODE_OAUTH_TOKEN` (paste only into GitHub). The bot skips Dependabot PRs, so no Dependabot secret is needed.

**Do this** (branch `phase0-m07`; build log `M07: in progress`):

1. Copy `setup/templates/workflows/secret-scan.yml` and `setup/templates/workflows/ai-qa-review.yml` into `.github/workflows/`. The QA bot is **advisory**: it comments and records a verdict, never fails on the verdict, is never a required check, skips drafts/forks/Dependabot, and replaces the PR's `.claude/` and `CLAUDE.md` with `main`'s before running (so a PR can't change its rules or hooks). Confirm the secret exists with `gh secret list`. Personal-account repo, so gitleaks needs no license.
2. `.github/CODEOWNERS` assigning these critical paths to `@mlip3191` (leading `/` anchors a path at the repo root): `/CLAUDE.md`, `/INIT.md`, `/.claude/`, `/.github/`, `/.githooks/`, `/.gitignore`, `/.gitattributes`, `/.editorconfig`, `/.nvmrc`, `/.env.example`, `/.mcp.json`, `/.gitleaks.toml`, `/.gitleaksignore`, `/scripts/` (root only — `backend/scripts/` is not critical, D-29), `/package.json`, `/package-lock.json`, `/frontend/package.json`, `/frontend/package-lock.json`, `/backend/pyproject.toml`, `/backend/uv.lock`, `/backend/app/config.py`, `/backend/app/models/`, `/docs/ARCHITECTURE.md`.
3. `.github/workflows/critical-files.yml`, job name **"Critical files approval"**:
   - Trigger: `pull_request_target` with types `opened, synchronize, reopened, ready_for_review`. This runs **main's** copy of the workflow, so a PR can't weaken the check that guards it. Do **not** check out the PR's code; use only `gh`/API calls. Permissions: `contents: read`, `pull-requests: read`.
   - Logic: read the CODEOWNERS patterns **from `main`** via the API, and match the PR's changed files against them with the same root-anchored semantics. If any file matches and the author isn't `mlip3191`, pass only if `mlip3191` — or the backup approver `gunnaroc` when he isn't the author (DECISIONS D-31) — has an `APPROVED` review whose commit is the PR's current head SHA; otherwise fail with a plain-English reason. Every other case passes.
   - Approvals don't re-trigger `pull_request_target`, so after Mike approves a critical-file PR the check must be re-run. The review-prs skill does this automatically (`gh run rerun`), and Mike can also click "Re-run jobs".
4. `.github/pull_request_template.md`: Linked issue (`Closes #`), What changed (plain English), How it was tested, Screenshots (if UI), **Built with** (AI tool + model, e.g. "Claude Code — <model>"; feeds the Build Stack slide), Checklist (tests pass, lint passes, no secrets, scope limited to the issue, contract unchanged or `contract-change` label).
5. Verify the shipped review tooling (`.claude/agents/code-reviewer.md`, `.claude/commands/review.md`, `.claude/skills/review-prs/SKILL.md`): read them, check the `gh` commands are valid, and make sure the skill's fallback critical-files list matches CODEOWNERS. List any fixes. Don't change the confirm-before-send / confirm-before-approve rules.
6. Build log `M07: done`; commit "Add review tooling and checks (M07)"; PR; merge. Tell Mike that Secret scan, Critical files approval, and the advisory QA bot will all run on the dry-run PR in M08.

*If Phase 0 is behind:* the QA bot (step 1, second file) is advisory and can move to a follow-up PR later in the week. Secret scan and the critical-files check can't — they become required in M08.

**Acceptance criteria**
- [ ] `.github/workflows/` contains `ci.yml`, `secret-scan.yml`, `critical-files.yml`, and `ai-qa-review.yml`
- [ ] `gh secret list` shows `CLAUDE_CODE_OAUTH_TOKEN`; the QA bot workflow never fails on its verdict, skips drafts, forks, and Dependabot, restores `main`'s `.claude/` and `CLAUDE.md` before running, and has job-level concurrency
- [ ] `critical-files.yml` triggers only on `pull_request_target`, never checks out PR code, has read-only permissions, reads CODEOWNERS from `main`, and accepts approval from `mlip3191` or the backup `gunnaroc`
- [ ] CODEOWNERS uses root-anchored paths, including `/.gitleaksignore` and `/scripts/`; the PR template has a "Built with" section
- [ ] In a fresh Claude Code session, both "What can I review?" and `/review` start the review-prs skill (shown)

### M08 · Labels, issues, project board, full branch protection, dry run, assignments · M (2)

**Goal:** Turn the plan into GitHub issues on a board the team can use, finish protecting `main`, prove the whole loop, and assign everyone their work.
**Read first:** TEAM_PROCESS Steps 2, 4, 5; [docs/plan/LANES.md](docs/plan/LANES.md); DECISIONS D-26, D-28.

**Do this** (show each write command before running it; for repetitive creates, show Mike the full batch once and let him approve the batch):

1. **Labels** (`gh label create --force`, so existing defaults like `good first issue` are updated rather than failing): `type: feature`, `type: bug`, `type: chore`, `size: S`, `size: M`, `size: L`, `status: blocked`, `good first issue`, `contract-change`, `needs-pm`, `re-review` (asks the advisory QA bot to look again), `usability` (findings from D10), `lane: mike|adam|gunnar|felipe|dillon`, `wave: 1|2|3|4`.
2. **Issues**, created in dependency order (wave by wave, and within a wave so that a task's dependencies already exist), so every body can say "Blocked by #n" without a second pass. Read `docs/plan/lane-1-mike.md` (M09 only) and `docs/plan/lane-2-adam.md` … `lane-5-dillon.md`. One issue per task in lanes 2–5 (A01–A08, G01–G08, F01–F07, D01–D05, D07–D10) plus M09 from `docs/plan/lane-1-mike.md`: title "<ID> · <task name>"; body (via `--body-file`) = Goal, Read first, Blocked by #n, Acceptance criteria checklist, "Prompt: see docs/plan/<lane file> → <ID>". Labels: type, size, lane, wave. Show Mike the full list first. Also create closed issues M01–M07 linking their PRs, and an open M08 issue.
3. **Project board** (D-28): `gh project create --owner mlip3191 --title "Battle Royale"`; `gh project link <number> --owner mlip3191 --repo mlip3191/battleRoyale`; add all issues. Then give Mike the web-UI click paths for what the CLI can't do: (a) Status field values Backlog, Ready, In progress, In review, Done; (b) Workflows → turn on "Auto-add to project" (filter `is:issue,pr is:open` for this repo), "Item added to project → Backlog", and "Pull request merged → Done"; (c) Settings → Manage access → add `afondale`, `gunnaroc`, `felcervino`, `dilloncsmart` with Write. Then set Wave 1 issues to Ready.
4. **Invites accepted?** `gh api repos/mlip3191/battleRoyale/invitations --jq '.[].invitee.login'` must print nothing. GitHub won't let you assign people who haven't accepted, and invitations expire after 7 days; if anyone is pending, give Mike their handle to nudge (or re-invite), and wait.
5. **Assign** every issue to its lane owner (A→`afondale`, G→`gunnaroc`, F→`felcervino`, D→`dilloncsmart`, M09→`mlip3191`).
6. **Dry run** (before tightening the ruleset): issue "Dry run"; branch `issue-<n>-dry-run`; change one line in README.md and set `M08: done` in `docs/build-log.md`; push; open a PR with the template. Wait for CI (4), Secret scan, Critical files approval, and the advisory QA bot to report. Run the review-prs skill as if Mike were the reviewer and show that it refuses (he's the author). Leave the PR open for Felipe's first review (F01).
7. **Full ruleset:** update the M02 ruleset: require a pull request with **1 approval**; required status checks with source GitHub Actions — the 4 CI check names confirmed in M04, `Secret scan`, `Critical files approval`; block force pushes and deletions; no bypass actors. **Don't** turn on "branches up to date", "dismiss stale approvals", "approval of the most recent push", or "conversation resolution" (D-26). The QA bot is **not** a required check.
8. **Team board issue:** create and pin "Team board" (no chat channel): @mention all four with links to README "Teammate quick start", their lane file, their first issue, the board, the dry-run PR to review, and the rule: once a week comment here with done / doing / blocked.

**Acceptance criteria**
- [ ] `gh label list` shows every label in step 1, including `re-review`, `usability`, and the lane and wave labels
- [ ] One issue per task in lanes 2–5 plus M09 (32 issues), each with type, size, lane, and wave labels, a "Blocked by #n" line for every dependency in the lane tables, and the right assignee; closed issues M01–M07 and an open M08 exist
- [ ] The board is linked to the repo and has the five Status columns; auto-add is on; the four teammates have Write access; every Wave 1 issue is in Ready (Mike confirms the web-UI steps)
- [ ] The ruleset read back from `gh api repos/mlip3191/battleRoyale/rulesets` shows: 1 approval; required checks = the 4 CI names + `Secret scan` + `Critical files approval`; none of the four rules D-26 leaves off; no bypass actors
- [ ] On the dry-run PR all 6 required checks reported and the QA bot commented; the review-prs skill refused Mike as the author; the PR is left open for Felipe
- [ ] `gh api repos/mlip3191/battleRoyale/invitations` returns nothing; the pinned "Team board" issue @mentions all four teammates

### After Phase 0 — Mike's ongoing duties

- Triage the board each Monday; split anything that turns out larger than M.
- Approve every PR that touches a critical file (the skill then re-runs the critical-files check).
- Own `docs/ARCHITECTURE.md` and `docs/DECISIONS.md`.
- Before each milestone (Nov 14, 17, 20, 22): `gh workflow run ci.yml --ref main -f os=macos-latest` and test on the Mac by hand.
- Run `backend/scripts/smoke_providers.py` whenever an endpoint changes.
- Merge Dependabot PRs after CI and Secret scan pass (they need your approval for lockfiles).
- Check Actions minutes weekly (Settings → Billing). **Downgrade plan (D-34)** if fewer than ~600 minutes remain: (1) stop manual macOS runs; (2) switch the Windows CI jobs to on-demand and edit the ruleset so only the two ubuntu checks plus Secret scan and Critical files approval are required; (3) run Windows CI by hand before milestones. Keep the ruleset JSON for step 2 ready in `docs/build-log.md` so the switch takes one command.
- **Instructor access (your call, whenever you choose):** the overview requires adding the instructor as a collaborator on a private repo. GitHub invitations expire after 7 days, so invite close to when he'll look, or re-check and re-send. Claude doesn't send this.
- Squash-merged local branches can't be deleted by Claude (`git branch -D` is denied); clean them up yourself occasionally, or ignore them.

---

## Part 4 — What happens next (Claude: give Mike this briefing after M08, with real issue numbers and links)

1. **Kickoff (30 min, video call).** Mike shares his screen: the project board, one lane file, the dry-run PR. Everyone confirms README "Teammate quick start" is done (`.env` filled, `node scripts/check-env.mjs` passes, `npm run setup` works).
2. **Wave 1 (Wed Nov 11):** each teammate's setup task — A01 (Adam), G01 (Gunnar), F01 (Felipe, includes reviewing the dry-run PR with the review-prs skill), D01 (Dillon).
3. **Waves 2–4 (Nov 12–20):** teammates pick their next issue from **Ready**; every task's prompt is in their lane file. Mike moves issues to Ready as dependencies merge. Scope checks at MS-1 (Nov 14) and MS-2 (Nov 17) against the cut order in `docs/plan/LANES.md`.
4. **Weekly:** Monday triage; mid-week check-in on the pinned Team board issue; Friday benchmark review once F07 exists.
5. **Then:** feature freeze Nov 20, bug bash Nov 21, deck and rehearsals Nov 22–23, buffer Nov 24, due Nov 25 — see `docs/plan/DELIVERABLES.md`.
6. **Prompts teammates use:**
   - Start a task: *"Start work on issue #<n>. Read the task in docs/plan/<my lane file> under its ID, follow its prompt, and check off its acceptance criteria before opening the PR."*
   - Review: *"What can I review?"*
   - Ask the QA bot to look again after fixes: add the `re-review` label to the PR.
   - New work: `/new-issue` (after A01)
