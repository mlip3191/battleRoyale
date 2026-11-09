# Build Log

The single source of truth for Phase 0 progress (INIT.md), plus three lines at each milestone afterwards (DELIVERABLES.md).

## Phase 0

Started 2026-11-08 by Mike with Claude Code (Opus 5.5).

### Progress

- M01: done
- M02: done
- M03: done — live checks passed
- M04: done
- M05: done
- M06: done
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
- M02: hook test passed with decoys (fake AWS-format key and `hook-test/decoy.env` both blocked, key never printed); light ruleset "main protection" (id 26832578): PR required with 0 approvals, force push and deletion blocked, no bypass; teammates invited with Write.
- M03: `.claude/settings.json` + hooks (`guard-shell.mjs`, `ensure-hookspath.mjs`, `format-on-edit.mjs`); `node .claude/hooks/test-hooks.mjs` → 119 cases, 0 failed.
- M04: create-vite 9.3.4 (`react-ts` template). The template now ships oxlint; replaced with ESLint + Prettier as documented (Mike approved adding `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `globals`). TypeScript pinned to 5.9 because `typescript-eslint` (<6.1) and `openapi-typescript` (^5) don't support TypeScript 7 yet. Phaser pinned to 3.x (npm's latest is 4). `npm audit`: 10 moderate (minimatch, dev tooling only), 0 high.
- M05: 16 contract models in `backend/app/models/` (no deviations from ARCHITECTURE §5). Additions within the documented rules: models reject unknown fields; validators also enforce the number-rule table (`is_estimate` ⇔ estimate method, `hand_verified` needs a source, `derived` needs a note, every mythical stat is an assumption). `display_name`/`media_name` allowlist = letters, digits, spaces, hyphens (ARCHITECTURE §11), so the grizzly's display name is "Grizzly bear - adult male". Fixture quotes copied from Wikipedia on 2026-11-09 and checked word for word.
- M06: 8 provider interfaces (`providers/base.py`) with deterministic offline mocks; `get_provider(name)` picks mock or live and names missing settings (never values); `GET /api/health` reports `provider_mode` and all 8 providers. Smoke test (run by Mike's session on 2026-11-09): all 10 configured services reachable, redaction scan 0 remaining, Mike confirmed `docs/providers.md` is clean; live chat via `providers/live/chat.py` returned plain and JSON-schema completions. Deviations: mock embedding dimension is a constant (64) in the mock, since `config.py` has no setting for it; tests live in `backend/tests/unit/`. Finding for follow-up: port 9010 "Structured Decisions" answers choice/score/yes-no questions, not schema-shaped extraction, so ARCHITECTURE §7's `StructuredLLM.extract` plan needs a PM decision (suggested: extract stats with chat JSON-schema mode).
