# Project Guide — start here

**Battle Royale: The Science-Backed Fight Simulator** · MBAX 6418 AI Business Solutions final project
**Group A:** Mike Lippert (PM, `mlip3191`), Adam Fondale (`afondale`), Gunnar O'Connor (`gunnaroc`), Felipe Cervino (`felcervino`), Dillon Smart (`dilloncsmart`) · Repo: https://github.com/mlip3191/battleRoyale

This guide consolidates the project proposal and the team's setup standard into one plan. It tells you what we're building, how the documents fit together, and exactly what to do, step by step, from an empty repo to a finished demo.

## 1. The documents

| Document | Read it when | Owner |
|---|---|---|
| [PRODUCT_SPEC.md](PRODUCT_SPEC.md) | You want to know **what** the app does and how it's judged | Mike |
| [ARCHITECTURE.md](ARCHITECTURE.md) | You need the **structure**: modules, contracts, API, providers, edge cases | Mike |
| [TEAM_PROCESS.md](TEAM_PROCESS.md) | You need the **rules**: branches, PRs, reviews, QA bot, secrets, CI | Mike |
| [DECISIONS.md](DECISIONS.md) | Something is unclear or undecided | Mike |
| [plan/LANES.md](plan/LANES.md) | You want the big picture of who does what, when | everyone |
| `plan/lane-<n>-<name>.md` | You're starting a task: **every task has a ready-to-paste prompt** | each owner |
| [../INIT.md](../INIT.md) | Mike, once: the single document Claude Code follows to initialize the project | Mike |
| [plan/DELIVERABLES.md](plan/DELIVERABLES.md) | Planning the deck, presentation, and Canvas submission | everyone |
| [../CLAUDE.md](../CLAUDE.md) | Claude reads it automatically every session | Mike |

## 2. The product in one minute

Users type a matchup ("100 duck-sized horses vs 1 horse-sized duck"). The app:

1. **Intake** — understands the request, asks one clarifying question if needed, blocks unsafe requests.
2. **Research** — builds a stat sheet per fighter from Wikipedia, Wikidata, and datasets; every number has a source or is labeled an estimate.
3. **Simulate** — runs ~1,000 seeded fights in code (Lanchester laws, square-cube scaling, terrain, retreat).
4. **Background** — the announcer's corny intro.
5. **Narration + soundtrack** — play-by-play captions and voice; a short music track.
6. **Battlefield** — crude sprites and a Phaser animation that replays the simulation exactly.
7. **Summary + fair fight** — win %, survivors, deciding factor, and "a fair fight needs 37 house cats."
8. **Next challenger** — the closest-odds opponent for the winner.

## 3. The plan at a glance

| Phase | Who | What | Done when |
|---|---|---|---|
| **0 Foundation** (days 1–3) | Mike alone | Repo settings, guardrails, skeleton, contracts, providers, review tooling, protection, issues, invites (M01–M08) | Dry-run PR passes all checks; teammates invited |
| **1 Onboard + setup** (days 4–5) | Everyone | Each teammate's setup task: A01, G01, F01, D01 | Everyone has merged one PR and reviewed one |
| **2 Skeleton** (week 2) | Lanes in parallel | Parsing, ingestion, engine core, app shell | **MS-1:** matchup → verdict on mocks in the UI |
| **3 Core** (week 3) | Lanes | Clarify, orchestrator, retrieval, stat sheets, terrain, results UI, animation | **MS-2:** real stat sheets + real simulation |
| **4 Complete** (week 4) | Lanes | Scripts, audio, images, fair fight, benchmark, broadcast page, Docker | **MS-3:** the full show; **MS-4:** demo-ready |

Wave dates follow the course calendar (DECISIONS D-05).

## 4. Step by step — Mike (Phase 0)

1. **Install and log in:** Git, GitHub CLI (`gh auth login`), Claude Code (`claude`), Node 24, uv.
2. **Clone:** `git clone https://github.com/mlip3191/battleRoyale.git`, `cd battleRoyale`.
3. **Fill `.env`:** copy `.env.example` to `.env`; add the course endpoint URLs (D-03). Never paste them anywhere else — they're public URLs, so anyone holding them could use the course's quota.
4. **Turn on GitHub Pro** through the GitHub Student Developer Pack (D-01), and collect the remaining open items in [DECISIONS.md](DECISIONS.md): D-03 (missing ports), D-05 (deadlines), D-06 (roster), D-08 (usernames).
5. **Open Claude Code in the repo and say: "Read INIT.md and follow it."** ([INIT.md](../INIT.md)) It runs M01–M08 one at a time, stops for your confirmation, and tells you when to click something in GitHub. In order:
   - **M01** GitHub settings: squash-only merges, Dependabot, secret scanning + push protection, read-only Actions token, allowed-actions list.
   - **M02** Switch on and test the secret-blocking git hook; finalize CLAUDE.md.
   - **M03** Claude Code permissions and hooks (`.claude/settings.json`).
   - **M04** Backend + front-end skeleton, cross-platform files, CI on Windows/Mac/Linux.
   - **M05** Shared contracts — the shapes all lanes build against.
   - **M06** Provider layer with mocks; smoke-test the course endpoints; `docs/providers.md`.
   - **M07** QA bot, Secret scan, critical-files check, CODEOWNERS, PR template.
   - **M08** Labels, one issue per task, project board, branch protection, dry run, invites.
6. **Kickoff call:** walk the team through the board, their lane file, and the dry-run PR.

## 5. Step by step — every teammate (Adam, Gunnar, Felipe, Dillon)

**Day 1 — get set up (about an hour)**

1. **GitHub account** with two-factor authentication turned on (Settings → Password and authentication). Send Mike your username and whether you use Windows, Mac, or both.
2. **Accept the invite** from the email or https://github.com/mlip3191/battleRoyale/invitations.
3. **Install** (detailed links in `docs/onboarding.md` once D01 lands):
   - Git (Windows: Git for Windows, which includes Git Bash; Mac: `xcode-select --install`)
   - GitHub CLI, then run `gh auth login` and pick GitHub.com → HTTPS → log in with a browser
   - Claude Code (needs a Claude plan that includes it), then run `claude` once to log in
   - Node 24 (Windows: nvm-windows or fnm; Mac: fnm or nvm) and uv
   - VS Code (optional but helpful)
4. **Tell git who you are** (same email as GitHub):
   `git config --global user.name "Your Name"` and `git config --global user.email "you@example.com"`
   Windows only: `git config --global core.longpaths true`
5. **Clone and enter the project:** `git clone https://github.com/mlip3191/battleRoyale.git` then `cd battleRoyale`.
6. **Switch on the secret guard:** `git config core.hooksPath .githooks` (the setup check does this for you after D01).
7. **Create your `.env`:** copy `.env.example` to `.env` (Mac: `cp .env.example .env`, Windows: `copy .env.example .env`) and fill in every `[required]` line with the course endpoint URLs, ports, and keys you already have; then run `node scripts/check-env.mjs` (it never shows values). Values everyone already has.
8. **Start Claude Code** in the folder (`claude`) and say: *"Read CLAUDE.md and docs/PROJECT_GUIDE.md and explain the project to me in plain English. Then run npm run setup and npm run dev and tell me if it works."*

**Day 2 — your first task**

9. Open the project board → **Ready** → your Wave 1 issue (A01, G01, F01, or D01). Assign yourself; move it to **In progress**.
10. In Claude Code: *"Start work on issue #<n>. Read the task in docs/plan/<your lane file> under its ID, follow its prompt, and check off its acceptance criteria before opening the PR."*
11. Claude explains its plan → you say yes → it builds, runs tests, commits, pushes, and opens the PR.
12. Request a reviewer on the PR (GitHub notifies them). Wait for the QA bot and a teammate's review. Fix anything requested on the same branch.
13. When it's approved and all checks are green, click **Squash and merge**.

**Every day after**

14. **Review someone's PR:** ask Claude *"What can I review?"* Pick one; the agent drafts comments and fixes; you read them, say **send**, and approve only if it's ready (Claude asks separately).
15. **Need new work tracked?** Type `/new-issue` (after A01).
16. **Stuck more than 30 minutes?** Comment on your issue and @mention Mike (`@mlip3191`).

## 6. How a task flows (everyone, every time)

```
Issue (Ready) → branch issue-<n>-… → Claude plans → you approve → build + tests
→ PR (template, "Closes #n") → CI ×6 + Secret scan + QA bot + Critical files
→ teammate review (review-prs skill: draft → send → separate approve) → author merges → Done
```

## 7. Review of the proposal and setup guide: gaps filled

| # | Gap or ambiguity found | How it's resolved | Where |
|---|---|---|---|
| 1 | "No language model sets a number" conflicts with the model filling the stat schema | Precise rule: models copy numbers only with a verified quote; estimates come from code | ARCHITECTURE §5, D-14 |
| 2 | Five endpoints have no port listed (Structured Decisions, Reranking, TTS/Voice, Music, STT); endpoints are public URLs | Provider layer + smoke test discovers and documents them; mocks unblock everyone meanwhile; URLs kept in `.env` | ARCHITECTURE §7, M06, D-03 |
| 3 | Course endpoints aren't reachable from GitHub CI | Mock-first providers; CI always in mock mode | D-15 |
| 4 | Proposal names Hermes as the coding agent; team uses Claude Code | Claude Code for the build; Hermes Agent builds task G06 for the report | D-02 |
| 5 | Dillon isn't on the proposal; group letter and last names are blank | Group A, Dillon confirmed, names and handles recorded | D-06, D-08 |
| 6 | Deliverables weren't mapped to work | Final Project Overview mapped to owners, record-keeping, bug bash, and instructor access | plan/DELIVERABLES.md |
| 7 | The repo was public; going private on GitHub Free would silently drop branch protection | Private + GitHub Pro (Student Pack); gitleaks Secret scan replaces GitHub's secret scanning, which private personal repos don't get | D-01, Step 8 |
| 8 | "Expert answers" for the benchmark undefined | Three groups (obvious, documented, count) with pass rules set in advance | G07, D-10 |
| 9 | Stat schema undefined | Ten fixed stats + habitat + weapons | ARCHITECTURE §5 |
| 10 | Long media generation would block the verdict | Staged pipeline with progressive reveal and per-stage fallbacks | ARCHITECTURE §4 |
| 11 | No safety detail beyond "block real people" | Code rules + classifier + Wikidata human check; minors and groups of people blocked; PG tone | A04, ARCHITECTURE §11 |
| 12 | Voice cloning and music raise consent/copyright issues | Stock gruff voice first; cloning needs consent; no real artists or franchises in prompts | A07, D-09 |
| 13 | Wikipedia text license | Attribution (CC BY-SA) on the results page | D04, ARCHITECTURE §11 |
| 14 | No demo-day plan | Five cached showcase battles + backup video | PRODUCT_SPEC §9 |
| 15 | Setup guide said "PM does everything first"; lanes need balance | Each teammate's first task is a setup task; Mike's lane is Phase 0 | LANES.md |
| 16 | Setup guide's review tool posted and set status automatically | review-prs skill: draft → confirm send → separate confirm approve | Step 3, D-23 |
| 17 | Fork PRs could run code on a reviewer's machine or slip past the QA bot | Forking disabled; skill refuses to run fork code; QA bot fails (not skips) fork PRs | SKILL.md, M01 |
| 18 | QA bot cost and Actions minutes on a private repo | Bot on Mike's subscription token, skips drafts, cancels stale runs; macOS/Windows CI only on PRs | D-01, D-04 |

The full list of edge cases the app must handle is in [ARCHITECTURE §14](ARCHITECTURE.md#14-edge-cases-the-design-must-handle). Outstanding questions are the **Open** rows in [DECISIONS.md](DECISIONS.md).

## 8. Features added beyond the proposal

- Two-layer safety: code rules + LLM classifier + Wikidata "is a real human" check
- One-question clarification with automatic, visible assumptions
- Count words and swarm limits (up to 10,000 per side, aggregated swarm mode)
- Verified-quote extraction: model numbers rejected unless the quote proves them
- Hand-verified seed stat sheets for 15 fighters (25 seed fighters total)
- Win % with 95% confidence intervals
- Deterministic, cached battles (same input → same result, instantly)
- "No contest" outcome for fighters that can't reach each other
- Deciding factor by sensitivity analysis, explained by a code template
- "No fair fight within 10,000" message when odds can't balance
- Number guard on announcer scripts + template fallback script
- Progressive reveal: verdict first, media fills in; every media stage has a fallback
- Captions always on, synced to the animation; reduced-motion mode; mute
- Placeholder sprites when image generation is down; sprites cached per fighter
- Sources section with licenses on the results page
- Benchmark runner with history, plus traceability report
- Five pre-generated showcase battles and a backup video for demo day
- Mock mode for every AI service, so everything runs offline and in CI
- Provider smoke test that documents the real course endpoints
- review-prs skill: lists open PRs by what they need, agent-drafted comments with suggested fixes, confirm-before-send, separate approval
- QA bot, Secret scan, and critical-files check as required GitHub checks
- Shared git hook that blocks keys, `.env` files, and large files on every commit
- Setup-check (`npm run doctor`) for Windows and Mac
- `/new-issue` command that scopes and splits work
