# Final Deliverables — Group A

From the **MBAX 6418 Final Project Overview**. Everything is submitted on Canvas. **Due Wednesday, November 25, 2026** (DECISIONS D-05).

| Date | What |
|---|---|
| Sat Nov 14 | MS-1 walking skeleton; first scope check against the cut order in LANES.md |
| Tue Nov 17 | MS-2 real brain; second scope check; deck owners start their slides |
| Fri Nov 20 | MS-3 the show; **feature freeze** at end of day (only bug fixes after this) |
| Sat Nov 21 | Bug bash (everyone, 90 minutes); fixes through Nov 22 |
| Sun Nov 22 | MS-4 demo-ready (showcase battles saved); slide deck draft + first timed rehearsal |
| Mon Nov 23 | Second rehearsal (or record the MP4 if presenting online); backup demo video recorded |
| Tue Nov 24 | Buffer; README and user guide final; repo export tested from a fresh unzip |
| **Wed Nov 25** | Presentation (live 10–12 min + 3 min Q&A, or recorded MP4) |
| **Wed Nov 25** | Canvas submission: deck, repo link, repo export, peer evaluations (submit the morning of, not at midnight) |

## What the instructor requires, and how we meet it

| Requirement (overview) | How we meet it | Owner |
|---|---|---|
| Repo starts from scratch, step-by-step buildout | First commit is the plan; every change is an issue → PR → squash merge, so history shows the build step by step | everyone |
| Private repo → add the instructor as collaborator | M02 invites david.dobolyi@colorado.edu (Settings → Collaborators → Add people → email); confirm he accepted before Nov 25 | Mike |
| README describes the project from the proposal, kept up to date | README updated at each milestone (MS-1…MS-4); final pass before submission | Mike |
| Documentation for a naïve user | `docs/user-guide.md`: what the app does, how to run it, how to read results | Dillon |
| Runnable code the instructor can test easily | `npm run setup` then `npm start` (one process, http://localhost:8000, no Docker); mock mode runs with no endpoints; showcase battles committed in `data/showcase/` (D-24); `node scripts/check-env.mjs` tells him what to fill in | Mike + Gunnar (G08) |
| API keys only if we use non-course APIs | We use only course endpoints + public Wikipedia/Wikidata (no key) → **no extra keys**; say so in the README | Mike |
| Repo export (ZIP) | `git archive --format=zip -o battleRoyale.zip main` (excludes ignored files) — confirm size and that it runs from a fresh unzip | Mike |
| Peer evaluation | Each person submits their own on Canvas | everyone |

## Slide deck — one owner per section (balanced)

Title slide: **Battle Royale: The Science-Backed Fight Simulator** · Group A · Mike Lippert, Adam Fondale, Gunnar O'Connor, Felipe Cervino, Dillon Smart · date.

| Section (required by the overview) | Content | Owner | Built from |
|---|---|---|---|
| Deck design + title slide | Broadcast-style template matching the app; title slide | **Dillon** | app theme (D02) |
| Project framing | Finalized proposal: the situation, the product, "corny voice, serious brain" | **Adam** | PRODUCT_SPEC §1–2 |
| App demonstration | Live demo plan (2 showcase battles + 1 audience pick), screenshots, backup video | **Felipe** | showcase battles, benchmark results |
| Build stack | AI coding tools + models: Claude Code (model per the PR records), Hermes Agent with its model (G06), the advisory QA bot on GitHub | **Mike** | PR template "Built with" field |
| App software / API / model stack | FastAPI, React, Phaser, SQLite + sqlite-vec; each course endpoint with its model name and what it does | **Mike** | ARCHITECTURE §2, §7, `docs/providers.md` |
| Sources | Wikipedia Structured Contents, Wikidata, PanTHERIA, AnimalTraits; licenses; no apps or screenshots used as a base | **Gunnar** | DECISIONS D-20, `docs/research.md` |
| Build process + bug testing | How it grew (milestones), what changed vs the proposal, how we tested (CI on Linux/Windows per PR + macOS on merges, advisory QA bot, benchmark, bug bash), top bugs fixed | **Adam** | closed issues labeled `type: bug`, `docs/benchmark-results.md` |
| Contributions | CRediT-style table (below) | **Dillon** | lanes + git history |
| Lessons learned + limitations | What worked (contracts, mocks, review skill), what we'd change, limits (estimates, two sides only), future work | **Gunnar** | retro notes |

Presentation: everyone speaks for about 2 minutes on their own section(s). Two full rehearsals with a timer (target 11 minutes).

## Contributions (CRediT draft — update at the end)

| Role (CRediT) | Mike | Adam | Gunnar | Felipe | Dillon |
|---|---|---|---|---|---|
| Conceptualization | lead | support | support | support | support |
| Software | foundation, contracts, providers | intake, safety, pipeline, announcer | research, RAG, stat sheets | simulation engine, analytics | front end, animation, images |
| Data curation | | | lead (seed sheets, benchmark set) | support | |
| Validation | QA bot, CI | safety test set | traceability | benchmark runner | UI tests |
| Project administration | lead | | | | |
| Visualization | | | | | lead |
| Writing — original draft | process docs | framing, build process | sources, lessons | demo | user guide, deck design |
| Writing — review & editing | all | all | all | all | all |

## Bug bash (Wave 4)

90 minutes, everyone, each on their own Windows machine (Mike also on Mac):
1. Pull latest main, `npm run setup`, `npm run dev`.
2. Each person tries 15 matchups from a shared list: 5 normal, 5 edge cases from ARCHITECTURE §14, 5 creative.
3. File every problem with `/new-issue` as a bug (steps, expected, actual, screenshot).
4. Mike triages the same day; fixes go through normal PRs.
The closed bug issues become the "Build process + bug testing" slide.

## Record-keeping that feeds the deck (start now)

- **PR template "Built with" field:** every PR states the AI tool and model used (M07 adds it).
- **Milestone notes:** at each MS-1…MS-4, Mike adds 3 lines to `docs/build-log.md`: what works, what changed from the plan, screenshots.
- **Screenshots/GIFs:** save to `docs/media/` (small files only) whenever something visible lands.
