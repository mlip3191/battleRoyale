# Lane 5 — Dillon: Front End & Battle Stage

**Total effort: 13 points.** Dillon owns what people see and hear: the onboarding experience for the team, the app shell, the intake screen, the broadcast-style battle page, the Phaser animation, and the fighter images. The front end works against contract fixtures, so this lane never waits on the backend.

| ID | Task | Size | Depends on | Blocks | Wave |
|---|---|---|---|---|---|
| D01 | Onboarding guide + setup check script | M | M08 | everyone's first run | 1 |
| D02 | App shell, broadcast theme, typed API client | M | M04, M05 | D03–D07 | 2 |
| D03 | Intake page + clarification UI | S | D02 (+ A03 for live) | — | 2 |
| D04 | Results page: stat sheet cards with sources | M | D02 | — | 3 |
| D05 | Phaser battle scene that replays the event log | M | D02, M05 | D07 | 3 |
| D06 | Fighter sprites + battlefield images (step 6 backend) | M | M06, M05 | D05 (real art) | 4 |
| D07 | Broadcast page: intro, captions, audio, controls | M | D05, A05 | demo | 4 |

---

## D01 · Onboarding guide + setup check script · M (2)

**Goal:** Any teammate goes from nothing to a running app and a first PR on day one, on Windows or Mac.
**Read first:** TEAM_PROCESS Step 5; README "Teammate quick start".

**Prompt for Claude Code:**
```text
Task D01 from docs/plan/lane-5-dillon.md.
1. Write docs/onboarding.md for non-coders: accounts and access (GitHub with 2FA, invite accepted, Claude plan with Claude Code), installs with download links and how to check each version (Git — Git for Windows on Windows; GitHub CLI then gh auth login; Claude Code; VS Code; Node 24 via fnm or nvm-windows; uv; Docker Desktop optional; gitleaks via Homebrew or winget), first run (clone, setup check, copy .env.example to .env, fill every [required] line with the course endpoint values everyone has, run node scripts/check-env.mjs until it passes, npm run setup, npm run dev), the practice loop (pick issue, branch, change, PR, review someone else), and a cheat sheet of Claude Code requests (start work on issue #n, /new-issue, "what can I review?", pull latest main, undo your last change and explain, explain this in plain English).
2. Create scripts/setup-check.mjs (Node, so it runs the same on Windows and Mac) and a root npm script "doctor" that runs it; it reuses scripts/check-env.mjs for the .env part. It checks: git, gh logged in, claude installed, node version matches .nvmrc, uv installed, gitleaks installed (prints the install command for the user's OS if not), git user.name/email set, core.hooksPath is .githooks (sets it if not, and says so), .env passes scripts/check-env.mjs (never shows values), and that git ls-files --cached --ignored --exclude-standard prints nothing. Output is a checklist with a plain-English fix for each failure.
3. Add "If a teammate is new, point them to docs/onboarding.md." to CLAUDE.md.
Run npm run doctor on your machine and paste the output (no secrets) in the PR. Mike runs it on his Mac during review (the rest of the team is on Windows).
```

**Acceptance criteria**
- [ ] `npm run doctor` passes on Windows (Dillon) and Mac (Mike)
- [ ] The script never prints `.env` contents
- [ ] `docs/onboarding.md` gets a new person to a first PR

---

## D02 · App shell, broadcast theme, typed API client · M (2)

**Goal:** The frame every screen lives in, styled like a cheesy late-night sports broadcast.
**Read first:** ARCHITECTURE §10; PRODUCT_SPEC "Look and feel"; DECISIONS D-11 (styling library).

**Prompt for Claude Code:**
```text
Task D02 from docs/plan/lane-5-dillon.md. In frontend/:
1. Routing with react-router: / (Home), /battle/:id (Battle), /battle/:id/results (Results), and a 404 page.
2. Theme: CSS variables for a late-night sports broadcast look (dark navy, neon accents, scoreboard fonts from a free Google Font, lower-third banners). Use plain CSS modules unless DECISIONS.md says otherwise. Must meet WCAG AA contrast; respect prefers-reduced-motion.
3. src/api/client.ts: typed fetch functions for every route in ARCHITECTURE section 6 using the generated types from npm run gen:api; base URL from Vite env (VITE_API_BASE, default same origin via the dev proxy).
4. A fixtures mode: when VITE_USE_FIXTURES=true, the client returns data from src/fixtures/ (synced from backend contract fixtures) with realistic delays, including a battle that moves through stages over ~10 seconds.
5. A useBattle(id) hook that subscribes to /api/battles/{id}/events (Server-Sent Events) and falls back to polling every second.
6. Layout components: Header with logo text "BATTLE ROYALE", LowerThird, LoadingTicker ("Researching the grizzly..."), ErrorPanel with a friendly message.
7. Vitest tests for the client in fixtures mode and for useBattle's polling fallback.
```

**Acceptance criteria**
- [ ] All routes render; fixtures mode runs the full flow without a backend
- [ ] Types come only from generated files (no hand-written API types)
- [ ] Contrast AA; reduced-motion respected

---

## D03 · Intake page + clarification UI · S (1)

**Goal:** Type a matchup, answer one question if needed, start the battle.
**Prompt for Claude Code:**
```text
Task D03 from docs/plan/lane-5-dillon.md. Build the Home page:
1. A large text box ("Who would win?"), a Fight! button, and 6 example chips (e.g. "100 duck-sized horses vs 1 horse-sized duck").
2. Calls POST /api/intake. On "clarify", show the question with the options as buttons plus a free-text answer, then POST the answer. On "blocked", show the friendly message and keep the text so the user can edit it. On "ok", show a confirmation card (fighters, counts, terrain, assumptions) with a terrain dropdown the user can change, then POST /api/battles and navigate to /battle/:id.
3. Keyboard: Enter submits; all controls reachable by Tab; labels for screen readers.
4. Tests in fixtures mode for ok, clarify, and blocked.
```

**Acceptance criteria**
- [ ] All three intake outcomes handled; terrain editable before the fight
- [ ] Keyboard and screen-reader friendly

---

## D04 · Results page: stat sheet cards with sources · M (2)

**Goal:** The defensible verdict: numbers, reasons, and a source behind every stat.
**Read first:** ARCHITECTURE §5 (`StatSheet`, `SimulationResult`, `FairFight`, `ChallengerSuggestion`).

**Prompt for Claude Code:**
```text
Task D04 from docs/plan/lane-5-dillon.md. Build the Results page and components:
1. VerdictBanner: winner (or draw/no contest), win % per side with the 95% interval shown as "62% (58–66%)", survivors, duration, and the deciding factor explainer.
2. StatSheetCard per fighter: each stat with value + unit, a SourceBadge (link to the source in a new tab, confidence dot, hover/focus shows the quote), and an "estimate" tag when is_estimate. A banner if more than 3 stats are estimates.
3. FairFightCard ("A fair fight needs 37 house cats" or the no-fair-fight message) and NextChallengerCard with a "Fight them!" button that starts a new battle with the winner vs the suggestion.
4. A Sources section listing every unique source with title, URL, and license.
5. Tests in fixtures mode: every displayed stat has either a SourceBadge link or an estimate tag (this is our traceability promise in the UI).
```

**Acceptance criteria**
- [ ] Every stat shows a source link or an estimate tag (tested)
- [ ] Fair fight + next challenger work; "Fight them!" starts a new battle

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
4. Large counts: render at most 50 sprites per side and show "x 1,000" badges.
5. Controls exposed to React: play, pause, speed 1x/2x, skip to end, and an onEvent(index) callback (used later to sync captions).
6. Reduced motion: when prefers-reduced-motion is on, show key frames only (start, every KO, end) with no shaking.
7. Tests: the timeline visits every event in order (test the timeline logic outside Phaser); component unmount destroys the game.
```

**Acceptance criteria**
- [ ] The fixture battle replays start to finish, matching the event log
- [ ] Placeholders work with no images; 1,000-fighter battles stay smooth
- [ ] Reduced-motion mode works

---

## D06 · Fighter sprites + battlefield images (step 6 backend) · M (2)

**Goal:** Generate crude, consistent fighter sprites and a battlefield, cached per fighter.
**Read first:** ARCHITECTURE §7 (ImageGen), §11 (no copyrighted characters); `docs/providers.md`.

**Prompt for Claude Code:**
```text
Task D06 from docs/plan/lane-5-dillon.md. This one is backend (Python) work.
1. Live ImageGen adapter backend/app/providers/live/image.py for the image endpoint (port 9006) with generate and edit, per docs/providers.md. If unknown, stop and ask Mike to run the smoke script.
2. backend/app/media/images.py:
   - make_sprite(stat_sheet) -> Asset: prompt built in code from a style template ("crude 16-bit side-view sprite of a <display_name>, plain background, facing right, game asset") — never names a franchise, artist, or character. Then use the edit mode to remove the background (transparent PNG). Cache per fighter_id + style version so each fighter is drawn once.
   - make_battlefield(terrain) -> Asset: one per terrain, cached.
   - make_images(record) -> list[Asset] for the orchestrator.
3. Fallback: on failure return an Asset with fallback=True and no URL; the front end draws placeholders.
4. A small "style lock": the same seed/params every time so sprites look like one set.
5. Pre-generate sprites for all seed fighters with a script (backend/scripts/pregen_sprites.py) so the demo is fast.
6. Tests with the mock provider for caching and fallback.
```

**Acceptance criteria**
- [ ] Sprites for the seed fighters generated live and cached (thumbnails in the PR)
- [ ] Transparent backgrounds; consistent style
- [ ] Fallback path works with no image endpoint

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
6. Tests in fixtures mode for the stage flow and the degraded modes.
```

**Acceptance criteria**
- [ ] Full broadcast plays in fixtures mode and against the live backend
- [ ] Captions sync with the animation; every degraded mode tested
