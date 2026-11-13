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
- M07: done
- M08: done

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

### D-34 fallback: Linux-only required checks (ready to apply)

**Minutes snapshot (2026-11-09):** about 289 of 3,000 billed Actions minutes used in November (90 runs: 99 Linux job-minutes ×1, 85 Windows ×2, 2 macOS ×10; each job rounded up to a whole minute). One PR push costs roughly 10–13 billed minutes, most of it the two Windows jobs. Estimated from job timings, because the billing API needs the `user` token scope (`gh auth refresh -s user` to read it directly).

**When:** fewer than ~600 minutes remain (check Settings → Billing weekly). Step 1 is to stop manual macOS runs; this is step 2.

**Step 2a — CI runs Windows only on demand.** In `.github/workflows/ci.yml` (protected; PR needs PM approval), change the default matrix in both jobs from `'["ubuntu-latest","windows-latest"]'` to `'["ubuntu-latest"]'`. `workflow_dispatch` still accepts `windows-latest`, so step 3 is `gh workflow run ci.yml --ref main -f os=windows-latest` before each milestone.

**Step 2b — the ruleset stops requiring the Windows checks.** Save this as `.claude/tmp/ruleset-linux.json` and run `gh api repos/mlip3191/battleRoyale/rulesets/26832578 --method PUT --input .claude/tmp/ruleset-linux.json`. Do 2a and 2b together: if 2b comes first nothing breaks; if 2a comes first, PRs wait forever for Windows checks that never run.

```json
{
  "name": "main protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "bypass_actors": [],
  "rules": [
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 1,
      "dismiss_stale_reviews_on_push": false,
      "required_reviewers": [],
      "require_code_owner_review": false,
      "require_last_push_approval": false,
      "required_review_thread_resolution": false,
      "require_extra_approval_for_unattributed_changes": true,
      "allowed_merge_methods": ["merge", "squash", "rebase"]}},
    {"type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": false,
      "do_not_enforce_on_create": false,
      "required_status_checks": [
        {"context": "backend (ubuntu-latest)", "integration_id": 15368},
        {"context": "frontend (ubuntu-latest)", "integration_id": 15368},
        {"context": "Secret scan", "integration_id": 15368},
        {"context": "Critical files approval", "integration_id": 15368}]}},
    {"type": "non_fast_forward"},
    {"type": "deletion"}
  ]
}
```

**Switch back** (new month, minutes reset): restore the two-OS matrix in `ci.yml`, then add `{"context": "backend (windows-latest)", "integration_id": 15368}` and `{"context": "frontend (windows-latest)", "integration_id": 15368}` back to `required_status_checks` and run the same `gh api ... --method PUT` command.

### Notes

- Node changed from 24 to 26 (current LTS) before M04 (DECISIONS D-12).
- M02: hook test passed with decoys (fake AWS-format key and `hook-test/decoy.env` both blocked, key never printed); light ruleset "main protection" (id 26832578): PR required with 0 approvals, force push and deletion blocked, no bypass; teammates invited with Write.
- M03: `.claude/settings.json` + hooks (`guard-shell.mjs`, `ensure-hookspath.mjs`, `format-on-edit.mjs`); `node .claude/hooks/test-hooks.mjs` → 119 cases, 0 failed.
- M04: create-vite 9.3.4 (`react-ts` template). The template now ships oxlint; replaced with ESLint + Prettier as documented (Mike approved adding `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `globals`). TypeScript pinned to 5.9 because `typescript-eslint` (<6.1) and `openapi-typescript` (^5) don't support TypeScript 7 yet. Phaser pinned to 3.x (npm's latest is 4). `npm audit`: 10 moderate (minimatch, dev tooling only), 0 high.
- M05: 16 contract models in `backend/app/models/` (no deviations from ARCHITECTURE §5). Additions within the documented rules: models reject unknown fields; validators also enforce the number-rule table (`is_estimate` ⇔ estimate method, `hand_verified` needs a source, `derived` needs a note, every mythical stat is an assumption). `display_name`/`media_name` allowlist = letters, digits, spaces, hyphens (ARCHITECTURE §11), so the grizzly's display name is "Grizzly bear - adult male". Fixture quotes copied from Wikipedia on 2026-11-09 and checked word for word.
- M06: 8 provider interfaces (`providers/base.py`) with deterministic offline mocks; `get_provider(name)` picks mock or live and names missing settings (never values); `GET /api/health` reports `provider_mode` and all 8 providers. Smoke test (run by Mike's session on 2026-11-09): all 10 configured services reachable, redaction scan 0 remaining, Mike confirmed `docs/providers.md` is clean; live chat via `providers/live/chat.py` returned plain and JSON-schema completions. Deviations: mock embedding dimension is a constant (64) in the mock, since `config.py` has no setting for it; tests live in `backend/tests/unit/`. Finding for follow-up: port 9010 "Structured Decisions" answers choice/score/yes-no questions, not schema-shaped extraction, so ARCHITECTURE §7's `StructuredLLM.extract` plan needs a PM decision (suggested: extract stats with chat JSON-schema mode).
- M07: Secret scan, advisory QA bot, Critical files approval, CODEOWNERS, PR template. The QA bot's own `gh pr comment` calls were denied by its tool permissions, so the bot now returns its report in structured output and a workflow step posts it. Adding `re-review` within seconds of a push may not start a run; remove and re-add the label.
- M08: 21 labels. Issues: #9-#16 closed Phase 0 records (#14 is the course-key setup), #17 M08, #18-#51 the 34 tasks (labeled, assigned, with "Blocked by" links).
  Board https://github.com/users/mlip3191/projects/2: Backlog / Ready / In progress / In review / Done; Wave 1 (#18-#21) in Ready; auto-add, "item added → Backlog", and "PR merged → Done" are on; teammates have Write.
  Dry run: issue #52, PR #53.
  Ruleset "main protection" (id 26832578) read back: PR with 1 approval; required checks = 4 CI + Secret scan + Critical files approval; force push and deletion blocked; no bypass; D-26's four options off. Team board: #54 (pinned).
- Kickoff call held 2026-11-09: all five attended; everyone's `npm run env:check` shows all ok and `npm run setup` works. Recap on the Team board (#54). No weekly meeting: written Done / Doing / Blocked check-ins on #54 instead.

## Milestones

### MS-1 walking skeleton (due Sat Nov 14), started Nov 10, final on Nov 14

- **What works (Nov 12, evening; `main` at 70d0169):**
  - **MS-1 status:** both gaps from Nov 10 have landed: the A05 stub path that starts a battle and returns a verdict on mocks (#197) and the intake API with its one clarifying question (D08, #158). **Confirmed on Nov 12:** running the app on `main` at 70d0169 in mock mode, "a grizzly bear vs a gorilla" gives the parsed fight card, all nine pipeline stages finish, and the Battle page shows the verdict and links to the full Results page (screenshots below).
  - **Built:** the engine (F02–F06, F08 and the tournament bracket; F07, the benchmark runner, is still a draft), with swarm mode now matching the one-by-one engine (#106), venom resolved after the fight (#107) and a proof that more fighters never hurt above the swarm threshold (#108). The live-tested intake parser (A02, #137, #140) and its follow-ups (#147, #231, #236, #237, #239), the first part of the A04 safety gate (#152) and a mock safety classifier for offline demos (#241). The pipeline's stage graph with time budgets, its next-challenger stage, and battle persistence with a repeat-battle cache (A05, #199, #200, #203). Narration part 1: the number guard, the fact list and the template scripts (A06, #216, #217, #218) with the number-guard and fair-fight wording fixes (#252, #253), and `script_kind` on narration assets (#247). The knowledge base with retrieval and reranking (G02, G03, #150), the benchmark matchup set and pass rules (G07, #129), the seed ingest with Wikidata, PanTHERIA and AnimalTraits facts (#190, #196), the stat-sheet builder without model extraction (G04 part 1, #232) and 14 hand-verified seed sheets (G05, most recently the king cobra and Roman legionary, #243, and the African lion, bulldozer and bald eagle, #254). Fighter sprites and battlefield images (A08, #248). The app shell and intake page with its outage and expired-question messages (D02, D03, #207), the wired Results page (D04, #127, #128), the Phaser battle stage with replay controls (D05, #121, #123), and the broadcast Battle page with caption sync, sound controls and degraded modes (D07, #187, #188).
  - **Approved or in review, not on `main` yet:** the announcer LLM writer (A06 part 2, #244, approved), the house cat, the 15th and last seed sheet (#257, approved), swarm mode chosen by work (D-50 build, #193, changes requested), and the rest of A04 (draft #156 and the stacked drafts #161, #164, #165 and #185; #185 closes #27).
- **What changed from the plan:**
  - **D-41:** the chat model extracts stats; port 9010 only answers decisions.
  - **D-42/D-44:** venom is modeled and resolved after the fight (built in #107).
  - **D-43:** dragon-vs-tank calibration waits for G09's real dragon sheet; no changes to breath damage or machine hit points until then.
  - **D-45:** swarm mode matches the one-by-one engine (built in #106).
  - **D-46:** plain-slug fighter IDs, two dataset licenses, derived machine values.
  - **D-47:** seed-sheet labeling rules.
  - **D-48:** the repo is public, after GitHub Actions stopped on the private repo for billing.
  - **D-49:** the PM or the backup may merge a teammate's approved PR after an @mention.
  - **D-50:** swarm mode is chosen by how much work a fight is, not by head count (recorded in #184, wording refined in #194; build in review in #193).
  - **D-51:** a bare lowercase word that matches a famous name stays a possible proper name unless the name is also a common word (not built yet, issue #186).
  - **D-52:** the intake budget is about 7 s typical with a 25 s limit, not 3 s.
  - **D-53:** a published arm length counts as reach; an arm span alone doesn't.
  - **D-54:** the king cobra may have 4 estimates and the Roman legionary 3.
  - **D-55:** the house cat may have 3 estimates, a kill hold isn't fighting endurance, and the image-style templates may stay in code (in review in #256).
  - **The board:** the "PR linked → In review" automation was turned on (#172).
- **Screenshots (Nov 12, mocks):** [the parsed fight card](media/ms1-tonights-card.jpg) and [the verdict on the Battle page](media/ms1-verdict.jpg).
