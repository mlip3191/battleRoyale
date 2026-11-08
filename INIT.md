# INIT.md — initialize the Battle Royale project

**Give this one document to Claude Code.** Clone the repo first, open Claude Code **inside the repo folder**, and say:

> Read INIT.md and follow it.

Claude Code only loads the project's rules (`CLAUDE.md`, `.claude/`) from the folder it was started in, so never start it from an empty folder or a parent folder.

This document takes the project from "plan only" to a protected repo with a running skeleton, CI, review tooling, every task filed as a GitHub issue, and the team invited. It runs **Phase 0 (tasks M01–M08)** one task at a time and stops for Mike's OK at each step. Target: **Mon Nov 9 – Tue Nov 10**; the project is due **Wed Nov 25**.

---

## Part 1 — For Mike, before starting (about 15 minutes, by hand, on the Mac)

1. **Install and sign in:** Git, GitHub CLI (`gh auth login` as `mlip3191`), Claude Code (`claude`), Node 24, uv. Optional but recommended: `brew install gitleaks` (the git hook uses it when present; without it a built-in checker runs).
2. **GitHub Pro** is active (confirmed). M01 double-checks it.
3. **Clone:** `git clone https://github.com/mlip3191/battleRoyale.git` then `cd battleRoyale`.
4. **Create your `.env` with the course endpoints:**
   - `cp .env.example .env` (Windows teammates: `copy .env.example .env`)
   - Open `.env` and fill **every line marked `[required]`**: `COURSE_API_KEY`, each service URL as `http(s)://<host>:<port>` (chat 9001, embeddings 9002, document parsing 9005, image 9006, plus structured decisions, reranking, text-to-speech, and music from the course list), and the model names. A service with its own key gets an extra line `<SERVICE>_API_KEY=` (e.g. `TTS_API_KEY=`).
   - **Leave `PROVIDER_MODE=mock` for now.** M06 tells you when to switch it to `live`.
   - Check it: `node scripts/check-env.mjs` — lists anything missing or malformed and **never prints values**. Repeat until all required values are filled in.
   - Never paste these values into GitHub, a commit, an issue, a PR, or a Claude chat. `.env` is ignored by git.
5. **Start Claude Code in the repo folder** (`claude`) and say "Read INIT.md and follow it." Have a few minutes free during M07 to run `claude setup-token`.

---

## Part 2 — Instructions for Claude Code

You are the build assistant for **Battle Royale: The Science-Backed Fight Simulator**, the MBAX 6418 final project of **Group A**: Mike Lippert (PM, `mlip3191`, runs this on a Mac), Adam Fondale (`afondale`), Gunnar O'Connor (`gunnaroc`), Felipe Cervino (`felcervino`), Dillon Smart (`dilloncsmart`). The four teammates are non-coders on Windows who build later through Claude Code. Mike is the only one with coding experience.

### Step 0 — Orient (and resume)

1. Confirm you are inside a clone of `mlip3191/battleRoyale` (`CLAUDE.md` and `docs/` exist here). If not, stop and tell Mike to clone it and restart Claude Code inside the repo folder.
2. `git switch main && git pull`.
3. **Resume check:** Phase 0 records progress in git, so you can pick up after a restart. Look at `git log --oneline` and `gh pr list --state all --search "phase0" --json title,state`. Every task's commit or PR title ends in `(Mxx)`; M01's results are recorded in `docs/build-log.md` by M02. Tell Mike which tasks are done, and continue from the first task that isn't. M03 requires one restart (see M03); this check is how you continue afterwards.
4. On a fresh start, read in order: `CLAUDE.md`, `docs/PROJECT_GUIDE.md`, `docs/PRODUCT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/TEAM_PROCESS.md`, `docs/DECISIONS.md`, `docs/plan/LANES.md`, `docs/plan/DELIVERABLES.md`. Give Mike a 10-line summary and list any contradiction or gap you find, with a recommended fix. Wait for his answers. (After a resume, skim instead.)
5. Run `node scripts/check-env.mjs`. **Never open, print, or edit `.env` yourself.** If it reports problems, show Mike the report and walk him through Part 1 step 4. Everything before M06 works in mock mode, so you may continue and come back to it before M06.

### Rules for this session

- Do tasks **M01 → M08 strictly in order, one at a time.** For each task:
  1. Say which task you're starting and show its acceptance criteria.
  2. Follow its **Do this** steps exactly, including every confirmation point.
  3. When something must be done by hand (a GitHub setting, a secret, an invite), stop, give Mike a numbered checklist, and wait.
  4. Verify every acceptance criterion and show the evidence.
  5. Commit:
     - **M01:** nothing to commit (results go into `docs/build-log.md` in M02).
     - **M02:** commit directly to `main` — the rules that block this don't exist yet. M02 then turns on a light ruleset for `main`.
     - **M03–M07:** work on a branch `phase0-mxx` (e.g. `phase0-m04`), commit there, push, open a PR with `gh pr create` titled with the task's commit message, wait for the checks that exist so far, then — after Mike confirms — `gh pr merge --squash --delete-branch`. Until M08 the ruleset needs no approvals, so Mike can merge his own Phase 0 PRs. This also gives the instructor the step-by-step history the Final Project Overview asks for.
     - **M08:** changes settings and creates issues; its only file change is the dry-run PR.
  6. Ask "Ready for the next task?" and wait.
- If anything fails, stop, explain it in plain English, and propose a fix. Never skip a guardrail. Never use `--no-verify`, never force push, and never use `git add -f` except in the one decoy test in M02, which says so explicitly.
- **Never read, print, edit, move, or delete `.env`.** Never test a guardrail against the real `.env`; tests use decoy files under `hook-test/` only. Never put endpoint hosts or keys in any file, commit, or message.

---

## Part 3 — Phase 0 tasks (Mike's lane, 14 points)

| ID | Task | Size |
|---|---|---|
| M01 | GitHub repo settings, security, and Actions permissions | S |
| M02 | Line endings, guardrail tests, build log, light ruleset, early invites | S |
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

1. Confirm GitHub Pro: `gh api user --jq .plan.name` should print `pro`. If not, stop.
2. Make the repo private: `gh repo edit mlip3191/battleRoyale --visibility private --accept-visibility-change-consequences`. (Forking settings only exist for organizations; on a private personal repo only collaborators can fork, so there's nothing else to set.)
3. Merge settings: squash merge only (disable merge commits and rebase merges); "Automatically delete head branches" on; "Always suggest updating pull request branches" on.
4. Security: Dependabot alerts and Dependabot security updates on. Confirm GitHub secret scanning/push protection is not offered for this private personal repo, and remind Mike that the local git hook and the gitleaks Secret scan (M07) cover secrets.
5. Actions: default workflow permissions read-only; "Allow GitHub Actions to create and approve pull requests" off. Restrict allowed actions to GitHub-made actions plus these patterns: `anthropics/claude-code-action@*`, `oven-sh/setup-bun@*` (used inside the Claude action), `gitleaks/gitleaks-action@*`, `astral-sh/setup-uv@*`.
6. Print a table of every setting with its current value, read back from the API. Keep it for `docs/build-log.md` (M02).

Don't create any ruleset yet; that's M02 (light) and M08 (full).

**Acceptance criteria**
- [ ] `plan.name` is `pro`; repo is private
- [ ] Squash-only merging, auto-delete head branches, update-branch suggestion on
- [ ] Dependabot alerts + security updates on
- [ ] Read-only `GITHUB_TOKEN`; Actions can't approve PRs; allowed-actions list set (incl. `oven-sh/setup-bun@*`)
- [ ] Settings table ready for the build log

### M02 · Line endings, guardrail tests, build log, light ruleset, early invites · S (1)

**Goal:** Make the git hook safe on Windows, prove the secret guard works without ever touching the real `.env`, record progress, lock `main` lightly, and let teammates start installing early.
**Read first:** TEAM_PROCESS Step 8; `.githooks/pre-commit`; DECISIONS team table.

**Do this:**

1. **Line endings first** (Windows teammates' git would otherwise convert the hook to CRLF and break it): create `.gitattributes` with `* text=auto eol=lf`, `.githooks/* text eol=lf`, `*.sh text eol=lf`, `*.mjs text eol=lf`, `*.bat text eol=crlf`, `*.cmd text eol=crlf`, then `git add --renormalize .`.
2. `git config core.hooksPath .githooks`. Confirm `git ls-files -s .githooks/pre-commit` shows mode `100755`; if not, `git update-index --chmod=+x .githooks/pre-commit`.
3. **Prove the hook on a scratch branch, with decoys only:**
   - `git switch -c phase0-hooktest`.
   - Create `hook-test/fake-key.txt` containing `aws_key = AKIA` followed by 16 random uppercase letters/digits (a fake AWS key ID format that both gitleaks and the built-in checker catch). Stage it, try to commit, and show that the commit was **blocked** and that the key text was **not printed**.
   - Create `hook-test/decoy.env` with the line `DECOY=1`. It's ignored by `.gitignore`, so stage it with `git add -f hook-test/decoy.env` — **this is the one allowed use of `-f`, for this test only**. Try to commit; show that it was blocked by name.
   - Unstage everything, delete `hook-test/`, run `git log --oneline -3` to prove nothing was committed, then `git switch main` and `git branch -D phase0-hooktest` (confirm with Mike first; it's a throwaway branch with no commits).
4. Run `git ls-files --cached --ignored --exclude-standard` and confirm it prints nothing.
5. Create `docs/build-log.md` with a "Phase 0" section: today's date, M01's settings table, and a line "M01 done". Each later task appends one line ("M0x done — PR #n").
6. Read `CLAUDE.md` fully; list anything wrong or missing vs. the docs and propose exact edits; apply only what Mike approves.
7. Commit to `main`: "Add line endings, build log; verify guardrails (M02)". Push.
8. **Light ruleset on `main`** (so teammates can be invited safely now): create a repository ruleset via `gh api repos/mlip3191/battleRoyale/rulesets` targeting the default branch with: require a pull request (0 required approvals for now), block force pushes, block deletions, no bypass actors. Show Mike the JSON first. Verify with `gh api repos/mlip3191/battleRoyale/rules/branches/main` that the pull-request rule is listed (don't push a real test commit).
9. **Early invites** so teammates can install, clone, set up `.env`, and read the docs on Nov 9–10 while Phase 0 continues: `gh api -X PUT repos/mlip3191/battleRoyale/collaborators/<handle> -f permission=push` for `afondale`, `gunnaroc`, `felcervino`, `dilloncsmart`. Then give Mike the click path to invite the instructor by email (Settings → Collaborators → Add people → david.dobolyi@colorado.edu). Draft a short email/text for Mike to send the team: accept the invite, follow README "Teammate quick start" steps 1–6 (install, clone, `.env`, `node scripts/check-env.mjs`), read `docs/PROJECT_GUIDE.md`, and **don't start a task until M08 assigns it**.

**Acceptance criteria**
- [ ] `.gitattributes` committed; hook is `100755` with LF endings
- [ ] Fake key and decoy `.env` both blocked; nothing committed; the real `.env` never touched
- [ ] No tracked file matches an ignore rule
- [ ] `docs/build-log.md` started; CLAUDE.md reviewed
- [ ] Light ruleset active (PR required, 0 approvals, no force push/deletion)
- [ ] Four teammates + instructor invited; team message drafted

### M03 · Claude Code settings, permissions, and hooks · M (2) — needs one restart

**Goal:** Enforce the CLAUDE.md rules with settings and hooks, so a non-coder can't accidentally approve something dangerous.
**Read first:** TEAM_PROCESS Step 7. Use the current, documented Claude Code settings and hooks syntax; check the official docs if unsure of a field name.

**Important facts:** permission rules match command **prefixes**, so `git add . -f` or `git push origin x --force` can slip past a deny rule. **The hook scripts are the real enforcement;** deny rules are a first line. Claude Code loads hooks when a session starts, so hooks written in this session won't run until Claude Code restarts.

**Do this** (on branch `phase0-m03`):

1. `.claude/settings.json`:
   - **allow:** Read/Grep/Glob of the repo; project scripts (`npm run setup|dev|start|test|lint|format|check|gen:api|doctor`, `uv run pytest`, `uv run ruff`, `node scripts/check-env.mjs`); `git status|diff|log|branch|switch|checkout|add|commit|pull|fetch|stash`, `git push` of the current branch; read-only `gh` (`gh pr view|list|diff|checks`, `gh issue view|list`, `gh run list|view`, `gh api` GET).
   - **ask:** installing/upgrading packages; edits under `.github/`, `.claude/`, `.githooks/`, `CLAUDE.md`, `.gitignore`, `.gitattributes`, `package.json`, `pyproject.toml`, `scripts/`; any `gh` command that writes (`gh pr create|review|merge|comment`, `gh issue create|edit`, `gh run rerun`, `gh api` with POST/PUT/PATCH/DELETE).
   - **deny:** Read of `.env`, `.env.local`, `.env.development`, `.env.production`, `.env.test`, `.env.*.local`, `**/*.pem`, `**/*.key` (list `.env` files by exact name so `.env.example` stays readable); `git push --force`, `git push -f`, `git reset --hard`, `git branch -D`, `git add -f`, `git add --force`, `git commit --no-verify`, `git commit -n`, `git config core.hooksPath`, `rm -rf`, `Remove-Item -Recurse`, `sudo`, `printenv`, `env`.
   - `permissions.disableBypassPermissionsMode`: `"disable"`.
2. **Hooks** as Node.js scripts in `.claude/hooks/`, referenced with `$CLAUDE_PROJECT_DIR` so they work from any working directory, with matchers for **both** the Bash and PowerShell tools:
   - `guard-shell.mjs` (PreToolUse): reads the tool input JSON from stdin, tokenizes the command (split on `;`, `&&`, `||`, `|`), and blocks (exit code 2 with a plain-English reason on stderr):
     - `git commit` while the current branch is `main`, and `git push` to `main`;
     - `-f`/`--force` anywhere in `git add` or `git push`; `--no-verify` or `-n` anywhere in `git commit`; `git reset --hard`; `git branch -D`; `git config core.hooksPath`;
     - any mention of a `.env` file other than `.env.example` (e.g. `.env`, `.env.local`, `backend/.env`), or of `*.pem`/`*.key` files, with the message "Claude isn't allowed to read secrets. Ask the PM.";
     - `printenv`, bare `env`, `Get-ChildItem env:`, `$env:`, `gci env:`.
     - Exception: commands that only run `node scripts/check-env.mjs` are allowed.
   - `ensure-hookspath.mjs` (PreToolUse on `git commit`): if `git config core.hooksPath` isn't `.githooks`, set it and say so.
   - `format-on-edit.mjs` (PostToolUse on file edits): ruff format for `.py`, prettier for files under `frontend/`; skip quietly if the formatter isn't installed yet.
3. `.claude/hooks/test-hooks.mjs`: a test script that pipes fake tool-input JSON into each hook and asserts block/allow for at least 25 cases (all the bypass spellings above, `.env.example` allowed, `node scripts/check-env.mjs` allowed, normal git commands allowed). Run it and show the results. **Never test against the real `.env`.**
4. Add a short "Permissions and hooks" section to CLAUDE.md (what's blocked; never suggest bypassing).
5. Commit "Add shared Claude Code settings and hooks (M03)", push, open the PR, merge after Mike confirms.
6. **Restart:** tell Mike: "Type /exit, run `claude` again in this folder, run `/hooks` to review and accept the new hooks, then say: Read INIT.md and resume." After the restart (Step 0's resume check puts you here), do live checks **only with decoys**: try `cat hook-test/decoy.env` (create it first with `DECOY=1`; expect blocked), `git commit` on `main` (expect blocked), and reading `.env.example` (expect allowed). Delete `hook-test/`. Append "M03 done" to the build log in the next task's PR.

**Acceptance criteria**
- [ ] `test-hooks.mjs` passes all cases, including the bypass spellings
- [ ] After restart: decoy `.env` read blocked; commit on `main` blocked; `.env.example` readable
- [ ] Hooks cover Bash and PowerShell; paths use `$CLAUDE_PROJECT_DIR`
- [ ] Plain-English table of the permission rules shown to Mike

### M04 · Monorepo skeleton, one-command start, cross-platform files, CI · M (2)

**Goal:** An empty-but-running backend and front end, commands that work the same on Windows and Mac, `npm start` as the one-command run, and CI that fits the Actions-minutes budget.
**Read first:** ARCHITECTURE §2–3, §10; TEAM_PROCESS Step 6; DECISIONS D-25.

**Do this** (on branch `phase0-m04`; ask before installing anything not listed):

Backend (`backend/`):
- uv project; Python 3.12 in `backend/.python-version`; `uv.lock` committed.
- Dependencies: fastapi, uvicorn[standard], pydantic, pydantic-settings, httpx, sqlite-vec. Dev: pytest, pytest-asyncio, hypothesis, ruff.
- `app/main.py`: app factory, CORS for `FRONTEND_ORIGIN`, `GET /api/health` → `{"status":"ok"}`. When `frontend/dist` exists, serve it as static files at `/`, with `index.html` as the fallback for front-end routes, so `npm start` needs one process and one port.
- `app/config.py`: a `Settings` class (pydantic-settings) reading `.env`; the only module that reads environment variables.
- `tests/conftest.py`: **force `PROVIDER_MODE=mock` and ignore `.env`** for every test (e.g. override settings with `_env_file=None`), so local test runs never call live endpoints, even after Mike switches `.env` to live.
- Empty packages with `__init__.py` + one-line docstring: models, providers, safety, intake, research, simulation, narration, media, pipeline, api, db. Create `backend/prompts/`, `backend/scripts/`, `backend/tests/{unit,contract,golden,property,fixtures}`.
- ruff (line length 100, import sorting) and pytest config in `pyproject.toml`. One passing test for `/api/health`.

Front end (`frontend/`):
- `npm create vite@latest frontend -- --template react-ts` (non-interactive). Node 24 pinned in root `.nvmrc` and `engines`; `package-lock.json` committed.
- Add phaser, vitest, @testing-library/react, jsdom, eslint, prettier, openapi-typescript.
- Folders `src/api`, `src/pages`, `src/components`, `src/game`, `src/fixtures`. A Home page that calls `/api/health` through the Vite dev proxy and shows "Backend: ok". One passing Vitest test.

Root:
- `package.json` scripts (cross-platform; `concurrently` as a root dev dependency):
  - `setup`: `npm ci` (root) + `uv sync --directory backend` + `npm ci --prefix frontend` + `git config core.hooksPath .githooks` (so commits from VS Code or GitHub Desktop are guarded too);
  - `dev` (backend :8000 + frontend :5173 with hot reload); `start` (build the front end, then run the backend serving everything at http://localhost:8000; print the URL); `test`, `lint`, `format`, `typecheck` (`tsc --noEmit`), `build` (`vite build`), `check` (lint + typecheck + test + build for both), `gen:api` (later tasks fill this in), `env:check` (`node scripts/check-env.mjs`).
- Extend `.gitattributes` (from M02) with binary types: images, audio, fonts. `.editorconfig` (utf-8, lf, final newline, 2 spaces; 4 for `.py`).
- Keep `.gitignore`; don't remove any rule.

CI (`.github/workflows/ci.yml`), designed for the Actions-minutes budget (Pro: 3,000 min/month; Windows ×2, macOS ×10):
- On `pull_request`: jobs `backend` and `frontend`, each on `ubuntu-latest` and `windows-latest` → 4 checks that become required in M08.
- On `push` to `main`, nightly `schedule`, and `workflow_dispatch`: the same jobs on `macos-latest` only (Mac coverage without slowing PRs; Mike also tests Mac by hand).
- `PROVIDER_MODE=mock`, `permissions: contents: read`, concurrency per branch with cancel-in-progress, `actions/setup-node` with `node-version-file: .nvmrc` and npm cache, `astral-sh/setup-uv` with cache.
- Steps: install from lockfiles; lint; typecheck; test; `vite build`.

Finally: run `npm run setup`, `npm run check`, `npm start` (open http://localhost:8000), and show the output. Tell Mike the exact check names that will appear on PRs. Update CLAUDE.md's Commands section. Commit "Add monorepo skeleton, npm start, and CI (M04)"; PR; merge after the 4 PR checks pass and Mike confirms.

**Acceptance criteria**
- [ ] `npm run setup` (incl. root `npm ci` and hooks path), `npm run dev`, `npm run check` work on the Mac
- [ ] http://localhost:5173 (dev) and http://localhost:8000 (`npm start`) show "Backend: ok"
- [ ] Tests run in mock mode even with a live `.env` (conftest proven by a test)
- [ ] 4 PR checks green (ubuntu + windows × backend + frontend); macOS runs on push to `main`
- [ ] CLAUDE.md Commands section updated

### M05 · Shared contracts: Pydantic models, JSON Schema, fixtures, TS types · M (2)

**Goal:** Lock the shapes every lane builds against, so five people can work in parallel.
**Read first:** ARCHITECTURE §5 (normative), §14.

**Do this** (branch `phase0-m05`):

1. Implement every model in ARCHITECTURE §5 in `backend/app/models/` (one module per heading: terrain, matchup, stats, simulation, narration, media, battle) with the exact field names, types, and constraints; docstrings explain each field in plain English.
2. Validators: `StatSheet` contains every `StatName`; `is_estimate=True` ⇒ `source=None` and confidence `low`; `method="extracted"` ⇒ source with a non-empty quote; `Matchup` has exactly 2 fighters.
3. `backend/scripts/export_schema.py` writes JSON Schema for every model to `backend/app/models/schema/*.json`.
4. One realistic, valid fixture per model in `backend/tests/fixtures/contracts/` ("grizzly bear (adult male)" vs "6 gray wolves" on "forest"; every extracted value has a Wikipedia URL and quote). A `BattleRecord` fixture in "running" and one in "done".
5. `backend/tests/contract/`: every fixture validates; one negative test per validator rule.
6. **TypeScript types for all contracts:** the OpenAPI schema only includes models used by routes, and only `/api/health` exists now. So customize `app.openapi()` in `main.py` to add every contract model to `components.schemas` (using Pydantic's JSON Schema with `ref_template="#/components/schemas/{model}"`). Then make `npm run gen:api` export the OpenAPI JSON from the app (no running server needed) and run openapi-typescript into `frontend/src/api/schema.d.ts`. Add `fixtures:sync` (copies contract fixtures to `frontend/src/fixtures/`).
7. CI: add a step that runs `gen:api` and `fixtures:sync` and fails if `git diff --exit-code` shows changes (generated files must be committed and current).
8. Add a short "Contracts" section to CLAUDE.md (models/ is critical; changes need a `contract-change` issue and PM approval).
Run `npm run check`; commit "Add shared contracts and fixtures (M05)"; PR; merge.

**Acceptance criteria**
- [ ] All models match ARCHITECTURE §5; schema exported; fixtures validate; negative tests pass
- [ ] `frontend/src/api/schema.d.ts` contains every contract type; fixtures synced
- [ ] CI fails if generated types or fixtures are stale

### M06 · Provider layer: interfaces, mocks, config, live chat adapter, smoke test · M (2)

**Goal:** One clean way to call every course endpoint, a mock for each, and real facts about how the endpoints behave.
**Read first:** ARCHITECTURE §7, §13; `.env.example`.
**Manual prerequisite:** `node scripts/check-env.mjs` passes. Then Mike sets `PROVIDER_MODE=live` in `.env` himself (tests stay in mock mode thanks to the M04 conftest).

**Do this** (branch `phase0-m06`):

1. `providers/base.py`: a Protocol per provider — ChatLLM, StructuredLLM, Embedder, Reranker, DocParser, ImageGen, TTS, MusicGen — async methods with type hints and docstrings.
2. `providers/mock/`: a deterministic mock for each (see ARCHITECTURE §7 "Mock behavior"); no network. Canned chat responses as JSON in `backend/tests/fixtures/providers/`, keyed by prompt name.
3. `providers/registry.py`: `get_provider(name)` returns mock or live per `settings.provider_mode`. Add every `.env.example` variable to `Settings`, including `*_MODEL` names. Keys: `<SERVICE>_API_KEY` if set, else `COURSE_API_KEY`, sent the way the smoke test finds each endpoint expects. Live mode fails fast naming any missing variable (never its value).
4. `backend/scripts/smoke_providers.py`: for each configured service, one tiny request plus discovery paths (`/v1/models`, `/docs`, `/openapi.json`, `/health`); write findings (URL shape with host replaced by `<host>`, auth style, request/response format, latency) to `docs/providers.md`. **Before writing, scan the whole output for every configured host, URL, and key value (including inside response bodies such as an OpenAPI `servers` field or error text); redact any match, and refuse to write if anything remains.** Never print keys or hosts to the terminal.
5. `providers/live/chat.py`: live ChatLLM with httpx, 30 s timeout, 2 retries with backoff, optional JSON-schema mode. Assume an OpenAI-compatible `/v1/chat/completions` only if the smoke test confirms it; otherwise stop and show Mike what it found.
6. `GET /api/health`: `provider_mode` and per-provider `mock|up|down` (live: cached 2 s ping).
7. Tests: every mock satisfies its interface; registry returns mocks under test; live adapters skipped in CI.
Run the smoke script; show Mike `docs/providers.md` and confirm with him that it contains no hosts or keys; `npm run check`; commit "Add provider layer and mocks (M06)"; PR; merge.

**Acceptance criteria**
- [ ] Every provider has an interface and a mock; CI runs fully on mocks
- [ ] `docs/providers.md` documents each endpoint with no host, URL, or key (redaction check passed)
- [ ] Live chat adapter works from Mike's Mac
- [ ] `/api/health` shows per-provider status

### M07 · Review tooling: advisory QA bot, Secret scan, critical-files check, CODEOWNERS, PR template · M (2)

**Goal:** Every PR gets an advisory AI review and a required secret scan, and critical files need the right approver.
**Read first:** TEAM_PROCESS Steps 2, 3, 8, 9; `.claude/skills/review-prs/SKILL.md`; `.claude/agents/code-reviewer.md`; DECISIONS D-04, D-26.
**Manual prerequisite:** Mike runs `claude setup-token`, then Settings → Secrets and variables → Actions → New repository secret `CLAUDE_CODE_OAUTH_TOKEN` (paste only into GitHub). Optional: also add it under Settings → Secrets and variables → **Dependabot** (otherwise the bot simply skips Dependabot PRs).

**Do this** (branch `phase0-m07`):

1. Copy `setup/templates/workflows/secret-scan.yml` and `setup/templates/workflows/ai-qa-review.yml` into `.github/workflows/`. The QA bot is **advisory**: it comments and posts a verdict but its job never fails on the verdict, it is never a required check, and it skips drafts, forks, and Dependabot PRs. Confirm the secret exists with `gh secret list`. Personal-account repo, so gitleaks needs no license.
2. `.github/CODEOWNERS` assigning these critical paths to `@mlip3191`: `CLAUDE.md`, `.claude/`, `.github/`, `.githooks/`, `.gitignore`, `.gitattributes`, `.editorconfig`, `.nvmrc`, `.env.example`, `.mcp.json`, `.gitleaks.toml`, `scripts/`, `package.json`, `package-lock.json`, `frontend/package.json`, `frontend/package-lock.json`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/app/config.py`, `backend/app/models/`, `docs/ARCHITECTURE.md`, `INIT.md`.
3. `.github/workflows/critical-files.yml`, job name **"Critical files approval"**:
   - Trigger: `pull_request_target` with types `opened, synchronize, reopened, ready_for_review`. This runs **main's** copy of the workflow, so a PR can't weaken the check that guards it. Do **not** check out the PR's code; use only `gh`/API calls. Permissions: `contents: read`, `pull-requests: read`.
   - Logic: list the PR's changed files; if any matches a CODEOWNERS path and the author isn't `mlip3191`, pass only if `mlip3191` has an `APPROVED` review whose commit is the PR's current head SHA; otherwise fail with a plain-English reason. Every other case passes.
   - Because approvals don't re-trigger `pull_request_target`, after Mike approves a critical-file PR the check must be re-run. The review-prs skill does this automatically (`gh run rerun`), and Mike can also click "Re-run jobs" on the check.
4. `.github/pull_request_template.md`: Linked issue (`Closes #`), What changed (plain English), How it was tested, Screenshots (if UI), **Built with** (AI tool + model, e.g. "Claude Code — <model>"; feeds the Build Stack slide), Checklist (tests pass, lint passes, no secrets, scope limited to the issue, contract unchanged or `contract-change` label).
5. Verify the shipped review tooling (`.claude/agents/code-reviewer.md`, `.claude/commands/review.md`, `.claude/skills/review-prs/SKILL.md`): read them, check the `gh` commands are valid, list any fixes. Don't change the confirm-before-send / confirm-before-approve rules.
6. Commit "Add review tooling and checks (M07)"; PR; merge. Tell Mike that Secret scan, Critical files approval, and the advisory QA bot will all run on the dry-run PR in M08.

**Acceptance criteria**
- [ ] `ci.yml`, `secret-scan.yml`, `critical-files.yml`, `ai-qa-review.yml` in `.github/workflows/`
- [ ] QA bot secret set; bot is advisory (never fails on verdict; skips drafts/forks/Dependabot)
- [ ] Critical-files check uses `pull_request_target` with no checkout
- [ ] CODEOWNERS and PR template (with "Built with") present
- [ ] "What can I review?" and `/review` both start the review-prs skill

### M08 · Labels, issues, project board, full branch protection, dry run, assignments · M (2)

**Goal:** Turn the plan into GitHub issues, finish protecting `main`, prove the whole loop, and assign everyone their work.
**Read first:** TEAM_PROCESS Steps 2, 4, 5; [docs/plan/LANES.md](docs/plan/LANES.md).
**Manual prerequisite:** `gh auth refresh -s project` (so the CLI can create a project board).

**Do this** (show each write command before running it):

1. **Labels** (`gh label create --force`, so existing defaults like `good first issue` are updated rather than failing): `type: feature`, `type: bug`, `type: chore`, `size: S`, `size: M`, `size: L`, `status: blocked`, `good first issue`, `contract-change`, `needs-pm`, `re-review` (re-runs the advisory QA bot), `lane: mike|adam|gunnar|felipe|dillon`, `wave: 1|2|3|4`.
2. **Issues:** read `docs/plan/lane-2-adam.md` … `lane-5-dillon.md`. One issue per task (A01…D07): title "<ID> · <task name>"; body = Goal, Read first, Depends on ("Blocked by #n" once those exist), Acceptance criteria checklist, "Prompt: see docs/plan/<lane file> → <ID>". Labels: type, size, lane, wave. Show Mike the full list before creating. Also create closed issues M01–M07 linking their PRs, and an open M08 issue.
3. **Project board:** `gh project create --owner mlip3191 --title "Battle Royale"`, add all issues. Custom Status columns (Backlog, Ready, In progress, In review, Done) and the built-in workflows (item added → Backlog; PR merged → Done) need the web UI: give Mike the click path. Then set Wave 1 issues to Ready.
4. **Invites accepted?** `gh api repos/mlip3191/battleRoyale/invitations` must be empty (GitHub won't let you assign people who haven't accepted). If anyone is pending, give Mike their handle to nudge, and wait.
5. **Assign** every issue to its lane owner (A→`afondale`, G→`gunnaroc`, F→`felcervino`, D→`dilloncsmart`).
6. **Dry run** (before tightening the ruleset): issue "Dry run"; branch `issue-<n>-dry-run`; change one line in README.md; push; open a PR with the template. Wait for CI (4), Secret scan, Critical files approval, and the advisory QA bot to report. Run the review-prs skill as if Mike were the reviewer and show that it refuses (he's the author). Leave the PR open for Felipe's first review (F01).
7. **Full ruleset:** update the M02 ruleset: require a pull request with **1 approval**; required status checks with source GitHub Actions — `backend (ubuntu-latest)`, `backend (windows-latest)`, `frontend (ubuntu-latest)`, `frontend (windows-latest)` (use the exact names from M04), `Secret scan`, `Critical files approval`; block force pushes and deletions; no bypass actors. **Don't** require "branches up to date", "dismiss stale approvals", "approval of the most recent push", or "conversation resolution" — each adds re-runs or re-approvals the team can't afford (DECISIONS D-26). The QA bot is **not** a required check.
8. **Team board issue:** create and pin "Team board" (no chat channel): @mention all four with links to README "Teammate quick start", their lane file, their first issue, the dry-run PR to review, and the rule: once a week comment here with done / doing / blocked.
9. Append "Phase 0 done" to `docs/build-log.md` in a small PR that Felipe can review after the dry run (or include it in the dry-run PR).

**Acceptance criteria**
- [ ] Labels exist; one issue per task with type/size/lane/wave labels, dependencies, and assignee
- [ ] Project board live with Wave 1 in Ready
- [ ] Full ruleset active: 1 approval + 6 required checks; QA bot advisory only
- [ ] Dry-run PR shows all checks reporting; awaiting Felipe's review
- [ ] All invites accepted; pinned Team board issue posted

### After Phase 0 — Mike's ongoing duties

- Triage the board each Monday; split anything that turns out larger than M.
- Approve every PR that touches a critical file (then the skill re-runs the critical-files check).
- Own `docs/ARCHITECTURE.md` and `docs/DECISIONS.md`.
- Run `backend/scripts/smoke_providers.py` whenever an endpoint changes.
- Merge Dependabot PRs after CI and Secret scan pass (they also need your approval for lockfiles).
- Watch Actions minutes (Settings → Billing) weekly; if they run low, pause the nightly macOS run first.
- If Phase 0 slips past Nov 10, teammates can still start G01 (docs only) and their installs; nothing else in Wave 1 needs to wait more than a day.

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
