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

## M09 · Live AI evaluation: does the GenAI actually work? · M (2)

**When:** Wave 4 (Nov 18–21), after G04, G06, F07, and A04 have landed. Results feed the Limitations and Build Process material for the deck.
**Goal:** Measure the AI parts against real endpoints, not mocks, so "science-backed" is backed by numbers about the AI itself. The benchmark (F07) tests the simulator; this tests intake, safety, retrieval, and extraction.
**Read first:** PRODUCT_SPEC §7; `docs/benchmark.md`; `docs/research.md`.

**Prompt for Claude Code:**
```text
Task M09 from docs/plan/lane-1-mike.md. Build backend/scripts/evaluate_ai.py (live mode only; never in CI) and write docs/evaluation.md. Measure:
1. Extraction accuracy: for each hand-verified fighter in data/seed/fighters/, build a sheet with the research pipeline ONLY (ignore the seed file), then compare stat by stat to the hand-verified value: share within 10% / within 25% / wrong, share returned as estimates, and how many extracted values failed quote verification.
2. Retrieval: hit@5 on backend/tests/fixtures/retrieval_cases.yaml (G03).
3. Coverage on new fighters: for 10 fighters NOT in the seed list, the share of the 7 sourced stats that came from sources vs. estimates.
4. Intake accuracy on the live chat model: run the 25+ A02 phrasings; exact-match rate on entity, count, and terrain.
5. Safety on the live model: precision and recall on the 40-case set (A04), plus the injection cases.
6. Benchmark twice (via F07's runner): with seed sheets, and with research-only sheets, on the held-out subset that was frozen before tuning (G07). Report both.
7. Cost and speed: endpoint calls per battle by service, cache hit rate on a repeat run, median and 90th-percentile time to verdict and to full show.
Write docs/evaluation.md with a one-paragraph summary, a table per section, the date, the commit, and an honest "what this means / limitations" section. Never print or write endpoint hosts or keys.
```

**Acceptance criteria**
- [ ] `docs/evaluation.md` with all seven sections, run against live endpoints
- [ ] Held-out benchmark reported both ways (seed vs research-only)
- [ ] Limitations stated plainly (estimates, behavioral assumptions, two-sided only)

---

## After Phase 0

Mike's ongoing duties are listed at the end of Part 3 in [INIT.md](../../INIT.md). Code-complete duties (Nov 25) are in [DELIVERABLES.md](DELIVERABLES.md).
