# Battle Royale: The Science-Backed Fight Simulator

**Corny voice, serious brain.** Name two combatants in plain language — *"100 duck-sized horses vs 1 horse-sized duck"* — and the app researches each one from vetted sources into a cited stat sheet, a simulation written in code decides the outcome, and the result plays as a cheesy late-night sports broadcast with an announcer, a soundtrack, and a crude animated battle. Every stat links to its source; gaps are labeled as estimates. No language model sets a number.

MBAX 6418 AI Business Solutions — final project, **Group A**: Mike Lippert (PM), Adam Fondale, Gunnar O'Connor, Felipe Cervino, Dillon Smart.

> **Status:** feature freeze Nov 22, 2026 · code complete Nov 25, 2026 (to be tagged `v1.0` then). Every task and bug is an issue on the [project board](https://github.com/users/mlip3191/projects/2).

## Start here

| You are | Do this |
|---|---|
| **The instructor** | Follow [For the instructor](#for-the-instructor) below |
| **A teammate** | Follow the quick start below, then your lane file in [docs/plan/](docs/plan/LANES.md) |
| **Anyone** | [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md) explains everything in order |
| **Trying the app for the first time** | Follow the [user guide](docs/user-guide.md): install, run, and play a fight, with screenshots |

## Teammate quick start

1. Install Git, GitHub CLI (`gh auth login`), Claude Code (`claude`), Node 26, and uv. Your GitHub account needs two-factor authentication on, and collaborator access from Mike to push branches.
2. `git clone https://github.com/mlip3191/battleRoyale.git` then `cd battleRoyale`
3. `npm run setup` — installs everything from the lockfiles and switches on the guard that blocks keys and `.env` files from being committed.
4. Optional: to use the course endpoints, run `npm run env:setup` in **your own terminal** (Terminal, PowerShell, or VS Code → Terminal → New Terminal). It asks for the course host and API key from the course endpoint list (the key is hidden as you type or paste), writes `.env`, and checks it. Check again anytime with `npm run env:check` — it never shows your values. In Claude Code, `/setup-env` walks you through it. Never paste the key into a chat, issue, or PR. Without a `.env`, the app runs in mock mode (sample data, no endpoints), which is also what the tests and CI use.
5. `npm start`, then open http://localhost:8000. For hot reload while you work, `npm run dev` and open http://localhost:5173.
6. Run `claude` in the folder and say: *"Read CLAUDE.md and docs/PROJECT_GUIDE.md and explain the project to me in plain English."*
7. Work only on an issue assigned to you. Pick it from the project board and say: *"Start work on issue #<n>."*
8. To review a teammate's work, say: *"What can I review?"*

## Documents

- [Project guide](docs/PROJECT_GUIDE.md) — start here
- [User guide](docs/user-guide.md) — run and use the app, for a first-time user
- [Product spec](docs/PRODUCT_SPEC.md) — what we build and how it's judged
- [Architecture](docs/ARCHITECTURE.md) — modules, contracts, API, providers, edge cases
- [Team process](docs/TEAM_PROCESS.md) — branches, PRs, reviews, QA bot, secrets, CI
- [Filing issues](docs/issues.md) — how to use /new-issue, labels, and the board
- [Decisions](docs/DECISIONS.md) — what's decided and what's still open
- [Lanes and tasks](docs/plan/LANES.md) — who does what, with a ready-to-paste prompt for every task
- [INIT.md](INIT.md) — history: the Phase 0 setup Claude Code ran to create the project

## For the instructor

The app runs on Windows or Mac, with no Docker. It uses only the course-provided endpoints and the public Wikipedia and Wikidata APIs, so no extra API keys are needed.

1. Install Node 26 and uv ([how](docs/user-guide.md#step-1-install-node-26-uv-and-git)). Git is needed only if you clone the repo instead of using the ZIP.
2. Unzip the repo and open a terminal in the unzipped folder: the one with `package.json` in it (a GitHub ZIP unzips to `battleRoyale-main`).
3. Run `npm run setup`. It installs everything the app needs from the lockfiles, in a minute or two.
4. **No course key? Skip this step.** With no `.env` file the app runs in mock mode: the stats, pictures and commentary are samples, but the simulation is real. To use the course endpoints, run `npm run env:setup` and enter the course host and API key (or copy `.env.example` to `.env` and fill it in by hand). `npm run env:check` confirms either way, without showing any values.
5. Run `npm start`. Wait for the line "Uvicorn running on http://127.0.0.1:8000", then open http://localhost:8000. Leave the terminal open; Ctrl+C stops the app. If port 8000 is busy, run `npm start -- --port 8001` and open http://localhost:8001 (the "Battle Royale is starting" line still says 8000).
6. Optional: `npm run check` runs every lint, every test and the build (about 3 minutes).

Showcase battles load automatically when the app starts (any that are missing are added; your own battles are never replaced). In live mode, the prebuilt knowledge base (`data/prebuilt-kb/`, D-66) also loads the first time, so `npm run ingest` is only needed to refresh the articles, or if the app says your embedding model differs from the one that built it. A full first-time guide, with screenshots, is in [docs/user-guide.md](docs/user-guide.md).

Some warnings during setup and start are normal and can be ignored: npm's "looking for funding" and "vulnerabilities" notes, an `fsevents` note on a Mac, and Vite's "Some chunks are larger than 500 kB".

On Windows, if PowerShell says "running scripts is disabled on this system", type `npm.cmd` instead of `npm` (for example `npm.cmd start`).

If `npm run setup` stops on Windows with "failed to hardlink file" (os error 396), run it again with copying turned on: `$env:UV_LINK_MODE="copy"; npm run setup` in PowerShell (or `set "UV_LINK_MODE=copy" && npm run setup` in Command Prompt).

## Stack

Python 3.12 · FastAPI · Pydantic v2 · SQLite + sqlite-vec · React + Vite + TypeScript · Phaser 3 · course-provided GenAI endpoints.
