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

**Group A** · MBAX 6418 AI Business Solutions · Instructor: David Dobolyi. The overview requires adding the instructor as a collaborator on a private repo; Mike does that by hand when he chooses (invitations expire after 7 days).

## Open — need an answer

| ID | Question | Why it matters | Recommendation | Blocks |
|---|---|---|---|---|
| D-16 | **Which machine shows the app in the presentation?** (The presentation itself is prepared outside the repo.) | Showcase battles and `npm start` must work there. | Mike's laptop, plus a recorded backup | demo |

## Decided

| ID | Decision | Date |
|---|---|---|
| D-01 | **Private repo + GitHub Pro** (Pro confirmed active 2026-11-08). M01 checks `plan.name` and makes the repo private (on a private personal repo only collaborators can fork; the "Allow forking" setting exists only for organizations). Teammates are invited early, in M02; the instructor is invited by Mike by hand when he chooses. GitHub secret scanning/push protection aren't available for private personal repos, so the gitleaks Secret scan + local hook are our secret checks. | 2026-11-08 |
| D-02 | **Claude Code builds the app; Hermes Agent is used once:** task G06 is built with Hermes Agent (port 9000), Mike pairing, with screenshots for the Build Stack slide. | 2026-11-07 |
| D-03 | **Course endpoints:** public URLs; Mike and every teammate have the hosts, ports, and keys. Everyone fills their own `.env` from `.env.example` and checks it with `node scripts/check-env.mjs` (never shows values). Per-service keys are supported (`<SERVICE>_API_KEY` overrides `COURSE_API_KEY`). The repo never contains hosts or keys. | 2026-11-08 |
| D-04 | **QA bot is advisory** and uses Mike's Claude subscription token (`claude setup-token` → repo secret `CLAUDE_CODE_OAUTH_TOKEN`). It comments and records a verdict but never blocks a merge and is not a required check. It runs on PR open/reopen/ready and on the `re-review` label; skips drafts, forks, and Dependabot. Switch to a spend-capped API key if Mike's plan limits get tight. | 2026-11-08 |
| D-05 | **Code complete Wednesday, November 25, 2026.** The slide deck and presentation are prepared outside this repo, starting Nov 25. Feature freeze end of Sun Nov 22; fixes Nov 23–24. Schedule in `docs/plan/DELIVERABLES.md` and `docs/plan/LANES.md`. | 2026-11-08 |
| D-06 | **Team roster:** Group A, five members including Dillon (confirmed). | 2026-11-08 |
| D-07 | **Allowed fighters:** animals (living and extinct) and generic historical human archetypes. **Blocked:** named real people, minors, groups of people, sexual content, copyrighted fictional characters. *Widened by D-38.* | 2026-11-07 |
| D-08 | **GitHub handles and OS** as in the team table. Everyone but Mike is Windows-only, and Mike runs Phase 0 on his Mac. **Mike is the Mac tester:** any PR touching setup scripts, hooks, the start command, or file paths gets a Mac check from him; CI runs macOS on demand (Mike triggers it before each milestone). gitleaks is optional (`brew install gitleaks` / `winget install gitleaks`); without it the hook's built-in checker runs. | 2026-11-08 |
| D-09 | **Announcer voice, first iteration: a stock TTS voice, gruff, deep, and hard-hitting.** A07 auditions the endpoint's stock voices with the same test line and picks the deepest, gruffest one; it lowers pitch/slows rate if the endpoint allows. The writing stays corny; the delivery is a gravel-voiced fight announcer. Voice cloning is a later polish item and needs written consent. | 2026-11-08 |
| D-10 | **"Expert answers" for the benchmark** = obvious-by-biology cases + documented expert views with citations + rough fair-fight ranges (G07). Pass rules written before the first run. | 2026-11-07 |
| D-11 | **Styling:** plain CSS modules with CSS variables; no CSS framework. | 2026-11-07 |
| D-12 | **Versions:** Python 3.12, Node 26 LTS, uv for Python packages, npm for JS. Lockfiles committed. Node changed from 24 to 26 (the current LTS) by Mike. | 2026-11-07; Node 26 2026-11-08 |
| D-13 | **MVP is exactly two sides** (each side can have many fighters). | 2026-11-07 |
| D-14 | **The number rule:** models copy numbers only with a verified quote; estimates come from code. | 2026-11-07 |
| D-15 | **Mock-first providers;** CI always runs in mock mode. | 2026-11-07 |
| D-17 | **Monorepo** (`backend/`, `frontend/`) with root npm scripts as the cross-platform task runner. | 2026-11-07 |
| D-18 | **No license file** while the repo is private. | 2026-11-07 |
| D-19 | **No user accounts; battles stored locally** in SQLite; no personal data collected. | 2026-11-07 |
| D-20 | **Data sources approved by Mike:** the recommended datasets below; details and licenses go in `docs/research.md` (G01). | 2026-11-08 |
| D-21 | **No team channel and no password manager.** All coordination happens on GitHub: request reviewers on the PR (GitHub notifies them), @mention people in issues and PR comments, and use one pinned "Team board" issue for announcements and weekly check-ins. Everyone already has the `.env` values. | 2026-11-08 |
| D-22 | **Five lanes:** Mike 16, Adam 14, Gunnar 15, Felipe 15, Dillon 14 points (Gunnar and Felipe raised from 13 by D-39) (see `docs/plan/LANES.md`). Mike's extra points are Phase 0 plus the live AI evaluation. | 2026-11-08 |
| D-23 | **PR review flow:** the review-prs skill drafts; nothing posts until the reviewer says send; approval is a separate, second confirmation. The QA bot never approves. | 2026-11-07 |
| D-26 | **Merge rules kept light for speed:** 1 approval; required checks = CI (backend + frontend on ubuntu + windows), Secret scan, Critical files approval. Off: dismiss stale approvals, approval of the most recent push, branches up to date, conversation resolution. macOS CI runs only on demand (Mike triggers it before each milestone: `gh workflow run ci.yml --ref main -f os=macos-latest`), because one macOS run bills ~80 of the 3,000 monthly Actions minutes. Norm: re-request review if you push meaningful changes after an approval. | 2026-11-08 |
| D-27 | **Early invites, light rules until M08.** Teammates are invited in M02 so they can install and read (the instructor is invited later, by hand, by Mike); until M08 the ruleset needs a PR but 0 approvals. Team rule: start no task and merge nothing until M08 assigns your first issue. Accepted risk for 1–2 days. | 2026-11-08 |
| D-28 | **Project board access:** the board is owned by `mlip3191`, linked to the repo, with the four teammates added as project collaborators (Write) and auto-add turned on for new issues and PRs. | 2026-11-08 |
| D-29 | **Critical-file scope:** only the root `/scripts/` folder is critical (not `backend/scripts/`). `.gitleaksignore` is critical, since it can silence the secret scan. | 2026-11-08 |
| D-30 | **QA bot trust boundary:** before running, the bot replaces the PR's `.claude/` and `CLAUDE.md` with `main`'s copies, so a PR can't change the bot's rules or hooks. | 2026-11-08 |
| D-31 | **Gunnar is the backup approver** for critical-file PRs when Mike is unavailable; the critical-files check accepts his approval on PRs he didn't write. | 2026-11-08 |
| D-32 | **Behavioral stats are assumptions, not sourced facts.** Aggression, group tactics, and armor use method `assumption` with a written 5-level rubric (`docs/research.md`); the UI tags them. Every stat carries a plausible range, and the simulation samples within it, so the win-probability range reflects input uncertainty. Engine constants are documented in `docs/simulation-model.md`. | 2026-11-08 |
| D-33 | **Size phrases use a `size_reference` field** ("horse-sized duck" → entity duck, reference horse). The scale factor is computed by code from both sourced masses; the model only names the reference. Added to the contracts before M05. | 2026-11-08 |
| D-34 | **Actions-minutes downgrade plan:** below ~600 remaining minutes, stop macOS runs, then make Windows CI on-demand and require only the Linux checks (steps in INIT.md "After Phase 0"). | 2026-11-08 |
| D-35 | **Lane changes after the grading review:** Gunnar keeps G05 (15 sheets: the 9 real showcase fighters, the dragon's two analogs, and 4 more — revised by D-40; the first five — horse, duck, grizzly, wolf, honey badger — by Nov 14, the rest by Nov 18). The clarifying-question backend moves from Adam to Dillon (now D08) and the sprite/image backend from Dillon to Adam (now A08). New: M09 live AI evaluation (Mike), D09 user guide and D10 usability sessions (Dillon). | 2026-11-08 |
| D-36 | **Next challenger uses the Structured Decisions model**, as the proposal specified, choosing only among seed and already-cached fighters so the 10-second budget holds. | 2026-11-08 |
| D-37 | **Evaluation measures the AI, not just the simulator:** 10 benchmark matchups are held out from all tuning; the benchmark runs with hand-verified and research-only sheets; M09 reports extraction accuracy, sourced share, retrieval, live intake and safety accuracy, and cost per battle (`docs/evaluation.md`). | 2026-11-08 |
| D-38 | **Any physical fighter (Mike, 2026-11-08):** objects, plants, vehicles, machines, and mythical/folklore creature *types* are in the MVP. Rules: stats follow the number rule (objects and vehicles are sourced or labeled estimates; mythical creatures are built by code from real "analog" animals and every stat is an assumption, shown as "according to legend"); each sheet gets `body` (living / machine / inert), a brand-free `media_name`, and `lore` for legends. **Still blocked:** real people, minors, groups of people, sexual content, named fictional characters (including film/game/toy robots and vehicles), named deities and religious figures, modern firearms, explosives and weapons of mass destruction, and abstract ideas, places, landforms, or celestial bodies. Brand-name products are allowed but drawn and scored generically. Vehicle guns aren't modeled (ramming and crushing only). | 2026-11-08 |
| D-39 | **New tasks for D-38:** G09 (Gunnar: categories, sourcing, `mythical.yaml`, on-demand legends) and F08 (Felipe: machine/inert bodies, abilities); both lanes go to 15 points. Smaller additions in M05, M08, M09, A02, A04, A06–A08, G01, G04, G06, G07, D03, D04. Seed list 25 → 30; safety set 40 → 50. | 2026-11-08 |
| D-40 | **Showcase battle 5 is "a dragon vs a main battle tank" (open field)**, replacing great white shark vs saltwater crocodile, to demo D-38. The dragon is built by G09 from hand-verified analogs (saltwater crocodile, African elephant) and fought with F08's abilities, so G08 now depends on G09 and F08. | 2026-11-08 |
| D-41 | **Stat extraction uses the chat model (port 9001) in JSON-schema mode; Structured Decisions (port 9010) only makes decisions.** M06 found 9010 is a decision model: it answers named choice, score, and yes/no questions with calibrated probabilities (`POST /v1/decisions`) and can't return free text such as a value, unit, and quote. So G04's extraction and G09's on-demand creatures ask the chat model for `{value, unit, quote}` (or analogs, abilities, and quote) via `ChatLLM.complete(..., json_schema=...)`. The number rule is unchanged: code accepts a value only if the number appears in the quote and the quote appears in the passage. 9010 keeps the decision jobs, starting with the next-challenger pick (D-36) as a choice question; `StructuredLLM.extract(prompt, schema)` becomes `StructuredLLM.decide(state, questions, *, prompt_name)`, which returns a choice, a probability per option, and a confidence for each question (#58). | 2026-11-09 |
| D-42 | **Venom is modeled** (Mike, after Felipe's showcase dry run #77). Showcase battle 3, honey badger vs king cobra, was a 100% badger win in 3 seconds because the engine had no venom. A venomous bite now applies damage over time and a target can resist it; every venom constant is a code assumption documented in `docs/simulation-model.md`, and the explanation can name venom or resistance as the deciding factor. Rejected: inflating venomous fighters' attack force (blurs the number rule) and swapping the matchup. Built in #81 (F-lane, after F05). | 2026-11-09 |
| D-43 | **Dragon vs tank calibration waits for G09's real dragon sheet.** With stand-in sheets the tank wins 100%: hit points scale with mass, so a 60-tonne tank outlasts the breath attack, and only the breath constant moves the odds. No change to `BREATH_DAMAGE_N` or machine hit points until the real sheet exists; a tank win is acceptable ("a fair fight is about 6 dragons" is a good demo line). Related: the swarm-model improvement (#76) stays in Backlog until after the F07 baseline, since no showcase battle exceeds 200 per side. | 2026-11-09 |
| D-44 | **Venom is resolved after the fight, on a realistic timescale** (refines D-42; Mike, after Felipe's spike on #81). Real venom acts over minutes and these fights last seconds, so a dose rarely lands in time: in the spike, badger vs cobra stayed 100/0 at every potency and resistance. So doses play out over minutes (no constants tuned to force a result), and when one side is wiped out, a survivor carrying a lethal unresisted dose still dies; if no one is left standing, the result is a draw. Resistance comes from a per-fighter assumption table in `constants.py`. No contract change: the deciding factor is reported as `attack_force_n` with an explainer sentence that names venom or resistance. The certain-result shortcut (#87) must include the venom dose in its bound. Rejected: compressing venom to seconds (unrealistic, tuned constants); waiting for real sheets alone (they refine the numbers but don't fix the timescale). | 2026-11-09 |
| D-25 | **No Docker.** The app runs with `npm start`: the backend serves the built front end and the API together at http://localhost:8000, so the instructor needs only Node 26 and uv. | 2026-11-08 |
| D-24 | **Showcase battles ship with the repo** (`data/showcase/`, small, committed) so the instructor's clone shows the five demo battles even before he fills `.env`. | 2026-11-08 |

## Changes from the proposal

Each one is deliberate and recorded here, so it reads as a decision, not a broken promise. This list feeds the deck.

| Proposal said | We're doing | Why |
|---|---|---|
| Hermes Primary Model + Hermes Agent as the AI coding agent | Claude Code builds the app; Hermes Agent builds one task (G06) as a documented comparison | The team's guardrails and review tooling are built on Claude Code (D-02) |
| Four team members | Five: Dillon joined | D-06 |
| Docker Compose implied by the stack | One command, `npm start`, no Docker | Simpler for non-coders and the instructor (D-25) |
| Voice cloning for the announcer | A stock gruff, deep voice first; cloning only with written consent | Consent and time (D-09) |
| Every stat from sources | Seven physical stats from sources or labeled estimates; three behavioral stats labeled assumptions from a rubric | No source measures aggression or armor; honesty over false precision (D-32) |
| Benchmark against expert answers | Benchmark plus held-out set plus a live evaluation of the AI parts | Measure the GenAI, not just the simulator (D-37) |
| Any media cut under the cut order | (fill in at code complete) | LANES.md cut order |

## Recommended datasets (D-20)

The proposal promised Wikipedia, Wikidata, and Hugging Face datasets. Recommended set, in priority order:

| # | Dataset | Where | What we use it for | License | Notes |
|---|---|---|---|---|---|
| 1 | **Wikipedia Structured Contents** (`wikimedia/structured-wikipedia`) | Hugging Face | Main RAG text: article abstracts, sections, and **parsed infoboxes**, each linked to its Wikidata ID | CC BY-SA 4.0 / GFDL | Official Wikimedia dataset. Never download or stream the whole thing: look up individual fighters through the Hugging Face Dataset Viewer API. Article text itself comes from the Wikipedia REST API (same content, much faster). If the viewer lookup is impractical, mirror our small trait subset (#4–5) as a team dataset on Hugging Face instead. |
| 2 | **FineWiki** (`HuggingFaceFW/finewiki`) | Hugging Face | Backup text source with infobox JSON and `wikidata_id` per article, built from recent Wikimedia dumps | CC BY-SA (Wikipedia) | Use if #1 lacks an article or is stale. |
| 3 | **Wikidata** (live API, no key) | wikidata.org | High-confidence numbers with property IDs and references (mass, length, speed when present); "is this a real human?" check | CC0 | Not a Hugging Face dataset; already in the plan (G02, A04). |
| 4 | **PanTHERIA** (mammal traits) | Ecological Archives / figshare (mirror to a team HF dataset if we want it "on HF") | Adult body mass, head-body length, limb length, group size for ~5,400 mammals | CC0 | Peer-reviewed, citable; ideal for `mass_kg` and `size_m`. |
| 5 | **AnimalTraits** (body mass, metabolic rate, brain size) | Scientific Data 2022 (download linked from the paper) | Body mass for ~2,000 terrestrial species incl. arthropods, reptiles, birds | CC BY 4.0 | Covers insects/spiders that PanTHERIA doesn't. Metabolic rate can inform `endurance_s`. |
| 6 | **TreeOfLife taxonomy metadata** (`imageomics/TreeOfLife-10M`, `metadata/` only) | Hugging Face | Common name → scientific name → class/order, for normalizing fighter names and setting `category` | CC0 | Optional; download only the taxonomy CSV, not the images. |

**Avoid (confirmed by Mike, 2026-11-08):** Kaggle-style "animal facts" tables and Hugging Face uploads whose cards say values were generated with AI or have no sources — for example `pcwoods/2026-animaldescription-text-dataset`, whose card says generative AI was used to identify the animal facts. They would break the "every number is traceable" promise. Speed, bite force, and armor rarely appear in trait databases; those come from Wikipedia text through the verified-quote extractor, or from code estimates.
