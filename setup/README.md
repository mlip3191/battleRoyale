# setup/

Ready-made files that Phase 0 tasks install. They live here, not in `.github/workflows/`, so they don't run before the secrets and settings they need exist.

| File | Installed by | Becomes |
|---|---|---|
| `templates/workflows/secret-scan.yml` | M07 | `.github/workflows/secret-scan.yml` — required check "Secret scan" |
| `templates/workflows/ai-qa-review.yml` | M07 | `.github/workflows/ai-qa-review.yml` — **advisory** QA bot, not a required check (needs the `CLAUDE_CODE_OAUTH_TOKEN` secret, DECISIONS D-04) |

Already active at the repo root: `.gitignore`, `.env.example`, `.githooks/pre-commit`, `CLAUDE.md`, `.claude/skills/review-prs/`, `.claude/agents/code-reviewer.md`, `.claude/qa/checklist.md`, `.claude/commands/review.md`, `.claude/commands/qa.md`.
