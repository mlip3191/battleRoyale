# Decisions Log

Every decision that shapes the build, with its status. **Open** items need Mike's answer. **Decided** items stand unless changed by a PR. When a decision changes, edit its row and add the date — don't delete history.

## Team

| Name | GitHub | OS | Lane |
|---|---|---|---|
| Mike Lippert (PM) | `mlip3191` | Windows + Mac | 1 — Foundation & platform |
| Adam Fondale | `afondale` | Windows | 2 — Intake, safety & orchestration |
| Gunnar O'Connor | `gunnaroc` | Windows | 3 — Research & knowledge base |
| Felipe Cervino | `felcervino` | Windows | 4 — Simulation & analytics |
| Dillon Smart | `dilloncsmart` | Windows | 5 — Front end & battle stage |

**Group A** · MBAX 6418 AI Business Solutions · Instructor: David Dobolyi (david.dobolyi@colorado.edu — must be added as a collaborator because the repo is private).

## Open — need an answer

| ID | Question | Why it matters | Recommendation | Blocks |
|---|---|---|---|---|
| D-16 | **Where does the demo run?** Endpoints are public URLs, so any machine with internet works. | The showcase battles and `npm start` must work on that machine. | Mike's laptop, plus the recorded backup | G08, demo |

## Decided

| ID | Decision | Date |
|---|---|---|
| D-01 | **Private repo + GitHub Pro** (Pro confirmed active 2026-11-08). M01 checks `plan.name` and makes the repo private (on a private personal repo only collaborators can fork; the "Allow forking" setting exists only for organizations). Teammates and the instructor (david.dobolyi@colorado.edu, required by the overview for private repos) are invited early, in M02. GitHub secret scanning/push protection aren't available for private personal repos, so the gitleaks Secret scan + local hook are our secret checks. | 2026-11-08 |
| D-02 | **Claude Code builds the app; Hermes Agent is used once:** task G06 is built with Hermes Agent (port 9000), Mike pairing, with screenshots for the Build Stack slide. | 2026-11-07 |
| D-03 | **Course endpoints:** public URLs; Mike and every teammate have the hosts, ports, and keys. Everyone fills their own `.env` from `.env.example` and checks it with `node scripts/check-env.mjs` (never shows values). Per-service keys are supported (`<SERVICE>_API_KEY` overrides `COURSE_API_KEY`). The repo never contains hosts or keys. | 2026-11-08 |
| D-04 | **QA bot is advisory** and uses Mike's Claude subscription token (`claude setup-token` → repo secret `CLAUDE_CODE_OAUTH_TOKEN`). It comments and records a verdict but never blocks a merge and is not a required check. It runs on PR open/reopen/ready and on the `re-review` label; skips drafts, forks, and Dependabot. Switch to a spend-capped API key if Mike's plan limits get tight. | 2026-11-08 |
| D-05 | **Due Wednesday, November 25, 2026.** Day-by-day schedule in `docs/plan/DELIVERABLES.md`; cut order in `docs/plan/LANES.md`. Assumed: presentation and Canvas submission are both that day. | 2026-11-08 |
| D-06 | **Team roster:** Group A, five members including Dillon (confirmed). | 2026-11-08 |
| D-07 | **Allowed fighters:** animals (living and extinct) and generic historical human archetypes. **Blocked:** named real people, minors, groups of people, sexual content, copyrighted fictional characters. Mythical creatures are a stretch goal and always all-estimate. | 2026-11-07 |
| D-08 | **GitHub handles and OS** as in the team table. Everyone but Mike is Windows-only, and Mike runs Phase 0 on his Mac. **Mike is the Mac tester:** any PR touching setup scripts, hooks, the start command, or file paths gets a Mac check from him; CI also runs macOS on every merge to main and nightly. gitleaks is optional (`brew install gitleaks` / `winget install gitleaks`); without it the hook's built-in checker runs. | 2026-11-08 |
| D-09 | **Announcer voice, first iteration: a stock TTS voice, gruff, deep, and hard-hitting.** A07 auditions the endpoint's stock voices with the same test line and picks the deepest, gruffest one; it lowers pitch/slows rate if the endpoint allows. The writing stays corny; the delivery is a gravel-voiced fight announcer. Voice cloning is a later polish item and needs written consent. | 2026-11-08 |
| D-10 | **"Expert answers" for the benchmark** = obvious-by-biology cases + documented expert views with citations + rough fair-fight ranges (G07). Pass rules written before the first run. | 2026-11-07 |
| D-11 | **Styling:** plain CSS modules with CSS variables; no CSS framework. | 2026-11-07 |
| D-12 | **Versions:** Python 3.12, Node 24 LTS, uv for Python packages, npm for JS. Lockfiles committed. | 2026-11-07 |
| D-13 | **MVP is exactly two sides** (each side can have many fighters). | 2026-11-07 |
| D-14 | **The number rule:** models copy numbers only with a verified quote; estimates come from code. | 2026-11-07 |
| D-15 | **Mock-first providers;** CI always runs in mock mode. | 2026-11-07 |
| D-17 | **Monorepo** (`backend/`, `frontend/`) with root npm scripts as the cross-platform task runner. | 2026-11-07 |
| D-18 | **No license file** while the repo is private. | 2026-11-07 |
| D-19 | **No user accounts; battles stored locally** in SQLite; no personal data collected. | 2026-11-07 |
| D-20 | **Data sources approved by Mike:** the recommended datasets below; details and licenses go in `docs/research.md` (G01). | 2026-11-08 |
| D-21 | **No team channel and no password manager.** All coordination happens on GitHub: request reviewers on the PR (GitHub notifies them), @mention people in issues and PR comments, and use one pinned "Team board" issue for announcements and weekly check-ins. Everyone already has the `.env` values. | 2026-11-08 |
| D-22 | **Five lanes,** 13–14 points each, owners as in `docs/plan/LANES.md`; final deliverables split one-per-person in `docs/plan/DELIVERABLES.md`. | 2026-11-08 |
| D-23 | **PR review flow:** the review-prs skill drafts; nothing posts until the reviewer says send; approval is a separate, second confirmation. The QA bot never approves. | 2026-11-07 |
| D-26 | **Merge rules kept light for speed:** 1 approval; required checks = CI (backend + frontend on ubuntu + windows), Secret scan, Critical files approval. Off: dismiss stale approvals, approval of the most recent push, branches up to date, conversation resolution. macOS CI runs on merges to main and nightly instead of every PR, to stay within the 3,000 Actions minutes of GitHub Pro. Norm: re-request review if you push meaningful changes after an approval. | 2026-11-08 |
| D-25 | **No Docker.** The app runs with `npm start`: the backend serves the built front end and the API together at http://localhost:8000, so the instructor needs only Node 24 and uv. | 2026-11-08 |
| D-24 | **Showcase battles ship with the repo** (`data/showcase/`, small, committed) so the instructor's clone shows the five demo battles even before he fills `.env`. | 2026-11-08 |

## Recommended datasets (D-20)

The proposal promised Wikipedia, Wikidata, and Hugging Face datasets. Recommended set, in priority order:

| # | Dataset | Where | What we use it for | License | Notes |
|---|---|---|---|---|---|
| 1 | **Wikipedia Structured Contents** (`wikimedia/structured-wikipedia`) | Hugging Face | Main RAG text: article abstracts, sections, and **parsed infoboxes**, each linked to its Wikidata ID | CC BY-SA 4.0 / GFDL | Official Wikimedia dataset. Don't download it all: stream it and keep only seed-fighter articles (filter by Wikidata QID). |
| 2 | **FineWiki** (`HuggingFaceFW/finewiki`) | Hugging Face | Backup text source with infobox JSON and `wikidata_id` per article, built from recent Wikimedia dumps | CC BY-SA (Wikipedia) | Use if #1 lacks an article or is stale. |
| 3 | **Wikidata** (live API, no key) | wikidata.org | High-confidence numbers with property IDs and references (mass, length, speed when present); "is this a real human?" check | CC0 | Not a Hugging Face dataset; already in the plan (G02, A04). |
| 4 | **PanTHERIA** (mammal traits) | Ecological Archives / figshare (mirror to a team HF dataset if we want it "on HF") | Adult body mass, head-body length, limb length, group size for ~5,400 mammals | CC0 | Peer-reviewed, citable; ideal for `mass_kg` and `size_m`. |
| 5 | **AnimalTraits** (body mass, metabolic rate, brain size) | Scientific Data 2022 (download linked from the paper) | Body mass for ~2,000 terrestrial species incl. arthropods, reptiles, birds | CC BY 4.0 | Covers insects/spiders that PanTHERIA doesn't. Metabolic rate can inform `endurance_s`. |
| 6 | **TreeOfLife taxonomy metadata** (`imageomics/TreeOfLife-10M`, `metadata/` only) | Hugging Face | Common name → scientific name → class/order, for normalizing fighter names and setting `category` | CC0 | Optional; download only the taxonomy CSV, not the images. |

**Avoid (confirmed by Mike, 2026-11-08):** Kaggle-style "animal facts" tables and Hugging Face uploads whose cards say values were generated with AI or have no sources — for example `pcwoods/2026-animaldescription-text-dataset`, whose card says generative AI was used to identify the animal facts. They would break the "every number is traceable" promise. Speed, bite force, and armor rarely appear in trait databases; those come from Wikipedia text through the verified-quote extractor, or from code estimates.
