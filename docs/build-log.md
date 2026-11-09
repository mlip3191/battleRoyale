# Build Log

The single source of truth for Phase 0 progress (INIT.md), plus three lines at each milestone afterwards (DELIVERABLES.md).

## Phase 0

Started 2026-11-08 by Mike with Claude Code (Opus 5.5).

### Progress

- M01: done
- M02: committed — hook test, light ruleset, invites pending
- M03: not started
- M04: not started
- M05: not started
- M06: not started
- M07: not started
- M08: not started

### M01 — repo settings (read back from the GitHub API, 2026-11-08)

| Setting | Value |
|---|---|
| GitHub plan (`gh api user --jq .plan.name`) | `pro` |
| Visibility | `PRIVATE` |
| Squash / merge commit / rebase merging | `true` / `false` / `false` |
| Automatically delete head branches | `true` |
| Always suggest updating pull request branches | `true` |
| Dependabot alerts | enabled |
| Dependabot security updates | enabled |
| Default workflow permissions | `read` |
| Actions can create and approve pull requests | `false` |
| Allowed actions | GitHub-made, plus `anthropics/claude-code-action@*`, `oven-sh/setup-bun@*`, `gitleaks/gitleaks-action@*`, `astral-sh/setup-uv@*` (verified creators off) |
| Rulesets | none (light ruleset added in M02) |
| GitHub secret scanning / push protection | not offered for this private personal repo; covered by the local git hook and the gitleaks Secret scan (M07) |

### Notes

- Node changed from 24 to 26 (current LTS) before M04 (DECISIONS D-12).
