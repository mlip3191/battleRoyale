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

### MS-1 walking skeleton (due Sat Nov 14), started Nov 11, final on Nov 14

Dates are Mountain Time.

- **What works (Nov 14; `main` at 5da83dc):**
  - **MS-1 status: met.** Running the app on `main` at cb41095 in mock mode (`npm start`), "a grizzly bear vs a gorilla" gives the parsed fight card, all nine pipeline stages finish, the Phaser stage plays the fight to its end banner, and the Battle page shows the verdict and links to the full Results page with the cited tale of the tape (screenshots below). No errors in the browser console or the server log during the browser run. API re-run on 5da83dc (no browser), after battles switched to the stat-sheet builder (#269): the same nine stages and the same verdict. The script stage ends "fallback" on mocks by design: the mock play-by-play has no canned reply, so the template play-by-play, which follows the real fight log, is used. First confirmed on Nov 12 at 70d0169, after the A05 stub path (#197) and the intake API with its one clarifying question (D08, #158) landed.
  - **Known issue:** the gorilla wins 79% because its 3,420 N bite is a modeled molar maximum compared with the grizzly's canine bite (#260; ruled: use the code's carnivore fit, about 1,016 N). Fixed in #260 (Nov 16): the grizzly now wins 83%.
  - **Built by Nov 12:** the engine (F02–F06, F08 and the tournament bracket; F07, the benchmark runner, is in review in #72), with swarm mode now matching the one-by-one engine (#106), venom resolved after the fight (#107) and a proof that more fighters never hurt above the swarm threshold (#108). The live-tested intake parser (A02, #137, #140) and its follow-ups (#147, #231, #236, #237, #239), the first part of the A04 safety gate (#152) and a mock safety classifier for offline demos (#241). The pipeline's stage graph with time budgets, its next-challenger stage, and battle persistence with a repeat-battle cache (A05, #199, #200, #203). Narration part 1: the number guard, the fact list and the template scripts (A06, #216, #217, #218) with the number-guard and fair-fight wording fixes (#252, #253), and `script_kind` on narration assets (#247). The knowledge base with retrieval and reranking (G02, G03, #150), the benchmark matchup set and pass rules (G07, #129), the seed ingest with Wikidata, PanTHERIA and AnimalTraits facts (#190, #196), the stat-sheet builder without model extraction (G04 part 1, #232) and 14 hand-verified seed sheets (G05, most recently the king cobra and Roman legionary, #243, and the African lion, bulldozer and bald eagle, #254). Fighter sprites and battlefield images (A08, #248). The app shell and intake page with its outage and expired-question messages (D02, D03, #207), the wired Results page (D04, #127, #128), the Phaser battle stage with replay controls (D05, #121, #123), and the broadcast Battle page with caption sync, sound controls and degraded modes (D07, #187, #188).
  - **Built Nov 13–14:** the announcer LLM writer, wired into the pipeline (A06 part 2, #244, #261), with number words in fighter names ignored by the number guard (#262), an honest "template commentary" notice (#272), narration that matches each broadcast phase (#268), and announcer audio and music through the mock providers (#276). The house cat, so all 15 seed sheets are on `main` (G05, #257). Model stat extraction with verified quotes (G04 part 2, #266), and the stat-sheet builder used in battles, with `/api/fighters` (G04 part 3, #269). The 12 mythical creature types and brand-safe media names (G09, #264, #291). Seed trait rows loaded from the team's Hugging Face dataset, pinned to one dataset version (G02, #288, #292). A showcase dry run on the real seed sheets (#282). On the front end: why a battle failed, on the Battle and Results pages (#265); crowd replay logs only in fixtures mode (#267); a skip link and per-page tab titles (#275); a tighter API client (#278); and the whole winning side named in the end banner (#286). A shared pluralizer (#263, #273), and waiting for a fresh database instead of failing with "locked" (#298).
  - **Approved or in review, not on `main` yet:** mythical creature sheets from their analogs and on demand (G09, #274, #293), the showcase export and startup import (G08 part 1, #295), keeping mock media out of the live cache (#299), the one-word answer splice (#297, changes requested), and the F07 benchmark runner (#72), whose first live baseline left three cases for a PM decision (#304). Swarm mode chosen by work (D-50 build, #193, changes requested). Drafts: the rest of A04 (#156 and the stacked #161, #164, #165 and #185; #185 closes #27) and the first-time user guide (D09, #294).
- **What changed from the plan:**
  - **D-41:** the chat model extracts stats; port 9010 only answers decisions.
  - **D-42/D-44:** venom is modeled and resolved after the fight (built in #107).
  - **D-43:** dragon-vs-tank calibration waits for G09's real dragon sheet (in review in #274); no changes to breath damage or machine hit points until then.
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
  - **D-55:** the house cat may have 3 estimates, a kill hold isn't fighting endurance, and the image-style templates may stay in code.
  - **D-56:** fighter loadouts and progression are post-MVP, and raising `HIT_SPEED_EXP` is declined for now.
  - **D-57:** weapons on built stat sheets are a stopgap until G09 or intake supplies real ones (recorded in #269).
  - **The board:** the "PR linked → In review" automation was turned on (#172).
- **Screenshots (Nov 14, mocks, `main` at cb41095):** [the parsed fight card](media/ms1-tonights-card.jpg) and [the verdict on the Battle page](media/ms1-verdict.jpg).

### Code complete, v1.0 (Wed Nov 25)

Dates are Mountain Time. MS-2 (Nov 17), MS-3 (Nov 20) and MS-4 (Nov 22) have no entries of their own, so this one covers everything since MS-1.

- **What works (Nov 25; `main` at 8acc9ec, after #640):**
  - **Code-complete status: met.** Running the app on `main` at 8acc9ec in mock mode (`PROVIDER_MODE=mock`), the home page shows the sample battles and the five showcase battles. The showcase "a grizzly bear vs 4 gray wolves in a forest" plays its intro, then the fight with a health bar per side, damage numbers and the 1×/2×/5×/10× speeds, then the "4 gray wolves win!" banner and the verdict (55%, range 52–58%, over 1,000 simulated fights). Its Results page shows the win chances, the reasons in plain words, the fair fight, the next challenger and the cited tale of the tape (screenshots below). No errors in the browser console or the server log during the run. Of the six cut-order items in LANES.md, only music was cut (below).
  - **The whole show:** intake reads a plain-English matchup (counts, sizes, a place, one clarifying question, and a card note when it reinterprets a fighter, #526). The safety gate blocks real people, named characters and deities, groups of people and harmful asks before any research (A04, #185, #312; rulings D-59, D-60, D-65, D-69). Research builds a cited stat sheet: the 15 hand-verified seed sheets, the 12 mythical creature types and on-demand legends (#322), and unlisted animals and objects researched from their Wikipedia article at battle time (#534, #551, #569), with a labeled all-estimate sheet instead of a failed battle (#401, #441). The seeded simulation runs 1,000 fights (swarm mode, venom, terrain including the sky, machines, objects and abilities), then the fair fight and the next challenger. The announcer's script passes the number guard (now also for numbers written as words, #633), is read in the synthetic announcer voice (D-67), and plays over generated sprites and battlefields on the broadcast page, followed by the Results page.
  - **Built Nov 14–17 (MS-2, the real brain):** the stat-sheet builder in battles with `/api/fighters`, and model extraction with verified quotes (G04, #266, #269). Mythical creatures in battles, from the file or their article (G09, #274, #293, #322, #373). The rest of the safety gate (A04, #156, #161, #164, #165, #185), run by the battle route before research (#312). Retrieval finished, with on-demand ingest and hit@5 of 93% (#346). The traceability checker (G06, #353) and the edge-case benchmark set (#375). Four showcase battles with the export and startup import (G08, #295, #350). The F07 benchmark runner (#72) and its first live research run (#406). Swarm mode chosen by work (D-50, #193) and the venom cliff (D-61, #333). The live AI evaluation, parts 1–3 (M09, #385, #392, #399).
  - **Built Nov 18–22 (MS-3 and MS-4, up to the feature freeze):** the live announcer voice (A07, #443) and the synthetic reference voice (#480, D-67). Showcase battle 1, so all five are on `main` (#434), and any missing one is added at startup (#490). The prebuilt knowledge base, so a fresh live setup skips the 30-minute ingest (D-66, #442). The evaluation finished and brought up to date (#421, #481). The first-time user guide (D09, #294, #495) and the usability plan (D10, #356). The bug bash on Nov 21 (#451). Health bars in the arena (#514) and sound that starts with the fight (#512). Military units, weapons and gods of mythology as fighters (D-69, #523), a sky battlefield (D-70, #543), and unlisted animals researched at battle time (#533, #534, #544).
  - **Fixed Nov 23–25 (after the freeze):** the top findings from the third usability session: each side's health bar drains with every hit (#578), 5× and 10× replay speeds (#583), the announcer speaks each line as the fight reaches it (#585) and starts from the "Start the fight" click (D-73, #594), a fight's replay lasts at most about 20 s at 1× with a 4–6 line play-by-play (D-72, #593; the Results page still shows the simulated fight time), and the show starts on the intro's voice while the rest is recorded (D-74, #640). Also: cloned-voice limits and retries (#563, #567, #574, #591), intake fixes, from a retry inside the deadline to clearer messages (#564, #566, #629, #637), the reasons for the win in plain words, clearer next steps and friendlier home page instructions (#607, #608, #611), setup and `npm run doctor` working from a ZIP copy (#600, #605, #632), the showcase battles re-exported with the model's script (#571), the usability findings finished with an issue for every finding (#588), and the README, user guide, decisions and ARCHITECTURE brought up to date (#599, #602, #626, #631).
  - **Evidence:** the live AI evaluation (`docs/evaluation.md`): the safety gate blocked 66 of the 68 requests it should block and wrongly blocked 2 of 52 allowed ones; retrieval found the right passage in the top 5 for 14 of 15 cases; 85% of 105 intake readings got every field right; of 51 hand-verified stats rebuilt from research alone, 35% landed within 10%, 33% fell back to labeled estimates, and no kept number failed its quote check. The pinned seed-sheet benchmark baseline (`docs/benchmark-results.md`, the Nov 16 run, with 5 cases skipped for lack of a sheet) passes 15 of 16 tuning and 8 of 9 held-out cases, and three cases are recorded as known limits rather than tuned away (D-58); the evaluation's Nov 19 re-run is lower (7 of 9 held-out on seed sheets). Bug testing: 101 `type: bug` and 36 `usability` issues closed, and three usability sessions (`docs/usability/findings.md`).
  - **Still open when this was written:** PRs #634, #636 and #638 (announcer and commentary fixes), the drafts #559 (image prompts for D-69 fighters, #529) and #284 (loadouts, post-MVP), bugs #612, #614, #619, #620, #622 and #623, and #522 (extraction accuracy).
- **What changed from the plan:**
  - **Music is cut** (cut-order item 1, decided on Nov 19 in #45 so the voice landed by MS-3). No live music adapter was built; the music stage and its mock (#276) stay, the stage falls back quietly, and the battle page stopped listing music as unavailable (#538, built in #539). The other five cut-order items all shipped: on-demand mythical creatures, generated sprites, the announcer voice, the full F07 benchmark and all 15 hand-verified sheets.
  - **D-58:** benchmark failures are reported as known limits; held-out cases never change after a run.
  - **D-59, D-60, D-65, D-69:** the safety rules: groups of real people are blocked; named mythological individuals count as named characters; generic deity kinds are allowed and named deities blocked; military units, weapons and gods of mythology are allowed fighters.
  - **D-61:** the venom cliff is accepted and documented, and big venomous one-by-one fights are refused.
  - **D-62:** Hermes Agent isn't used; Claude Code built the whole app, so there is no Hermes comparison (the G06 section below is kept as history).
  - **D-63, D-68:** the Simulate stage limit is 15 s (was 3 s) and the Audio stage limit 120 s (was 60 s).
  - **D-64, D-71:** the tournament was cut at the MS-2 scope check, and on Nov 22 the post-MVP work (loadouts, the tournament, venom in swarm mode) was closed as not planned. The bracket engine (#145) and the loadouts draft (#284) stay as starting points.
  - **D-66:** a prebuilt knowledge base ships with the repo.
  - **D-67:** the announcer is a synthetic voice designed from a generic description, not modeled on any real person.
  - **D-70:** a sky battlefield, where only fliers and ranged attacks reach a flier (a contract change).
  - **D-72, D-73, D-74:** a fight's replay lasts at most about 20 s; sound starts with the "Start the fight" click and "sound off" lasts one visit; the show starts on the intro's voice. They came from the usability findings and landed after the freeze as fixes.
  - **Schedule:** the third usability session ran on Mon Nov 23, a day after the planned deadline (three sessions, the minimum). The Windows fresh-clone check was run by Felipe on Nov 20. Mike's Mac re-run on Nov 24 (#595) found that setup failed from a ZIP copy, fixed in #600, #605 and #632.
- **Screenshots (Nov 25, mocks, `main` at 8acc9ec, the showcase battle "a grizzly bear vs 4 gray wolves in a forest"):** [the home page](media/v1-home.jpg), [the fight with health bars and replay speeds](media/v1-fight.jpg), [the verdict](media/v1-verdict.jpg), [the top of the Results page](media/v1-results.jpg) and [the cited tale of the tape](media/v1-tale-of-the-tape.jpg).

## G06 traceability checker and the Hermes comparison (D-02)

- **Not done as planned.** D-02 says G06 is the one task built with the course's Hermes Agent, with Mike pairing, as a comparison with Claude Code. On Nov 16 Gunnar chose to build it with Claude Code instead, so F07's traceability column wasn't held up (code complete is Nov 25). The PR for #40 asks Mike whether to keep D-02 by running the same G06 prompt through Hermes for the comparison alone, or to record the change as a decision.
- **Claude Code's side, for a later comparison:** one working session on Nov 16. It built `research/trace.py` (`check_battle`), `scripts/trace_report.py`, the benchmark's traceability column and 11 tests on fixtures. What helped: the checks reuse the narration number guard and the quote matcher, so the checker and the pipeline can't disagree. What didn't: the first test draft had three mistakes (a wrong stat name and two fixture assumptions), caught by running the tests before committing.
- **First run on stored battles (Nov 16):** the 4 showcase battles all pass with 0 issues. Their sheets are hand-verified seed sheets and a mythical sheet, so no extracted quotes were checked against stored articles; the tests cover that check.
