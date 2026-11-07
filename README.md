# Battle Royale: The Science-Backed Fight Simulator

**Corny voice, serious brain.** Name two combatants in plain language — *"100 duck-sized horses vs 1 horse-sized duck"* — and the app researches each one from vetted sources into a cited stat sheet, a simulation written in code decides the outcome, and the result plays as a cheesy late-night sports broadcast with an announcer, a soundtrack, and a crude animated battle. Every stat links to its source; gaps are labeled as estimates. No language model sets a number.

MBAX 6418 AI Business Solutions — final project. Team: Mike (PM), Adam, Gunnar, Felipe, Dillon.

> **Status: Phase 0 (setup).** The app code doesn't exist yet. This repo holds the plan, the rules, and the prompts that build it with Claude Code.

## Start here

| You are | Do this |
|---|---|
| **Mike** | Read [docs/plan/00-KICKOFF.md](docs/plan/00-KICKOFF.md) and paste its prompt into Claude Code |
| **A teammate** | Follow the quick start below, then your lane file in [docs/plan/](docs/plan/LANES.md) |
| **Anyone** | [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md) explains everything in order |

## Teammate quick start

1. GitHub account with two-factor authentication on. Send Mike your username and OS. Accept the repo invite.
2. Install Git, GitHub CLI (`gh auth login`), Claude Code (`claude`), Node 24, and uv.
3. `git clone https://github.com/mlip3191/battleRoyale.git` then `cd battleRoyale`
4. `git config core.hooksPath .githooks` — switches on the guard that blocks keys and `.env` files from being committed.
5. Copy `.env.example` to `.env`; fill it with values Mike shares through the password manager.
6. Run `claude` in the folder and say: *"Read CLAUDE.md and docs/PROJECT_GUIDE.md and explain the project to me in plain English."*
7. Pick your Wave 1 issue from the project board and say: *"Start work on issue #<n>."*
8. To review a teammate's work, say: *"What can I review?"*

## Documents

- [Project guide](docs/PROJECT_GUIDE.md) — start here
- [Product spec](docs/PRODUCT_SPEC.md) — what we build and how it's judged
- [Architecture](docs/ARCHITECTURE.md) — modules, contracts, API, providers, edge cases
- [Team process](docs/TEAM_PROCESS.md) — branches, PRs, reviews, QA bot, secrets, CI
- [Decisions](docs/DECISIONS.md) — what's decided and what's still open
- [Lanes and tasks](docs/plan/LANES.md) — who does what, with a ready-to-paste prompt for every task

## Stack

Python 3.12 · FastAPI · Pydantic v2 · SQLite + sqlite-vec · React + Vite + TypeScript · Phaser 3 · Docker Compose · course-provided GenAI endpoints.
