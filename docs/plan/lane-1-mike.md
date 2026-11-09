# Lane 1 — Mike Lippert (PM): Foundation & Platform

**Total effort: 16 points.** Phase 0 tasks M01–M08 (14 points) live in **[INIT.md](../../INIT.md)** at the repo root — the single document Mike gives Claude Code to initialize the project. Mike runs them alone, in order. After Phase 0 Mike reviews, integrates, and runs **M09, the live AI evaluation** (below): Mike didn't build the research pipeline, so his evaluation of it is independent.

**Backup approver:** Gunnar (`gunnaroc`) approves critical-file PRs when Mike is unavailable (DECISIONS D-31).

| ID | Task | Size |
|---|---|---|
| M01 | GitHub repo settings, security, and Actions permissions | S |
| M02 | Line endings, build log, guardrail tests, light ruleset, early invites | S |
| M03 | Claude Code settings, permissions, and hooks (needs one restart) | M |
| M04 | Monorepo skeleton, one-command start, cross-platform files, CI | M |
| M05 | Shared contracts: Pydantic models, JSON Schema, fixtures, TS types | M |
| M06 | Provider layer: interfaces, mocks, config, live chat adapter, smoke test | M |
| M07 | Review tooling: advisory QA bot, Secret scan, critical-files check, CODEOWNERS, PR template | M |
| M08 | Labels, issues, project board, full branch protection, dry run, assignments | M |
| M09 | Live AI evaluation: does the GenAI actually work? | M |

**Definition of Done for every task (CLAUDE.md §7), on top of its own acceptance criteria:** at least one test for every code change (docs-only tasks such as G01, G07, F01, D09, and D10 are checked by the reviewer instead); `npm run check` passes; the app still starts with `npm start`; the PR uses the template with `Closes #<n>`, explains the change in plain English, and ticks each criterion with its evidence (test name, command output, link, or screenshot); docs updated if behavior changed; a teammate approved and all required checks passed before merging. Criteria marked "live" are run by the task owner on their own machine (never in CI), and the pasted results never include endpoint hosts or keys. (Phase 0 tasks M01–M08 follow INIT.md's own merge flow instead.)

## M09 · Live AI evaluation: does the GenAI actually work? · M (2)

**When:** Wave 4 (Nov 18–21), after G04, G06, F07, and A04 have landed. Results feed the Limitations and Build Process material for the deck.
**Goal:** Measure the AI parts against real endpoints, not mocks, so "science-backed" is backed by numbers about the AI itself. The benchmark (F07) tests the simulator; this tests intake, safety, retrieval, and extraction.
**Read first:** PRODUCT_SPEC §7; `docs/benchmark.md`; `docs/research.md`.

**Prompt for Claude Code:**
```text
Task M09 from docs/plan/lane-1-mike.md. Build backend/scripts/evaluate_ai.py (live mode only; never in CI) and write docs/evaluation.md. Measure:
1. Extraction accuracy: for each hand-verified fighter in data/seed/fighters/, build a sheet with the research pipeline ONLY (ignore the seed file), then compare stat by stat to the hand-verified value: share within 10% / within 25% / wrong, share returned as estimates, and how many extracted values failed quote verification.
2. Retrieval: hit@5 on backend/tests/fixtures/retrieval_cases.yaml (G03).
3. Coverage on new fighters: for 10 fighters NOT in the seed list (5 animals, 3 objects or machines, 2 mythical creatures not in data/seed/mythical.yaml), the share of the 7 physical stats that came from sources vs. estimates vs. assumptions, reported by kind; for the mythical ones, whether the chosen analogs are sensible (your judgment, one line each).
4. Intake accuracy on the live chat model: run the 25+ A02 phrasings; exact-match rate on entity, count, and terrain.
5. Safety on the live model: precision and recall on the 50-case set (A04), plus the injection cases.
6. Benchmark twice (via F07's runner): with seed sheets, and with research-only sheets, on the held-out subset that was frozen before tuning (G07). Report both.
7. Cost and speed: endpoint calls per battle by service, cache hit rate on a repeat run, median and 90th-percentile time to verdict and to full show.
Write docs/evaluation.md with a one-paragraph summary, a table per section, the date, the commit, and an honest "what this means / limitations" section. Never print or write endpoint hosts or keys.
```

**Acceptance criteria**
- [ ] `docs/evaluation.md` has all seven sections and a one-paragraph summary, with numbers from live endpoints, the run date, and the commit hash
- [ ] Extraction: a per-stat comparison for every hand-verified fighter (within 10% / within 25% / wrong / returned as estimate) and the count of quote-verification failures
- [ ] Intake exact-match rate on the A02 phrasings; safety precision and recall on the 50-case set plus the injection results
- [ ] The held-out benchmark is reported for both seed and research-only sheets
- [ ] Cost and speed: endpoint calls per battle by service, the cache hit rate on a repeat run, and median and 90th-percentile time to verdict and to full show
- [ ] The Limitations section names at least: estimates, behavioral assumptions, two-sided matchups only, and dependence on the course endpoints
- [ ] The redaction scan finds no host or key in the file

---

## After Phase 0

Mike's ongoing duties are listed at the end of Part 3 in [INIT.md](../../INIT.md). Code-complete duties (Nov 25) are in [DELIVERABLES.md](DELIVERABLES.md).
