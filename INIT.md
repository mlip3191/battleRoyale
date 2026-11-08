# INIT.md — initialize the Battle Royale project

**Give this one document to Claude Code.** Open Claude Code in an empty folder or in a clone of the repo and say:

> Read INIT.md and follow it.

It takes the project from "plan only" to a protected repo with a running skeleton, CI, review tooling, every task filed as a GitHub issue, and the team invited. It runs **Phase 0 (tasks M01–M08)** one task at a time and stops for Mike's OK at every step.

---

## Part 1 — For Mike, before starting (about 15 minutes, by hand)

1. **Install and sign in** (Windows or Mac): Git, GitHub CLI (`gh auth login` as `mlip3191`), Claude Code (`claude`), Node 24, uv. (No Docker needed.)
2. **GitHub Pro:** claim it through the GitHub Student Developer Pack (education.github.com) and confirm at github.com/settings/billing. Needed because the repo is going private (D-01).
3. **Get the code:** `git clone https://github.com/mlip3191/battleRoyale.git` then `cd battleRoyale` (Claude can do this for you in Step 0 below).
4. **Create your `.env` with the course endpoints** — the most important manual step:
   - Copy the template — Windows: `copy .env.example .env` · Mac: `cp .env.example .env`
   - Open `.env` in VS Code or Notepad. Fill **every line marked `[required]`**: `COURSE_API_KEY`, each service URL as `http(s)://<host>:<port>` (chat 9001, embeddings 9002, document parsing 9005, image 9006, plus structured decisions, reranking, text-to-speech, and music from the course list), and the model names. If a service has its own key, add `<SERVICE>_API_KEY=` (e.g. `TTS_API_KEY=`).
   - Set `PROVIDER_MODE=live`.
   - Check it: `node scripts/check-env.mjs` — it lists anything missing or malformed and **never prints your values**. Repeat until it says all required values are filled in.
   - Never paste these values into GitHub, a commit, an issue, a PR, or a Claude chat. `.env` is ignored by git.
5. **Have ready for later steps:** a few minutes to run `claude setup-token` (QA bot secret, step M07).

---

## Part 2 — Instructions for Claude Code

You are the build assistant for **Battle Royale: The Science-Backed Fight Simulator**, the MBAX 6418 final project of **Group A**: Mike Lippert (PM, `mlip3191`, Windows + Mac), Adam Fondale (`afondale`), Gunnar O'Connor (`gunnaroc`), Felipe Cervino (`felcervino`), Dillon Smart (`dilloncsmart`) — all four teammates are non-coders on Windows. Mike is the only one with coding experience.

### Step 0 — Orient

1. If the current folder is not a clone of `mlip3191/battleRoyale` (no `CLAUDE.md` and no `docs/` here), run `gh repo clone mlip3191/battleRoyale` and work inside that folder from now on.
2. `git pull` so you have the latest `main`.
3. Read, in order: `CLAUDE.md`, `docs/PROJECT_GUIDE.md`, `docs/PRODUCT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/TEAM_PROCESS.md`, `docs/DECISIONS.md`, `docs/plan/LANES.md`, `docs/plan/DELIVERABLES.md`.
4. Give Mike a 10-line summary of what we're building and how Phase 0 works. List any contradiction or gap you found between the documents, with a recommended fix. Wait for his answers.
5. **Check the `.env`:** run `node scripts/check-env.mjs`. Never open, print, or edit `.env` yourself. If it reports problems, show Mike the report and walk him through Part 1 step 4; wait until it passes. (Mock mode still works without it, but M06 needs it.)
6. The project is **due Wednesday, November 25**; the day-by-day schedule is in `docs/plan/DELIVERABLES.md` and `docs/plan/LANES.md`. Phase 0 is planned for Nov 9–10, so keep each task moving and flag anything that threatens that.

### Rules for this session

- Do tasks **M01 → M08 strictly in order, one at a time.** For each task:
  1. Say which task you're starting and show its acceptance criteria.
  2. Follow its "Do this" steps exactly, including every confirmation point.
  3. When something must be done by hand (a GitHub setting, a secret, a billing check), stop, give Mike a numbered checklist, and wait.
  4. Verify every acceptance criterion and show the evidence.
  5. Commit with the message the task gives:
     - **M01–M02:** commit directly to `main` (the guardrails that block this don't exist yet).
     - **M03–M08:** create a branch `phase0-<task id lowercase>` (e.g. `phase0-m04`), commit there, push, open a PR with `gh pr create` (title = the commit message), wait for any checks that exist, then merge with `gh pr merge --squash --delete-branch` after Mike confirms. Mike may merge his own Phase 0 PRs because branch protection only starts in M08. Each "Commit: …" line below means this flow. This also gives the instructor the step-by-step history the Final Project Overview asks for.
  6. Ask "Ready for the next task?" and wait.
- If anything fails, stop, explain it in plain English, and propose a fix. Never skip a guardrail, never use `--no-verify` or `git add -f`, never force push.
- Never read, print, or edit `.env`, and never put endpoint hosts or keys in any file, commit, or message.

---

## Part 3 — Phase 0 tasks (Mike's lane, 14 points)

| ID | Task | Size |
|---|---|---|
| M01 | GitHub repo settings, security, and Actions permissions | S |
| M02 | Verify guardrail files, switch on the git hook, finalize CLAUDE.md | S |
| M03 | Claude Code settings, permissions, and hooks | M |
| M04 | Monorepo skeleton, toolchain pins, cross-platform files, CI | M |
| M05 | Shared contracts: Pydantic models, JSON Schema, fixtures, TS types | M |
| M06 | Provider layer: interfaces, mocks, config, live chat adapter, smoke test | M |
| M07 | Review tooling: QA bot, Secret scan, critical-files check, CODEOWNERS, PR template | M |
| M08 | Labels, issues from the plan, project board, branch protection, dry run, invites | M |

### M01 · GitHub repo settings, security, and Actions permissions · S (1)

**Goal:** Configure the repo so it is safe before any code lands.
**Read first:** TEAM_PROCESS Step 0 and Step 10; DECISIONS D-01 (private + GitHub Pro).
**Manual prerequisites:** GitHub CLI logged in as `mlip3191` (`gh auth status`); **GitHub Pro active** on the account (claim it through the GitHub Student Developer Pack at education.github.com, then confirm at github.com/settings/billing).

**Do this:**

Configure the GitHub repository mlip3191/battleRoyale using the GitHub CLI. For each change, show me the exact gh command first and run it only after I confirm. If a command fails or the API is not available for this account, stop and give me the exact click path in the GitHub web UI instead.

0. Confirm GitHub Pro is active on my account (ask me to check github.com/settings/billing; do not continue until I confirm). Then make the repo private: gh repo edit mlip3191/battleRoyale --visibility private --accept-visibility-change-consequences. Turn off "Allow forking".
1. Merge settings: squash merge only (disable merge commits and rebase merges), "Always suggest updating pull request branches" on, "Automatically delete head branches" on.
2. Security: turn on Dependabot alerts and Dependabot security updates. GitHub secret scanning and push protection are not available for private personal repos; confirm that, and remind me that the gitleaks Secret scan (M07) and the local hook cover it.
3. Actions: set default workflow permissions to read-only, and make sure "Allow GitHub Actions to create and approve pull requests" is OFF. Restrict allowed actions to GitHub-made actions plus these patterns: anthropics/claude-code-action@*, gitleaks/gitleaks-action@*, astral-sh/setup-uv@*.
4. Print a final table of every setting with its current value, read back from the API, so I can confirm.

Do not create branch protection yet; that is task M08.

**Acceptance criteria**
- [ ] Squash-only merging, auto-delete head branches, update-branch suggestion on
- [ ] Repo is private, GitHub Pro active, forking off
- [ ] Dependabot alerts + security updates on
- [ ] Default `GITHUB_TOKEN` is read-only; Actions cannot approve PRs; allowed-actions list set
- [ ] Settings table pasted into the M01 issue/notes

**Check it yourself:** Settings → General / Code security / Actions show the values in the table.

---

### M02 · Verify guardrail files, switch on the git hook, finalize CLAUDE.md · S (1)

**Goal:** Prove the secret guardrails already in the repo work on your machine, and make CLAUDE.md match reality.
**Read first:** TEAM_PROCESS Step 8; CLAUDE.md.

**Do this:**

1. Run: git config core.hooksPath .githooks — then confirm .githooks/pre-commit is marked executable in git (git ls-files -s .githooks/pre-commit should show mode 100755; if not, run git update-index --chmod=+x .githooks/pre-commit).
2. Prove the hook works without leaking anything: create a temporary file tmp-hook-test.txt containing the text sk-ant- followed by 30 random letters, stage it, try to commit, show me that the commit was blocked and that the key text was NOT printed. Then unstage and delete the file. Do the same with a file named .env forced with git add -f, then unstage and delete it.
3. Run git ls-files --cached --ignored --exclude-standard and confirm it prints nothing.
4. Read CLAUDE.md fully. List anything that is wrong, missing, or contradicts docs/ARCHITECTURE.md or docs/TEAM_PROCESS.md, and propose exact edits. Keep it under two pages. Apply only the edits I approve.
5. Commit with message "Verify guardrails and finalize CLAUDE.md (M02)".

**Acceptance criteria**
- [ ] Hook blocks a fake key and a force-added `.env`, and never prints the key
- [ ] Hook file mode is 100755 in git
- [ ] No tracked file matches an ignore rule
- [ ] CLAUDE.md reviewed and committed

---

### M03 · Claude Code settings, permissions, and hooks · M (2)

**Goal:** Enforce the CLAUDE.md rules with settings, so a non-coder can't accidentally approve something dangerous.
**Read first:** TEAM_PROCESS Step 7.

**Do this:**

Create the shared Claude Code configuration. Use the current, documented Claude Code settings syntax; if you are unsure of a field name, check the official Claude Code settings and hooks documentation before writing it.

1. Create .claude/settings.json with:
   - allow: Read/Grep/Glob of the repo; running our project scripts (npm run setup|dev|test|lint|format|check|gen:api, uv run pytest, uv run ruff); git status, diff, log, branch, switch, checkout, add (not -f), commit, pull, fetch, stash, push of the current branch; read-only gh commands (gh pr view|list|diff|checks, gh issue view|list, gh api with GET).
   - ask: installing or upgrading packages (uv add, npm install <pkg>), editing files under .github/, .claude/, .githooks/, CLAUDE.md, .gitignore, package.json, pyproject.toml; any gh command that writes (gh pr create|review|merge|comment, gh issue create|edit, gh api with POST/PUT/PATCH/DELETE).
   - deny: Read of .env, .env.local, .env.development, .env.production, .env.test, .env.*.local and **/*.pem, **/*.key (list .env files by exact name so .env.example stays readable); the shell forms of reading those files (cat, type, more, head, tail, grep, Get-Content); git push --force and -f; git reset --hard; git branch -D; git push to main; git add -f / --force; git commit --no-verify / -n; git config core.hooksPath; rm -rf / Remove-Item -Recurse; sudo; printenv and env.
   - permissions.disableBypassPermissionsMode set to "disable".
2. Add hooks, each written as a Node.js script in .claude/hooks/ (Node is already required for the front end, so it runs the same on Windows and Mac):
   - PreToolUse on shell commands: block "git commit" when the current branch is main.
   - PreToolUse on shell commands: block any command that mentions a .env file other than .env.example, or a *.pem/*.key file, with the message "Claude isn't allowed to read secrets. Ask the PM."
   - PreToolUse on shell commands: before git commit, if git config core.hooksPath is not .githooks, set it and say so.
   - PostToolUse on file edits: run the right formatter on the edited file (ruff format for .py, prettier for .ts/.tsx/.css/.json/.md under frontend/) — skip silently if the formatter isn't installed yet.
3. Confirm .claude/settings.local.json and CLAUDE.local.md are in .gitignore (they are).
4. Add a short "Permissions and hooks" section to CLAUDE.md: they exist, what they block, and that Claude must never suggest bypassing them.
5. Test every hook and show me the result of each test (blocked/allowed and the message). Then explain each permission rule in plain English in a table.
6. Commit: "Add shared Claude Code settings and hooks (M03)".

**Acceptance criteria**
- [ ] Commit on `main` is blocked by the hook (after M08 this matters for everyone)
- [ ] `cat .env` and `type .env` are blocked; reading `.env.example` works
- [ ] `--no-verify`, `git add -f`, force push are denied
- [ ] Formatter hook runs (or skips quietly before M04)
- [ ] Plain-English permission table pasted in the PR/issue

---

### M04 · Monorepo skeleton, toolchain pins, cross-platform files, CI · M (2)

**Goal:** Empty-but-running backend and front end, one set of commands that work the same on Windows and Mac, and CI on all three OSes.
**Read first:** ARCHITECTURE §2–3; TEAM_PROCESS Step 6.

**Do this:**

Build the project skeleton exactly as laid out in docs/ARCHITECTURE.md sections 2 and 3. Ask me before installing anything not listed there.

Backend (backend/):
- uv project, Python 3.12 pinned in backend/.python-version, uv.lock committed.
- Dependencies: fastapi, uvicorn[standard], pydantic, pydantic-settings, httpx, sqlite-vec. Dev: pytest, pytest-asyncio, hypothesis, ruff.
- app/main.py with an app factory, CORS for FRONTEND_ORIGIN, and GET /api/health returning {"status":"ok"}. When frontend/dist exists, also serve it as static files at / (with index.html as the fallback for front-end routes), so npm start needs only one process and one port.
- app/config.py: a Settings class (pydantic-settings) reading .env; the only module allowed to read environment variables.
- Empty packages with __init__.py and a one-line docstring for: models, providers, safety, intake, research, simulation, narration, media, pipeline, api, db. Create backend/prompts/, backend/scripts/, backend/tests/{unit,contract,golden,property,fixtures}.
- ruff config (line length 100, import sorting on) and pytest config in pyproject.toml. One passing test for /api/health.

Front end (frontend/):
- Vite + React + TypeScript template, Node 24 pinned in the root .nvmrc and "engines" in package.json, package-lock.json committed.
- Add phaser, vitest, @testing-library/react, jsdom, eslint, prettier, openapi-typescript.
- Folders: src/api, src/pages, src/components, src/game, src/fixtures. A Home page that calls /api/health through the Vite dev proxy and shows "Backend: ok".
- One passing Vitest test.

Root:
- package.json scripts (cross-platform; use the concurrently package for dev): setup (uv sync in backend + npm ci in frontend), dev (backend on :8000 and frontend on :5173 together, with hot reload), start (the one-command way to run the finished app: build the front end, then run the backend, which serves the built files and the API together at http://localhost:8000 — print that URL when it's ready), test, lint, format, check (lint + test for both), gen:api (export OpenAPI from the backend and generate frontend/src/api/schema.d.ts), env:check (node scripts/check-env.mjs).
- .gitattributes (* text=auto eol=lf; *.bat and *.cmd eol=crlf; images/audio binary), then git add --renormalize .
- .editorconfig (utf-8, lf, final newline, 2 spaces; 4 spaces for .py).
- Keep the existing .gitignore; do not remove any rule.

CI: create .github/workflows/ci.yml that runs on pull_request and push to main, with jobs named "backend" and "frontend", each on a matrix of ubuntu-latest, windows-latest, macos-latest for pull requests and ubuntu-latest only for pushes to main (private repo: macOS minutes count 10x against our quota), with concurrency cancel-in-progress per branch, using the pinned versions (astral-sh/setup-uv and actions/setup-node with node-version-file: .nvmrc), PROVIDER_MODE=mock, permissions: contents: read. Steps: install from lockfiles, lint, test.

Finally: run npm run setup and npm run check locally and show me the output, tell me the exact CI check names that will appear on PRs, and update the Commands section of CLAUDE.md with the real commands. Commit: "Add monorepo skeleton and CI (M04)".

**Acceptance criteria**
- [ ] `npm run setup`, `npm run dev`, `npm run check` work on Mike's machine
- [ ] Browser at http://localhost:5173 (dev) shows "Backend: ok"
- [ ] `npm start` serves the same page at http://localhost:8000 from one process, on Windows and Mac
- [ ] CI is green on all 6 matrix jobs
- [ ] CLAUDE.md Commands section updated with real commands

---

### M05 · Shared contracts: Pydantic models, JSON Schema, fixtures, TS types · M (2)

**Goal:** Lock the shapes every lane builds against, so five people can work in parallel without waiting on each other.
**Read first:** ARCHITECTURE §5 (normative), §14.

**Do this:**

Implement every model in docs/ARCHITECTURE.md section 5 in backend/app/models/ (one module per heading: terrain, matchup, stats, simulation, narration, media, battle), with the exact field names, types, and constraints shown. Add docstrings that explain each field in plain English.

Also:
1. Validators: StatSheet must contain every StatName; a StatValue with is_estimate=True must have source=None and confidence="low"; a StatValue with method="extracted" must have a source whose quote is non-empty; Matchup must have exactly 2 fighters for now.
2. backend/scripts/export_schema.py writes JSON Schema for every model to backend/app/models/schema/*.json.
3. One realistic, valid fixture per model in backend/tests/fixtures/contracts/ (use "grizzly bear (adult male)" vs "6 gray wolves" on "forest" as the running example; make the stats plausible and give every extracted value a Wikipedia URL and quote). Include a BattleRecord fixture in "running" state and one in "done" state.
4. backend/tests/contract/: every fixture validates; the validators reject bad examples (one test per rule).
5. Copy the fixtures to frontend/src/fixtures/ via an npm script (fixtures:sync) and make npm run gen:api produce TypeScript types the front end can import.
6. Add a short "Contracts" section to CLAUDE.md: models/ is critical; changing it needs an issue labelled contract-change and PM approval.
Run npm run check, then commit: "Add shared contracts and fixtures (M05)".

**Acceptance criteria**
- [ ] All models match ARCHITECTURE §5 exactly
- [ ] JSON Schema exported; fixtures validate; negative tests pass
- [ ] Front end can import generated types and fixtures
- [ ] `backend/app/models/` added to critical files list

---

### M06 · Provider layer: interfaces, mocks, config, live chat adapter, smoke test · M (2)

**Goal:** One clean way to call every course endpoint, a mock for each, and real facts about how the endpoints behave.
**Read first:** ARCHITECTURE §7, §13; `.env.example`.
**Manual prerequisite:** `.env` filled from `.env.example` and `node scripts/check-env.mjs` passes (DECISIONS D-03).

**Do this:**

Build backend/app/providers/ as described in docs/ARCHITECTURE.md section 7.

1. base.py: an abstract interface (Protocol) for each provider in the table: ChatLLM, StructuredLLM, Embedder, Reranker, DocParser, ImageGen, TTS, MusicGen. Async methods with type hints and docstrings.
2. mock/: a deterministic mock for every interface, as described in the "Mock behavior" column. Mocks never touch the network. Canned chat responses live as JSON files in backend/tests/fixtures/providers/ keyed by prompt name.
3. registry.py: get_provider(name) returns the mock or the live adapter based on settings.provider_mode. Add every variable from .env.example to Settings, including the *_MODEL names. Keys: each service uses <SERVICE>_API_KEY if set, otherwise COURSE_API_KEY; send it the way the smoke test finds the endpoint expects (e.g. Authorization: Bearer). Live mode fails fast with a clear message naming any missing variable (never its value).
4. backend/scripts/smoke_providers.py: for every service whose URL is set, make one tiny request, try the common discovery paths (/v1/models, /docs, /openapi.json, /health), and write what it learned (base URL shape with the host redacted, auth needed or not, request/response format, latency) to docs/providers.md. Never print or write keys or full URLs with hosts.
5. live/chat.py: a live ChatLLM adapter using httpx, with a 30 s timeout, 2 retries with backoff, and optional JSON-schema mode. Assume an OpenAI-compatible /v1/chat/completions API only if the smoke test confirms it; otherwise stop and show me what the smoke test found.
6. GET /api/health returns provider_mode and, for each provider, "mock", "up", or "down" (live mode does a cached 2 s ping).
7. Tests: every mock satisfies its interface; registry picks mock by default; live adapters are skipped in CI.
Run the smoke script, show me docs/providers.md, run npm run check, then commit: "Add provider layer and mocks (M06)".

**Acceptance criteria**
- [ ] Every provider has an interface and a mock; CI runs fully on mocks
- [ ] `docs/providers.md` documents what each reachable endpoint actually expects (no hosts, no keys)
- [ ] Live chat adapter works against port 9001 from Mike's machine
- [ ] `/api/health` shows per-provider status

---

### M07 · Review tooling: QA bot, Secret scan, critical-files check, CODEOWNERS, PR template · M (2)

**Goal:** Every PR is checked by the QA bot and the secret scan on GitHub, and critical files need the right approver.
**Read first:** TEAM_PROCESS Steps 2, 3, 8, 9; `.claude/skills/review-prs/SKILL.md`; `.claude/agents/code-reviewer.md`.
**Manual prerequisite:** add the QA bot secret (DECISIONS D-04): run `claude setup-token` on your machine, then Settings → Secrets and variables → Actions → New repository secret `CLAUDE_CODE_OAUTH_TOKEN`. Paste it only into GitHub, never into chat or a file. Every bot run uses your Claude plan's limits.

**Do this:**

1. Install the workflow templates: copy setup/templates/workflows/secret-scan.yml and setup/templates/workflows/ai-qa-review.yml into .github/workflows/. ai-qa-review.yml already uses CLAUDE_CODE_OAUTH_TOKEN (DECISIONS D-04); confirm the secret exists with gh secret list. This repo is owned by a personal account, so gitleaks needs no license.
2. Create .github/CODEOWNERS assigning these critical paths to @mlip3191: CLAUDE.md, .claude/, .github/, .githooks/, .gitignore, .gitattributes, .editorconfig, .nvmrc, .env.example, package.json, package-lock.json, frontend/package.json, frontend/package-lock.json, backend/pyproject.toml, backend/uv.lock, backend/app/models/, docs/ARCHITECTURE.md.
3. Create .github/workflows/critical-files.yml with a job named "Critical files approval" that runs on pull_request (opened, synchronize, reopened) and pull_request_review (submitted, dismissed), permissions contents: read and pull-requests: read. Using gh, it checks whether the PR changes any CODEOWNERS path. If it does and the PR author is not mlip3191, it fails unless mlip3191 has an APPROVED review on the PR's latest commit. In every other case it passes. Print a plain-English reason either way.
4. Create .github/pull_request_template.md with sections: Linked issue (Closes #), What changed (plain English), How it was tested, Screenshots (if UI), Built with (AI tool and model, e.g. "Claude Code — <model>"; this feeds the Build Stack slide), Checklist (tests pass, lint passes, no secrets, scope limited to the issue, contract unchanged or contract-change label added).
5. Verify the shipped review tooling: .claude/agents/code-reviewer.md, .claude/commands/review.md, and .claude/skills/review-prs/SKILL.md. Read them, check that the gh commands they use are valid, and list any fixes needed. Do not change the confirm-before-send and confirm-before-approve rules.
6. Commit: "Add review tooling and required checks (M07)". Then tell me how to see the three new checks run (they will run on the dry-run PR in M08).

**Acceptance criteria**
- [ ] `secret-scan.yml`, `ai-qa-review.yml`, `critical-files.yml`, `ci.yml` all in `.github/workflows/`
- [ ] QA bot secret set; CODEOWNERS and PR template present
- [ ] `/review` and "what can I review?" both start the review-prs skill

---

### M08 · Labels, issues from the plan, project board, branch protection, dry run, invites · M (2)

**Goal:** Turn the plan into GitHub issues, lock `main`, prove the whole loop works, and bring the team in.
**Read first:** TEAM_PROCESS Steps 2, 4, 5; [docs/plan/LANES.md](docs/plan/LANES.md).
**Manual prerequisites:** `gh auth refresh -s project` so the CLI can create a project board. Handles: `afondale`, `gunnaroc`, `felcervino`, `dilloncsmart` (DECISIONS team table).

**Do this:**

Show me each write command before running it.

1. Labels (gh label create, distinct color per group): type: feature, type: bug, type: chore, size: S, size: M, size: L, status: blocked, good first issue, contract-change, needs-pm, and one label per lane: lane: mike, lane: adam, lane: gunnar, lane: felipe, lane: dillon; and wave: 1, wave: 2, wave: 3, wave: 4.
2. Issues: read docs/plan/lane-2-adam.md through lane-5-dillon.md. Create one GitHub issue per task (A01…D07). Title "<ID> · <task name>". Body: Goal, Read first, Depends on (as "Blocked by #n" once those issues exist), Acceptance criteria as a checklist, and a line "Prompt: see docs/plan/<lane file>#<ID>". Labels: type, size, lane, wave. Leave assignee empty for now; I will assign after invites. Show me the full list before creating anything. Also create closed issues M01–M07 summarizing what was done, and an open M08 issue.
3. Project board: create a GitHub Project "Battle Royale" owned by mlip3191 with Status columns Backlog, Ready, In progress, In review, Done; add all issues; Wave 1 issues go to Ready. Tell me the two built-in workflows to turn on by hand (item added → Backlog; PR merged → Done).
4. Branch protection: create a repository ruleset for main (gh api repos/mlip3191/battleRoyale/rulesets) with: require a pull request, 1 approval, dismiss stale approvals, require approval of the most recent push, require conversation resolution, required status checks (source GitHub Actions): "AI QA Review", "Secret scan", "Critical files approval", and the six CI checks from M04; require branches to be up to date; block force pushes and deletions; no bypass actors. Only add checks that have already run at least once — if one hasn't, open the dry-run PR first (step 5) and add it after.
5. Dry run: create issue "Dry run", branch issue-<n>-dry-run, change one line in README.md, push, open a PR with the template. Wait for CI, Secret scan, AI QA Review, and Critical files approval to report. Then run the review-prs skill as if I were a reviewer and show me it refuses because I am the author. Leave the PR open for the first teammate to review and approve.
6. Invites: for afondale, gunnaroc, felcervino, dilloncsmart run gh api -X PUT repos/mlip3191/battleRoyale/collaborators/<handle> -f permission=push, then assign their Wave 1 issue (A01 afondale, G01 gunnaroc, F01 felcervino, D01 dilloncsmart) and set assignees on all their later issues. Then tell me to invite the instructor by email in the web UI (Settings → Collaborators → Add people → david.dobolyi@colorado.edu) — required because the repo is private.
7. Create and pin a "Team board" issue (we have no chat channel): @mention all four teammates with links to README "Teammate quick start", their lane file, their first issue, the dry-run PR to review, and the weekly check-in rule (comment here: done / doing / blocked).

**Acceptance criteria**
- [ ] All labels exist; one issue per task with lane/wave/size labels and dependencies
- [ ] Project board live with Wave 1 in Ready
- [ ] Ruleset active on `main` with all required checks; direct push to `main` rejected
- [ ] Dry-run PR shows all checks reporting
- [ ] All four teammates invited with Write access and assigned their issues
- [ ] Instructor invited (david.dobolyi@colorado.edu)
- [ ] Pinned Team board issue posted

---

### After Phase 0 — Mike's ongoing duties (not pointed)

- Triage weekly: move ready issues to Ready, split anything that turns out L.
- Approve every PR that touches a critical file (the critical-files check enforces it).
- Own `docs/ARCHITECTURE.md` and `docs/DECISIONS.md`; record each decision.
- Run `scripts/smoke_providers.py` whenever an endpoint changes.
- Merge Dependabot PRs after CI and the QA bot pass.

---

## Part 4 — What happens next (Claude: give Mike this briefing after M08, with real issue numbers and links)

1. **Kickoff (30 min, video call).** Mike shares his screen: the project board, one lane file, the dry-run PR. Everyone does the README "Teammate quick start", including creating their `.env` and running `node scripts/check-env.mjs`.
2. **Wave 1 (Wed Nov 11):** each teammate's setup task — A01 (Adam), G01 (Gunnar), F01 (Felipe, includes reviewing the dry-run PR with the review-prs skill), D01 (Dillon).
3. **Waves 2–4:** teammates pick their next issue from **Ready**; every task's prompt is in their lane file (`docs/plan/lane-2-adam.md` … `lane-5-dillon.md`). Mike moves issues to Ready as dependencies merge.
4. **Weekly:** Monday, Mike triages the board. Mid-week, everyone comments on the pinned Team board issue (done / doing / blocked). Friday, after F07 exists, run the benchmark and review `docs/benchmark-results.md`.
5. **Milestones:** MS-1 walking skeleton (end of Wave 2) → MS-2 real brain (Wave 3) → MS-3 the show (Wave 4) → MS-4 demo-ready. Mike adds three lines to `docs/build-log.md` at each.
6. **Deliverables:** feature freeze, bug bash, deck, rehearsals, and Canvas submission per `docs/plan/DELIVERABLES.md`.
7. **Prompts teammates use:**
   - Start a task: *"Start work on issue #<n>. Read the task in docs/plan/<my lane file> under its ID, follow its prompt, and check off its acceptance criteria before opening the PR."*
   - Review: *"What can I review?"*
   - New work: `/new-issue` (after A01)
