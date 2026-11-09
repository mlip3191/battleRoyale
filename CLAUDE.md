# CLAUDE.md — Battle Royale

Read this first in every session. It is a critical file: changes need PM (Mike) approval.

## 1. Project
**Battle Royale: The Science-Backed Fight Simulator** — a web app where users name two combatants; the app builds cited stat sheets from vetted sources, a Monte Carlo simulation in code decides the outcome, and the result plays as a corny late-night sports broadcast. **Corny voice, serious brain: no language model sets a number.**
Stack: Python 3.12 + FastAPI + Pydantic v2 + SQLite/sqlite-vec (`backend/`, uv); React + Vite + TypeScript + Phaser 3 (`frontend/`, Node 26, npm). No Docker: `npm start` runs the whole app at http://localhost:8000. All AI calls go to course-provided endpoints through `backend/app/providers/`.
Docs: `INIT.md` (Phase 0) · `docs/PROJECT_GUIDE.md` (start here) · `docs/PRODUCT_SPEC.md` · `docs/ARCHITECTURE.md` · `docs/TEAM_PROCESS.md` · `docs/DECISIONS.md` · `docs/plan/` (tasks and prompts per lane).
**Phase:** if `backend/` doesn't exist yet, we're in Phase 0 — follow `INIT.md`.

## 2. Commands (from the repo root; work the same on Windows and Mac — available after task M04)
- Install: `npm run setup` · Develop: `npm run dev` (backend :8000 + frontend :5173 with hot reload) · Run the finished app: `npm start` (builds the front end; backend serves everything at http://localhost:8000)
- Test + lint everything: `npm run check` · Format: `npm run format` · Regenerate API types: `npm run gen:api`
- Backend only: `uv run --directory backend pytest` · `.env` check: `npm run env:check` (never shows values) · Full environment check: `npm run doctor` (added by task D01)

## 3. Folders and protected files
`backend/app/` modules: models (contracts), providers, safety, intake, research, simulation, narration, media, pipeline, api, db. `backend/prompts/` holds every prompt. `frontend/src/`: api, pages, components, game (Phaser), fixtures. `data/seed/`, `data/benchmark/`, and `data/showcase/` are committed; `data/app.db`, `data/kb/`, `data/media/` are generated and ignored.
**Protected (PM approval; the list in `.github/CODEOWNERS` is authoritative):** CLAUDE.md, INIT.md, .claude/, .github/, .githooks/, .gitignore, .gitattributes, .editorconfig, .nvmrc, .env.example, .mcp.json, .gitleaks.toml, .gitleaksignore, root `scripts/` (not `backend/scripts/`), all package.json / lockfiles / pyproject.toml / uv.lock, `backend/app/config.py`, `backend/app/models/`, `docs/ARCHITECTURE.md`.

## 4. Conventions
- Python: ruff format + ruff check, type hints everywhere, snake_case. TypeScript: ESLint + Prettier, camelCase, components PascalCase. Files: lowercase-with-dashes (Python modules snake_case).
- Small functions with a one-line comment on intent. Prompts live in `backend/prompts/*.md`, never inline strings.
- Only `backend/app/config.py` reads environment variables. Only `backend/app/providers/` calls course endpoints. The front end only calls our own `/api` and `/media`.
- Front-end API types are generated (`npm run gen:api`); never hand-write them.
- Banned without a PM-approved issue: LangChain/LlamaIndex, paid API SDKs, new databases, CSS frameworks, any model call from the front end.

## 5. Rules for working with non-coders (every session)
- Never work on `main` (only exception: INIT.md task M02). Branch per issue: `issue-<number>-short-description`. One issue at a time; don't expand scope — suggest a new issue (`/new-issue`) instead.
- Before changing anything, explain the plan in plain English and wait for a yes. After, summarize what changed and why.
- Run `npm run check` before every commit; don't commit if it fails. Never delete, skip, or weaken a test to make it pass — explain the failure.
- Never touch files outside the task's scope. Ask before adding any dependency.
- Never run destructive commands without explicit confirmation: no force push, `git reset --hard`, deleting branches/folders, or dropping databases.
- If a git command fails or conflicts, stop, explain in plain English, propose a fix.
- Before switching tasks or branches, make sure work is committed or stashed, and say so.
- Commit messages: imperative summary + issue, e.g. `Add matchup count clamping (#12)`. PRs under ~300 changed lines, using the PR template, with `Closes #<n>`. Merge only after a teammate approves and all checks pass.
- Write long text (commit messages, PR/issue bodies, comments) to a file in `.claude/tmp/` and pass it with `git commit -F` / `--body-file`; the shell guard ignores message text only when it isn't on the command line as a path-like word.
- If unsure, stop and ask.

## 6. Battle Royale rules
- **Number rule:** a model may only copy a number together with the exact quote it came from, and code verifies it. Estimates come from code and are labeled `is_estimate`. Scripts may only contain numbers present in the stat sheets or results.
- **Contracts:** shapes in `backend/app/models/` are shared by all lanes. Don't change them without an issue labeled `contract-change` and PM approval. Until a module exists, use its fixture in `backend/tests/fixtures/contracts/`.
- **Mocks:** every provider has a mock; tests and CI run with `PROVIDER_MODE=mock`. Live calls have timeouts, retries, and a fallback.
- **Simulation:** all randomness from the seeded generator; bump `ENGINE_VERSION` when results change.
- **Safety and tone:** no real people, minors, groups of people, named fictional characters, deities, firearms/explosives, or abstract ideas, places, landforms, or celestial bodies as fighters (objects, machines, and mythical creature types are fine — DECISIONS D-38); PG — no gore; no real artists, songs, franchises, or characters in media prompts; voice cloning only with written consent.

## 7. Testing and Definition of Done
Every feature or fix has at least one test (`backend/tests/{unit,contract,golden,property}`, `frontend/src/**/*.test.tsx`). A bug fix starts with a failing test. **Done** = the issue's acceptance criteria all met, `npm run check` passes, the app still starts, the PR explains the change in plain English, docs updated if behavior changed.

## 8. Secrets and environment (private repo — but treat every commit as if it were public)
- All config comes from `.env` (never committed), documented in `.env.example` with a comment and placeholder per variable. New variable → add it to `.env.example` and tell the user how to get the value.
- Never put keys **or course endpoint hosts** in code, tests, fixtures, docs, logs, or `.mcp.json` (use `${VAR}` there).
- Never read, print, or edit `.env`. Never `git add -f`, `--no-verify`, or edit `.gitignore`/`.githooks/` to let a file through. Never print environment variables.
- If the pre-commit hook or Secret scan blocks a commit, explain why and move the value into `.env`. If you see something that looks like a real key, stop and tell the user to alert the PM — don't copy or move it.

## 9. Reviews and issues
- To review: the user asks "What can I review?" or types `/review [n]` → use the **review-prs** skill. Nothing is posted until the user says send; approval is a separate confirmation.
- To check your own work: the user types `/qa [n]` (or asks "check my work before I open a PR") → run the **/qa** self-check. It works on your own branch or PR and posts nothing.
- The QA bot, /review, and /qa all follow **`.claude/qa/checklist.md`** on the same model, so they agree. Change the checklist, not the individual tools.
- The QA bot on GitHub is **advisory**. Treat its comments as suggestions; a teammate's approval and the required checks (CI, Secret scan, Critical files approval) are the gate. To have it look again after fixes, add the `re-review` label.
- Work only on an assigned issue; read its acceptance criteria and its task in `docs/plan/` first. If it's bigger than size M or unclear, stop and suggest splitting or clarifying.

## 10. Permissions and hooks
`.claude/settings.json` enforces these rules; the hooks in `.claude/hooks/` are the real enforcement (permission rules only match command prefixes). Never suggest bypassing them or changing them outside a PM-approved PR. Bypass-permissions mode is disabled.
- **Blocked:** reading or changing `.env` files (anything but `.env.example`), `*.pem`, `*.key`; printing environment variables; commits on `main`; pushing to `main`, force pushes, deleting remote branches; `git add -f`, `git commit --no-verify`/`-n`; `git reset --hard`, `git clean`, `git branch -D`, discarding changes (`git checkout -- <path>`, `git restore` without `--staged`); changing `core.hooksPath`; `rm -rf`, `Remove-Item -Recurse`; `sudo`. If a guard itself errors, the command is blocked to be safe.
- **Asks first:** every `gh api` call, installing packages, `gh` commands that write (PRs, issues, reviews, merges, labels, workflow runs, projects), and edits to critical config (`.github/`, `.claude/`, `.githooks/`, `scripts/`, CLAUDE.md, INIT.md, `.gitignore`, `.gitattributes`, `package.json`, `pyproject.toml`).
- **Automatic:** before any commit, `core.hooksPath` is set to `.githooks`; edited `.py` files are formatted with ruff and `frontend/` files with prettier. Test the hooks with `node .claude/hooks/test-hooks.mjs`.
- **Long text goes through files:** write commit messages, PR/issue bodies, and comments to `.claude/tmp/` and pass them with `-F` / `--body-file`, so the guard never mistakes message words for file paths.
