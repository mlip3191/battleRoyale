# Battle Royale: The Science-Backed Fight Simulator

**Corny voice, serious brain.** Name two combatants in plain language — *"100 duck-sized horses vs 1 horse-sized duck"* — and the app researches each one from vetted sources into a cited stat sheet, a simulation written in code decides the outcome, and the result plays as a cheesy late-night sports broadcast with an announcer, a soundtrack, and a crude animated battle. Every stat links to its source; gaps are labeled as estimates. No language model sets a number.

MBAX 6418 AI Business Solutions — final project, **Group A**: Mike Lippert (PM), Adam Fondale, Gunnar O'Connor, Felipe Cervino, Dillon Smart.

> **Status: Phase 0 done.** The skeleton runs (`npm start`), every task is an issue on the [project board](https://github.com/users/mlip3191/projects/2), and Wave 1 starts Wed Nov 11.

## Start here

| You are | Do this |
|---|---|
| **Mike** | Give [INIT.md](INIT.md) to Claude Code — it initializes the whole project |
| **A teammate** | Follow the quick start below, then your lane file in [docs/plan/](docs/plan/LANES.md) |
| **Anyone** | [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md) explains everything in order |

## Teammate quick start

1. GitHub account with two-factor authentication on. Send Mike your username and OS. Accept the repo invite.
2. Install Git, GitHub CLI (`gh auth login`), Claude Code (`claude`), Node 26, and uv.
3. `git clone https://github.com/mlip3191/battleRoyale.git` then `cd battleRoyale`
4. `git config core.hooksPath .githooks` — switches on the guard that blocks keys and `.env` files from being committed. (After setup is finished, `npm run setup` does this for you.)
5. Copy `.env.example` to `.env` (Windows: `copy .env.example .env`) and fill every `[required]` line with the course endpoint URLs, ports, and keys you already have. Check it with `node scripts/check-env.mjs` — it never shows your values.
6. Run `claude` in the folder and say: *"Read CLAUDE.md and docs/PROJECT_GUIDE.md and explain the project to me in plain English."*
7. Don't start a task or merge anything until Mike assigns your first issue (end of Phase 0). Then pick it from the project board and say: *"Start work on issue #<n>."*
8. To review a teammate's work, say: *"What can I review?"*

## Documents

- [Project guide](docs/PROJECT_GUIDE.md) — start here
- [Product spec](docs/PRODUCT_SPEC.md) — what we build and how it's judged
- [Architecture](docs/ARCHITECTURE.md) — modules, contracts, API, providers, edge cases
- [Team process](docs/TEAM_PROCESS.md) — branches, PRs, reviews, QA bot, secrets, CI
- [Decisions](docs/DECISIONS.md) — what's decided and what's still open
- [Lanes and tasks](docs/plan/LANES.md) — who does what, with a ready-to-paste prompt for every task

## For the instructor

Only course-provided endpoints and public Wikipedia/Wikidata APIs are used, so no extra API keys are needed. To run (Windows or Mac, no Docker): install Node 26 and uv; copy `.env.example` to `.env` and fill in the course endpoints (`node scripts/check-env.mjs` confirms); `npm run setup`; `npm run ingest` (builds the knowledge base, once); `npm start`; open http://localhost:8000. Five showcase battles load automatically. A full first-time guide is in `docs/user-guide.md`. With `PROVIDER_MODE=mock` the app runs without any endpoints.

## Stack

Python 3.12 · FastAPI · Pydantic v2 · SQLite + sqlite-vec · React + Vite + TypeScript · Phaser 3 · course-provided GenAI endpoints.
