# Lane 1 — Mike Lippert (PM): Foundation & Platform

**Total effort: 14 points.** Phase 0 tasks M01–M08 live in **[INIT.md](../../INIT.md)** at the repo root — the single document Mike gives Claude Code to initialize the project. Mike runs them alone, in order, before anyone else is invited.

| ID | Task | Size |
|---|---|---|
| M01 | GitHub repo settings, security, and Actions permissions | S |
| M02 | Verify guardrail files, switch on the git hook, finalize CLAUDE.md | S |
| M03 | Claude Code settings, permissions, and hooks | M |
| M04 | Monorepo skeleton, toolchain pins, cross-platform files, CI | M |
| M05 | Shared contracts: Pydantic models, JSON Schema, fixtures, TS types | M |
| M06 | Provider layer: interfaces, mocks, config, live chat adapter, smoke test | M |
| M07 | Review tooling: QA bot, Secret scan, critical-files check, CODEOWNERS, PR template | M |
| M08 | Labels, issues from the plan, project board, branch protection, dry run, invites | M |

## After Phase 0 — Mike's ongoing duties (not pointed)

- Triage weekly: move ready issues to Ready, split anything that turns out L.
- Approve every PR that touches a critical file (the critical-files check enforces it).
- Own `docs/ARCHITECTURE.md` and `docs/DECISIONS.md`; record each decision.
- Run `scripts/smoke_providers.py` whenever an endpoint changes.
- Merge Dependabot PRs after CI and the QA bot pass.
