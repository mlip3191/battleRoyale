# Lane 5 — Dillon Smart: Front End, Battle Stage & User Experience

**Total effort: 14 points.** Dillon owns what people see and how they experience it: team onboarding, the app shell, the intake screen and its clarifying question (front and back), the broadcast-style battle page, the Phaser animation, the user guide, and usability testing with outside users. The front end works against contract fixtures, so this lane never waits on the backend.

| ID | Task | Size | Depends on | Blocks | Wave |
|---|---|---|---|---|---|
| D01 | Onboarding guide + setup check script | M | M08 | everyone's first run | 1 |
| D02 | App shell, broadcast theme, typed API client | M | M04, M05 | D03–D07 | 2 |
| D03 | Intake page + clarification UI | S | D02 (+ D08 for live) | — | 2 |
| D04 | Results page: stat sheet cards with sources | M | D02 | — | 3 |
| D05 | Phaser battle scene that replays the event log | M | D02, M05 | D07 | 3 |
| D07 | Broadcast page: intro, captions, audio, controls | M | D05, A05 | demo | 4 |
| D08 | Clarifying question flow + intake API (backend) | S | A02 | D03 (live) | 3 |
| D09 | User guide for a first-time user | S | D07 | instructor | 4 |
| D10 | Usability sessions with 3–5 outside users | S | MS-3 | bug fixes | 4–5 |

**Definition of Done for every task (CLAUDE.md §7), on top of its own acceptance criteria:** at least one test for every code change (docs-only tasks such as G01, G07, F01, D09, and D10 are checked by the reviewer instead); `npm run check` passes; the app still starts with `npm start`; the PR uses the template with `Closes #<n>`, explains the change in plain English, and ticks each criterion with its evidence (test name, command output, link, or screenshot); docs updated if behavior changed; a teammate approved and all required checks passed before merging. Criteria marked "live" are run by the task owner on their own machine (never in CI), and the pasted results never include endpoint hosts or keys.

---

## D01 · Onboarding guide + setup check script · M (2)

**Goal:** Any teammate goes from nothing to a running app and a first PR on day one, on Windows or Mac.
**Read first:** TEAM_PROCESS Step 5; README "Teammate quick start".

**Prompt for Claude Code:**
```text
Task D01 from docs/plan/lane-5-dillon.md.
1. Write docs/onboarding.md for non-coders: accounts and access (GitHub with 2FA, invite accepted, Claude plan with Claude Code), installs with download links and how to check each version (Git — Git for Windows on Windows; GitHub CLI then gh auth login; Claude Code; VS Code; Node 24 via fnm or nvm-windows; uv; gitleaks via Homebrew or winget), first run (clone, setup check, copy .env.example to .env, fill every [required] line with the course endpoint values everyone has, run node scripts/check-env.mjs until it passes, npm run setup, npm run dev), the practice loop (pick issue, branch, change, PR, review someone else), and a cheat sheet of Claude Code requests (start work on issue #n, /new-issue, "what can I review?", pull latest main, undo your last change and explain, explain this in plain English).
2. Create scripts/setup-check.mjs (Node, so it runs the same on Windows and Mac) and a root npm script "doctor" that runs it; it reuses scripts/check-env.mjs for the .env part. It checks: git, gh logged in, claude installed, node version matches .nvmrc, uv installed, gitleaks installed (prints the install command for the user's OS if not), git user.name/email set, core.hooksPath is .githooks (sets it if not, and says so), .env passes scripts/check-env.mjs (never shows values), and that git ls-files --cached --ignored --exclude-standard prints nothing. Output is a checklist with a plain-English fix for each failure. Add a test that runs the .env check on a decoy file in a temporary folder containing a marker value and asserts the marker never appears in the output (never use the real .env).
3. Add "If a teammate is new, point them to docs/onboarding.md." to CLAUDE.md.
Run npm run doctor on your machine and paste the output (no secrets) in the PR. Mike runs it on his Mac during review (the rest of the team is on Windows).
```

**Acceptance criteria**
- [ ] `docs/onboarding.md` covers accounts, every install with a version check, first run (including `.env` and `node scripts/check-env.mjs`), the practice loop, and the cheat sheet
- [ ] `npm run doctor` checks every item in step 2 and prints a plain-English fix for each failure; it passes on Dillon's Windows machine and Mike's Mac (output pasted, no secrets)
- [ ] A test runs the doctor's `.env` check on a decoy file in a temporary folder containing a marker value; the marker never appears in the output
- [ ] The CLAUDE.md onboarding line is added

---

## D02 · App shell, broadcast theme, typed API client · M (2)

**Goal:** The frame every screen lives in, styled like a cheesy late-night sports broadcast.
**Read first:** ARCHITECTURE §10; PRODUCT_SPEC "Look and feel"; DECISIONS D-11 (styling library).

**Prompt for Claude Code:**
```text
Task D02 from docs/plan/lane-5-dillon.md. In frontend/:
1. Routing with react-router: / (Home), /battle/:id (Battle), /battle/:id/results (Results), and a 404 page.
2. Theme: CSS variables for a late-night sports broadcast look (dark navy, neon accents, scoreboard fonts from a free Google Font, lower-third banners). Use plain CSS modules unless DECISIONS.md says otherwise. Must meet WCAG AA contrast (at least 4.5:1 for every text/background pair; paste the checked pairs in the PR); respect prefers-reduced-motion.
3. src/api/client.ts: typed fetch functions for every route in ARCHITECTURE section 6 using the generated types from npm run gen:api; base URL from Vite env (VITE_API_BASE, default same origin via the dev proxy).
4. A fixtures mode: when VITE_USE_FIXTURES=true, the client returns data from src/fixtures/ (synced from backend contract fixtures) with realistic delays, including a battle that moves through stages over ~10 seconds.
5. A useBattle(id) hook that subscribes to /api/battles/{id}/events (Server-Sent Events) and falls back to polling every second.
6. Layout components: Header with logo text "BATTLE ROYALE", LowerThird, LoadingTicker ("Researching the grizzly..."), ErrorPanel with a friendly message.
7. Vitest tests for the client in fixtures mode and for useBattle's polling fallback.
```

**Acceptance criteria**
- [ ] Routes `/`, `/battle/:id`, `/battle/:id/results`, and the 404 page render (tests)
- [ ] With `VITE_USE_FIXTURES=true` and no backend, a battle moves through all stages in about 10 s (test)
- [ ] `useBattle` uses SSE and falls back to polling every 1 s when SSE fails (test)
- [ ] `src/api/client.ts` imports types only from the generated schema (lint rule or test)
- [ ] Every text/background color pair has a contrast ratio of at least 4.5:1 (checked with a contrast tool; results in the PR); animations stop under `prefers-reduced-motion`

---

## D03 · Intake page + clarification UI · S (1)

**Goal:** Type a matchup, answer one question if needed, start the battle.
**Prompt for Claude Code:**
```text
Task D03 from docs/plan/lane-5-dillon.md. Build the Home page:
1. A large text box ("Who would win?"), a Fight! button, 6 example chips (e.g. "100 duck-sized horses vs 1 horse-sized duck", "a toaster vs a goose", "a dragon vs a main battle tank"), and a "Showcase" row of the five saved battles from GET /api/battles?showcase=true (Gunnar's G08; use a fixture until it lands).
2. Calls POST /api/intake. On "clarify", show the question with the options as buttons plus a free-text answer, then POST the answer. On "blocked", show the friendly message and keep the text so the user can edit it. On "ok", show a confirmation card (fighters, counts, terrain, assumptions) with a terrain dropdown the user can change, then POST /api/battles and navigate to /battle/:id.
3. Keyboard: Enter submits; all controls reachable by Tab; labels for screen readers.
4. Tests in fixtures mode for ok, clarify, and blocked.
```

**Acceptance criteria**
- [ ] Fixtures-mode tests: "ok" shows the confirmation card and starts a battle; "clarify" shows the question with option buttons and free text; "blocked" shows the message and keeps the typed text
- [ ] Changing the terrain dropdown changes the matchup sent to `POST /api/battles` (test)
- [ ] The Showcase row lists five battles (from a fixture until G08 lands)
- [ ] Enter submits; every control is reachable with Tab; every input has a label (accessibility queries in the tests pass)

---

## D04 · Results page: stat sheet cards with sources · M (2)

**Goal:** The defensible verdict: numbers, reasons, and a source behind every stat.
**Read first:** ARCHITECTURE §5 (`StatSheet`, `SimulationResult`, `FairFight`, `ChallengerSuggestion`).

**Prompt for Claude Code:**
```text
Task D04 from docs/plan/lane-5-dillon.md. Build the Results page and components:
1. VerdictBanner: winner (or draw/no contest), win % per side with the 95% interval shown as "62% (58–66%)", survivors, duration, and the deciding factor explainer.
2. StatSheetCard per fighter: each stat with value + unit, a SourceBadge (link to the source in a new tab, confidence dot, hover/focus shows the quote), and a tag: "assumption" when method is assumption, otherwise "estimate" when is_estimate. A banner if more than 3 stats are estimates or assumptions.
3. LoreCard for mythical fighters: "Modeled on <body_analog>, scaled to <size_analog>", the abilities as icons with labels, and the quoted lore sentence with its link; plus a banner "Legendary fighter: every stat is an assumption".
4. FairFightCard ("A fair fight needs 37 house cats" or the no-fair-fight message) and NextChallengerCard with a "Fight them!" button that starts a new battle with the winner vs the suggestion.
5. A Sources section listing every unique source with title, URL, and license.
6. Tests in fixtures mode (add a mythical fixture): every displayed stat has either a SourceBadge link or an estimate tag (this is our traceability promise in the UI).
```

**Acceptance criteria**
- [ ] Test: every stat on the results fixture shows either a SourceBadge link or an "estimate" / "assumption" tag
- [ ] Win % is shown with its range (e.g. "62% (58–66%)"), along with the deciding-factor explainer
- [ ] A banner appears when more than 3 stats are estimates or assumptions (test)
- [ ] A mythical fighter shows the LoreCard with both analogs, its abilities, and the linked quote, plus the "Legendary fighter" banner (test)
- [ ] FairFightCard handles both a count and the no-fair-fight message; "Fight them!" posts a new battle with the winner vs the suggestion (test)
- [ ] The Sources section lists every unique source once, with title, URL, and license (test)

---

## D05 · Phaser battle scene that replays the event log · M (2)

**Goal:** A crude, fun animation that always matches the math.
**Read first:** ARCHITECTURE §10 (Phaser rules), §5 (`FightEvent`).

**Prompt for Claude Code:**
```text
Task D05 from docs/plan/lane-5-dillon.md. In frontend/src/game/:
1. PhaserStage React component that mounts and destroys a Phaser 3 game cleanly (no leaks on route change).
2. PreloadScene loads sprite and battlefield URLs from the battle's assets; if missing, generates placeholder sprites in code (colored shapes with the fighter's initial; side 0 blue, side 1 red).
3. BattleScene takes representative_log and plays it on a timeline: approach = move toward the target, attack/hit = lunge + shake + floating damage, miss = whiff, ko = fade out, retreat/flee = run off-screen, group events = show a crowd icon with a count. It never decides outcomes; it only replays events.
4. Large counts: render at most 50 sprites per side and show "x 1,000" badges. Measure a 1,000-v-1 fixture with the browser's performance tool; it should hold 30 fps or better on your laptop (note the result in the PR).
5. Controls exposed to React: play, pause, speed 1x/2x, skip to end, and an onEvent(index) callback (used later to sync captions).
6. Reduced motion: when prefers-reduced-motion is on, show key frames only (start, every KO, end) with no shaking.
7. Tests: the timeline visits every event in order (test the timeline logic outside Phaser); component unmount destroys the game.
```

**Acceptance criteria**
- [ ] Timeline test: for the fixture log, every event is visited in order, exactly once
- [ ] Missing images → placeholder shapes with the fighter's initial in side colors (test)
- [ ] At most 50 sprites per side, with "× N" badges for larger counts; a 1,000-v-1 fixture plays at 30 fps or better on Dillon's laptop (measured with the browser's performance tool; noted in the PR)
- [ ] Reduced-motion mode shows key frames only, with no shaking (test)
- [ ] Unmounting the component destroys the Phaser game (test)

---


## D07 · Broadcast page: intro, captions, audio, controls · M (2)

**Goal:** The full "late-night broadcast": intro, the fight with play-by-play, music, and the verdict reveal.
**Prompt for Claude Code:**
```text
Task D07 from docs/plan/lane-5-dillon.md. Build the Battle page (/battle/:id):
1. Stage-aware: while research/simulate run, show the LoadingTicker with live stage updates from useBattle. As soon as the result exists, allow "Skip to verdict".
2. Intro: title card with both fighters, the announcer intro script as captions, intro audio if present.
3. Fight: PhaserStage + play-by-play captions synced with onEvent(index) using ScriptLine.at_event; narration audio and music with an AudioBar (play/pause, mute, volume). Captions always on; audio optional.
4. Outro: verdict reveal, then a button to the Results page.
5. Degraded modes: no audio -> captions only; no music -> silent; no images -> placeholders; show a small "some effects unavailable" note when any stage is "fallback".
6. Tests in fixtures mode for the stage flow, caption sync, "Skip to verdict", and each degraded mode. Then run one full battle against the live backend and attach a screen recording or GIF to the PR.
```

**Acceptance criteria**
- [ ] Fixtures-mode test of the whole flow: loading ticker → intro with captions → fight with captions → verdict → results button
- [ ] Captions change on `onEvent(index)` according to `ScriptLine.at_event` (test)
- [ ] Each degraded mode is tested: no audio (captions only), no music, no images (placeholders), and the "some effects unavailable" note whenever a stage is `fallback`
- [ ] "Skip to verdict" appears as soon as the result exists and jumps straight to the verdict (test)
- [ ] One full run against the live backend is recorded (screen recording or GIF in the PR)

---

## D08 · Clarifying question flow + intake API (backend) · S (1)

**Goal:** When a fighter is vague, ask one question and continue.
**Read first:** ARCHITECTURE §6 (`/api/intake` routes).

**Prompt for Claude Code:**
```text
Task D08 from docs/plan/lane-5-dillon.md. This one is backend (Python) work; it pairs with your intake page (D03), so you own the clarifying question end to end.
1. Add POST /api/intake {text} and POST /api/intake/{pending_id}/answer {answer} in backend/app/api/intake.py, both returning IntakeResult.
2. Store pending clarifications in SQLite (table intake_pending: pending_id, original_text, question, options, created_at) via backend/app/db; expire after 30 minutes.
3. Answer handling: combine original text + answer, re-parse once. If it is still vague, pick the most common variant, add it to assumptions, and return status "ok". Never ask more than one question per matchup.
4. Tests for: ok on first try; one clarification then ok; still vague after the answer (assumption added); expired pending_id (404 with a plain message).
```

**Acceptance criteria**
- [ ] `POST /api/intake` and `POST /api/intake/{pending_id}/answer` appear in OpenAPI, and `npm run gen:api` produces their types
- [ ] Tests: ok on the first try; one clarification then ok; still vague after the answer → assumption added and "ok"; a second question is never asked
- [ ] Pending clarifications are stored in SQLite and expire after 30 minutes; an expired or unknown `pending_id` returns 404 with a plain-English message (test)

---

---

## D09 · User guide for a first-time user · S (1)

**Goal:** The overview requires documentation "for a naïve user." This is it.
**Read first:** README; PRODUCT_SPEC §2–5.

**Prompt for Claude Code:**
```text
Task D09 from docs/plan/lane-5-dillon.md. Write docs/user-guide.md for someone who has never seen the app or a terminal:
1. What the app does in three sentences, and what "science-backed" means here (sourced stats, estimates labeled, a simulation decides).
2. How to run it on Windows and Mac: install Node 24 and uv, copy .env.example to .env and fill it in (or leave PROVIDER_MODE=mock to try it without endpoints), npm run setup, npm start, open http://localhost:8000. Screenshots of each step.
3. How to use it: typing a matchup, answering the clarifying question, choosing terrain, watching the broadcast, reading the results page (win % and the range, deciding factor, fair fight, next challenger, source links, the "estimate" and "assumption" tags), and the five showcase battles.
4. What it won't do (real people, more than two sides, etc.) and why.
5. Troubleshooting: the five most likely problems and their fixes (from the bug bash and usability sessions).
Link it from README. Ask a teammate who hasn't run the app recently to follow it start to finish in their review.
```

**Acceptance criteria**
- [ ] `docs/user-guide.md` covers all five sections in the task, with a screenshot for each run step, and is linked from README
- [ ] A teammate who hasn't run the app recently followed it start to finish without help; anything they got stuck on is fixed in the same PR (noted in the PR)

---

## D10 · Usability sessions with 3–5 outside users · S (1)

**Goal:** Test the UI/UX with people outside the team — one of the overview's three stated purposes — and turn what they hit into fixes.
**When:** Nov 21–22, after MS-3 (the full show works).

**Prompt for Claude Code:**
```text
Task D10 from docs/plan/lane-5-dillon.md. Help me run usability sessions.
1. Write docs/usability/plan.md: 5 tasks for a tester (start a battle from the examples, type your own matchup, answer a clarifying question, find where a stat came from, start the next challenger battle), what to observe, and 5 short questions afterwards (what confused you, what made you laugh, would you trust the verdict, would you share it, what's missing). Each session about 15 minutes; no personal data recorded.
2. After I run 3–5 sessions (friends, family, classmates outside our group), help me write docs/usability/findings.md: a table of each problem, how many testers hit it, severity, and a suggested fix.
3. Create one issue per problem with /new-issue (type: bug or feature, label usability), and tell Mike which ones you think must be fixed before the freeze.
```

**Acceptance criteria**
- [ ] `docs/usability/plan.md` contains the 5 tasks and 5 questions
- [ ] 3–5 sessions are run by Sun Nov 22, and `docs/usability/findings.md` has a table of problem, testers affected, severity, and suggested fix, with no names or personal data
- [ ] One issue per finding, labeled `usability`; Dillon's top-3 must-fix list goes to Mike before the freeze

