# Repository Deliverables — Group A

The **code is complete on Wednesday, November 25, 2026** (DECISIONS D-05). The slide deck and presentation are prepared **outside this repo**, starting Nov 25; this file covers only what the repository itself must deliver, plus the notes that will feed the deck.

## What the Final Project Overview requires of the repo

| Requirement (overview) | How we meet it | Owner | Done by |
|---|---|---|---|
| Repo starts from scratch, step-by-step buildout | First commit is the plan; every change is an issue → PR → squash merge, so history shows the build step by step | everyone | ongoing |
| README describes the project from the proposal, kept up to date | README updated at each milestone; final pass on Nov 24 | Mike | Nov 24 |
| Documentation for a naïve user | `docs/user-guide.md` (task D09), with screenshots, linked from README | Dillon | Nov 23 |
| Runnable code the instructor can test easily | `npm run setup` then `npm start` (one process, http://localhost:8000, no Docker); mock mode runs with no endpoints; five showcase battles committed in `data/showcase/` (D-24); `npm run ingest` builds the knowledge base for live mode; `node scripts/check-env.mjs` tells him what to fill in | Gunnar (G08) + Mike | Nov 22 |
| Fresh-clone check | Someone clones into an empty folder and follows README "For the instructor" exactly — Windows (Gunnar, G08) and Mac (Mike) | Gunnar, Mike | Nov 22, re-run Nov 24 |
| API keys only if we use non-course APIs | Only course endpoints + public Wikipedia/Wikidata/Hugging Face (no keys) → no extra keys; README says so | Mike | done |
| Private repo → instructor added as collaborator | Mike's call, done by hand when he chooses (invitations expire after 7 days). Claude doesn't send it. | Mike | before submission |
| Repo export | **Zip a fresh clone including `.git`** so the step-by-step history travels with the code (`git archive` drops history). Steps on Nov 25: `git tag v1.0 && git push --tags`; `git clone https://github.com/mlip3191/battleRoyale.git battleRoyale-v1.0`; zip that folder; unzip it somewhere new and run `npm run setup` + `npm start` once to prove it works. | Mike | Nov 25 |
| Thorough bug testing / UI-UX | Internal bug bash (Nov 21) + 3–5 outside usability sessions (D10, Nov 21–22); every finding filed as an issue (`type: bug` or `usability`) | everyone, Dillon leads D10 | Nov 22 |
| Evidence the AI works | `docs/evaluation.md` (M09) + `docs/benchmark-results.md` (F07) | Mike, Felipe | Nov 21 |

## Schedule to code complete

| Date | What |
|---|---|
| Sat Nov 14 | MS-1 walking skeleton; first scope check against the cut order in LANES.md |
| Tue Nov 17 | MS-2 real brain; second scope check |
| Fri Nov 20 | MS-3 the show works |
| Sat Nov 21 | Bug bash (everyone, 90 minutes); usability sessions start; M09 evaluation written |
| Sun Nov 22 | Usability sessions done; MS-4 demo-ready; **feature freeze at end of day** |
| Mon Nov 23 – Tue Nov 24 | Fixes only; user guide and README final; fresh-clone check re-run |
| **Wed Nov 25** | **Code complete:** tag `v1.0`, export ZIP with history, hand off to deck work |

## Bug bash (Sat Nov 21)

90 minutes, everyone, each on their own Windows machine (Mike also on Mac):
1. Pull latest `main`, `npm run setup`, `npm start`.
2. Each person tries 15 matchups from a shared list: 5 normal, 5 edge cases from ARCHITECTURE §14, 5 creative.
3. File every problem with `/new-issue` as a bug (steps, expected, actual, screenshot).
4. Mike triages the same day; fixes go through normal PRs.

## Notes that will feed the deck (start now, keep in the repo)

These cost minutes now and save hours on Nov 25:
- **Build stack:** every PR's "Built with" field (AI tool + model). Mike also records the Hermes Agent comparison from G06 in `docs/build-log.md`.
- **Build process:** `docs/build-log.md` — three lines at each milestone (what works, what changed from the plan, a screenshot link).
- **Bug testing:** closed issues labeled `type: bug` and `usability`; `docs/usability/findings.md`.
- **Evaluation and limitations:** `docs/evaluation.md`, `docs/benchmark-results.md`, `docs/simulation-model.md` (where every constant comes from).
- **Changes vs. the proposal:** the "Changes from the proposal" list in DECISIONS.md.
- **Business case:** PRODUCT_SPEC §2a.
- **Contributions:** lane ownership (LANES.md) plus the git history; a CRediT-style draft follows.
- **Screenshots/GIFs:** small files in `docs/media/` whenever something visible lands.

### Contributions draft (CRediT-style; update at the end)

| Role | Mike | Adam | Gunnar | Felipe | Dillon |
|---|---|---|---|---|---|
| Conceptualization | lead | support | support | support | support |
| Software | foundation, contracts, providers | intake, safety, pipeline, media | research, RAG, stat sheets | simulation engine, analytics | front end, animation, intake API |
| Data curation | | | lead (seed sheets, benchmark set) | support | |
| Validation / formal analysis | AI evaluation (M09), CI | safety test set | traceability | benchmark runner | usability sessions, UI tests |
| Project administration | lead | | | | |
| Visualization | | | | | lead |
| Writing | process docs | | research docs | simulation-model doc | user guide |
