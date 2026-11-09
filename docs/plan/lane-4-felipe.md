# Lane 4 — Felipe: Simulation & Analytics

**Total effort: 15 points.** Felipe owns the "serious brain": the Monte Carlo engine that decides every outcome, the statistics shown to users, the fair-fight search, and the benchmark runner. The engine is pure Python with no network, so this lane can start as soon as the contracts land.

| ID | Task | Size | Depends on | Blocks | Wave |
|---|---|---|---|---|---|
| F01 | How-to-review guide + review practice | S | M08 | — | 1 |
| F02 | Engine core: seeded runs, combat loop, event log | M | M05 | F03–F06, D05 | 2 |
| F03 | Numbers and size: Lanchester laws, square-cube, swarm mode | M | F02 | F05, F06 | 2–3 |
| F04 | Terrain, habitat, and behavior | M | F02 | F05 | 3 |
| F05 | Summary stats + deciding factor | M | F03, F04 | A06, D04 | 3 |
| F06 | Fair-fight search + next-challenger testing | M | F05 | A05 | 4 |
| F07 | Benchmark runner + report | M | F05, G07, G06 | — | 4 |
| F08 | Machines, inert objects, and mythical abilities | M | F04, F05 | G09 integration, demo | 3–4 |

**Definition of Done for every task (CLAUDE.md §7), on top of its own acceptance criteria:** at least one test for every code change (docs-only tasks such as G01, G07, F01, D09, and D10 are checked by the reviewer instead); `npm run check` passes; the app still starts with `npm start`; the PR uses the template with `Closes #<n>`, explains the change in plain English, and ticks each criterion with its evidence (test name, command output, link, or screenshot); docs updated if behavior changed; a teammate approved and all required checks passed before merging. Criteria marked "live" are run by the task owner on their own machine (never in CI), and the pasted results never include endpoint hosts or keys.

---

## F01 · How-to-review guide + review practice · S (1)

**Goal:** Every teammate knows how to review a PR with the review-prs skill, and Felipe reviews the first real PR.
**Read first:** TEAM_PROCESS Steps 2, 3, 9; `.claude/skills/review-prs/SKILL.md`.

**Prompt for Claude Code:**
```text
Task F01 from docs/plan/lane-4-felipe.md. Write docs/reviewing.md for non-coders:
1. How to ask Claude "what can I review?" and what the list of open PRs means (needs your review, yours, drafts, blocked, ready to merge).
2. How an agent review works: it reads the issue and the change, runs tests on your machine, and drafts comments with suggested fixes — and that nothing is posted until you say "send".
3. How to read the report sections (what this code does, acceptance criteria, must fix, nits, proposed additional fixes, merge recommendation).
4. How to check the change yourself in the running app (npm run dev, what to click).
5. When to approve, when to request changes, and why you can never approve your own PR.
6. How the QA bot on GitHub differs from your review: it's automatic and advisory (it never blocks); your approval is what lets a PR merge. How to ask it to look again: add the re-review label (anyone can).
   Also: authors run /qa on their own branch before opening a PR; it uses the same rulebook (.claude/qa/checklist.md) and model as the bot and /review, so fixing its must-fix items first means fewer review rounds.
7. A one-screen checklist at the top.
Then use the review-prs skill to review the open dry-run PR from Mike's task M08, follow the skill to send the comments, and approve only if the report says Ready to merge. Link that review in this PR.
```

**Acceptance criteria**
- [ ] `docs/reviewing.md` covers all 7 points in the task, with a one-screen checklist at the top
- [ ] Felipe reviewed the dry-run PR with the skill: comments were posted only after he said send, and approval was asked as a separate question (review link in the PR)
- [ ] A teammate confirms in review that they could follow the checklist

---

## F02 · Engine core: seeded runs, combat loop, event log · M (2)

**Goal:** A deterministic fight simulator that already produces valid `SimulationResult` objects for 1 v 1 fights.
**Read first:** ARCHITECTURE §5 (`FightEvent`, `SimulationResult`), §8 (seed), §9.

**Prompt for Claude Code:**
```text
Task F02 from docs/plan/lane-4-felipe.md. Build backend/app/simulation/ with no I/O and no providers.
1. rng.py: make_seed(matchup, sheet_hash_0, sheet_hash_1) using a stable hash (hashlib) plus ENGINE_VERSION; all randomness comes from numpy.random.Generator or random.Random created from that seed (numpy is already installed by M04).
2. fighters.py: build combatant instances from a StatSheet: hp proportional to mass_kg, damage per hit from attack_force_n, hit chance from top_speed_mps and size_m ratio, armor_0_1 reduces damage, attacks_per_s sets the tick rate. On every run, sample each stat from its low–high range (seeded) so input uncertainty shows up in the results. Put every constant in simulation/constants.py, and write docs/simulation-model.md explaining each constant with a source (e.g. Lanchester's laws, Kleiber/allometric scaling, published bite-force or running-speed studies) or, where none exists, the reasoning and a note that it's an assumption. This document is what we show when someone asks "where do your numbers come from?"
3. engine.py: run_once(sides, terrain, rng, record_events) runs a time-stepped fight (0.1 s ticks, max 600 s) and returns the winner (0, 1, draw), survivors, duration, and optionally the event log using FightEvent with short neutral text_hint values.
4. run(matchup, stat_sheets, runs=settings.sim_runs) -> SimulationResult: runs N times, computes win/draw probabilities with 95% Wilson intervals, mean survivors, mean duration, picks the representative run (closest to the median duration among the most common outcome), re-runs it with events on, and caps the log at 300 events. deciding_factor can be a placeholder until F05.
5. Property tests (hypothesis) in backend/tests/property/: same inputs give identical results; probabilities sum to 1; mirror match is within 0.45–0.55 at 1,000 runs. Also test: narrower stat ranges give a narrower win-probability interval; a fight still going at 600 s is a draw; the log never exceeds 300 events. A timing test: 1,000 runs of 1 v 1 under 1 second.
```

**Acceptance criteria**
- [ ] `simulation.run` returns a valid `SimulationResult` for the contract fixture
- [ ] Property tests: same inputs give an identical result; probabilities sum to 1; a mirror match lands between 0.45 and 0.55 at 1,000 runs
- [ ] Each run samples stats within their `low`–`high` range (test: narrower ranges give a narrower win-probability interval)
- [ ] A fight still going at 600 simulated seconds ends as a draw (test); the event log never exceeds 300 events (test)
- [ ] 1,000 runs of a 1 v 1 finish in under 1 s on the ubuntu CI runner (timing test)
- [ ] Every constant lives in `simulation/constants.py` with a comment, and `docs/simulation-model.md` gives each one a source or labels it an assumption

---

## F03 · Numbers and size: Lanchester laws, square-cube, swarm mode · M (2)

**Goal:** Make group fights and size differences realistic.
**Read first:** ARCHITECTURE §9 (Numbers).

**Prompt for Claude Code:**
```text
Task F03 from docs/plan/lane-4-felipe.md. Extend backend/app/simulation/.
1. Engagement limits (Lanchester linear law for melee): each target can be attacked by at most max_engagers = clamp((size_target / size_attacker)^2, 1, 8) attackers at once; idle attackers queue. Fighters with weapon_ranged use the square law (everyone can engage).
2. Square-cube scaling for FighterRequest.size_reference ("horse-sized duck" = entity duck, size_reference horse): the orchestrator gives you both stat sheets; scale factor k = reference mass_kg / entity mass_kg, computed here in code. Scaled mass = mass × k; hp scales with mass; strength and damage with k^(2/3); size with k^(1/3); speed per a documented allometric rule (cite it in docs/simulation-model.md). Record the scaling in the result so the UI and announcer can say "scaled to horse size". This powers showcase battle #1 (100 duck-sized horses vs 1 horse-sized duck), so test it explicitly.
3. Swarm mode: when a side has more than 200 individuals, simulate in groups (bins of identical fighters with a count) so 10,000 ants run in under 3 seconds; events become group events with group_size.
4. Tests: adding fighters to a side never lowers its win probability by more than 0.02 (noise); max_engagers caps attackers on a much larger target; a scaling unit test with known masses; 100 v 1,000 and 10,000 ants vs 1 lion each run under 3 seconds; "100 duck-sized horses vs 1 horse-sized duck" produces a sensible, explainable result (write the explanation in the PR).
```

**Acceptance criteria**
- [ ] Tests: an attacker much smaller than its target is capped at `max_engagers`; a ranged side uses the square law
- [ ] Property test: adding fighters to a side never lowers its win probability by more than 0.02 (noise)
- [ ] Size-reference scaling has a unit test with known numbers (mass scaled to the reference's mass; strength by k^(2/3)); "100 duck-sized horses vs 1 horse-sized duck" runs, and the PR explains the result in plain English
- [ ] 100 v 1,000 and 10,000 ants vs 1 lion each finish in under 3 s on the ubuntu CI runner (timing tests); swarm events carry `group_size`

---

## F04 · Terrain, habitat, and behavior · M (2)

**Goal:** Sharks don't win on dry land; outmatched animals run away.
**Read first:** ARCHITECTURE §9 (Terrain/habitat, Behavior), §14.

**Prompt for Claude Code:**
```text
Task F04 from docs/plan/lane-4-felipe.md.
1. terrain.py: a table of modifiers per Terrain x Habitat (speed, attack, hit chance), with comments. Water-only fighters on land and land fighters in deep water get heavy penalties; shoreline lets both engage weakly.
2. no_contest: if neither side can reach the other (e.g. eagle vs shark in open water, air vs water), end immediately with outcome no_contest and a clear text_hint.
3. Behavior: each side retreats when its losses pass a morale threshold derived from aggression_0_1 (more aggressive = fights longer); a fleeing fighter that is faster than its pursuers escapes (counts as a loss for its side but a survivor). Add RETREAT and FLEE events.
4. Group tactics: group_tactics_0_1 boosts coordinated attacks for pack animals.
5. Tests: shark vs lion on open_field vs in water flips the favorite; eagle vs shark in water is no_contest; a timid side retreats earlier (median retreat time) than an aggressive one; RETREAT and FLEE events appear in representative logs; higher group_tactics_0_1 raises a pack's win probability.
```

**Acceptance criteria**
- [ ] `terrain.py` covers every Terrain × Habitat pair, with a comment per row
- [ ] Tests: shark vs lion flips the favorite between `open_field` and `water`; eagle vs shark in water → `no_contest`; a low-aggression side retreats earlier (median retreat time) than a high-aggression one
- [ ] RETREAT and FLEE events each appear in the representative log of at least one test matchup
- [ ] A test shows `group_tactics_0_1` raises a pack's win probability against the same opponent

---

## F05 · Summary stats + deciding factor · M (2)

**Goal:** Plain-language "why it happened," computed by code.
**Prompt for Claude Code:**
```text
Task F05 from docs/plan/lane-4-felipe.md.
1. deciding_factor: one-at-a-time sensitivity — for each StatName plus "numbers" and "terrain", equalize that factor between the sides, re-run 200 times, and measure the change in the favorite's win probability. The biggest change wins. Cache within a run.
2. deciding_factor_explainer: a code template (no LLM), e.g. "Size did it: the grizzly outweighs each wolf about 8 to 1, and the pack couldn't surround it in the trees." Use values from the stat sheets; round sensibly. If the deciding factor is a behavioral stat (aggression, group tactics, armor), say it rests on an assumption.
3. A summary() helper that returns the numbers the UI and the announcer need: win % per side, survivors, duration in seconds, favorite, and the deciding factor text.
4. Tests: a size-dominated matchup reports mass_kg or size_m; a swarm matchup reports numbers; a behavioral deciding factor mentions the assumption; the explainer contains no number that isn't in the inputs; a timing test for the 5-second budget.
Keep total time for simulate + deciding factor under 5 seconds for 1 v 1.
```

**Acceptance criteria**
- [ ] Every `SimulationResult` has a `deciding_factor` and an explainer string
- [ ] Tests: a size-dominated matchup reports `mass_kg` or `size_m`; a swarm matchup reports `numbers`; when a behavioral stat decides it, the explainer says it rests on an assumption
- [ ] The explainer contains no number that isn't in the inputs (test)
- [ ] Simulate + deciding factor finishes in under 5 s for a 1 v 1 (timing test)

---

## F06 · Fair-fight search + next-challenger testing · M (2)

**Goal:** "A fair fight needs 37 house cats," and a good next opponent.
**Read first:** ARCHITECTURE §9 (Fair fight), PRODUCT_SPEC steps 7–8.

**Prompt for Claude Code:**
```text
Task F06 from docs/plan/lane-4-felipe.md.
1. fair_fight(matchup, stat_sheets) -> FairFight: vary the count of the losing side (or the side the user didn't fix) using doubling then integer binary search, 200 runs per probe, at most 20 probes, cap 10,000; stop when |p - 0.5| <= 0.05. If even 10,000 can't reach 0.45, return count None and a message like "No fair fight within 10,000 house cats."
2. test_challengers(winner_sheet, candidates: list[StatSheet]) -> list[ChallengerSuggestion]: quick 200-run sims of the winner against each candidate; return them sorted by closeness to 50/50. (The LLM that proposes candidate names is called by the orchestrator; this function only tests them.)
3. If the main result is a draw or no_contest, fair_fight returns None with an explanation.
4. Tests: wolf vs house cats finds a count; ant vs elephant reports no fair fight; results are deterministic.
```

**Acceptance criteria**
- [ ] Wolf vs house cats finds a count with |p − 0.5| ≤ 0.05 in at most 20 probes; ant vs elephant returns `count=None` with the "no fair fight within 10,000" message (tests)
- [ ] A draw or `no_contest` main result gives `fair_fight` = None with an explanation (test)
- [ ] `test_challengers` returns suggestions sorted by |p − 0.5|, identical across two runs (test)

---

## F07 · Benchmark runner + report · M (2)

**Goal:** One command tells us how good the app's verdicts are.
**Read first:** `docs/benchmark.md` (G07).

**Prompt for Claude Code:**
```text
Task F07 from docs/plan/lane-4-felipe.md. Build backend/scripts/run_benchmark.py.
1. Load data/benchmark/matchups.yaml and the sealed data/benchmark/heldout.yaml (G07). For each matchup, run the simulation and fair-fight search and compare to the expected answer using the pass rules in docs/benchmark.md. Two modes via a flag: --sheets seed (hand-verified seed sheets) and --sheets research (research pipeline only, ignoring seed files). Report the tuning set and the held-out set separately; never use held-out results to change constants.
2. Also run Gunnar's traceability check (research/trace.py) on each result.
3. Output docs/benchmark-results.md: pass rate for each mode (seed vs research) and each set (tuning vs held-out), overall pass rate, pass rate by group (obvious/documented/count), a table per matchup (expected, our favorite, win %, pass/fail), traceability %, total runtime, and the git commit hash. Never overwrite silently: include the date in the heading and keep the previous run below it (latest first, keep the last 5).
4. Flags: --mock (CI-safe, uses fixtures) and --live.
5. A CI test that runs --mock on 3 matchups so the runner can't silently break.
Run it live once and paste the headline numbers in the PR.
```

**Acceptance criteria**
- [ ] `run_benchmark.py --live --sheets seed` and `--sheets research` both write to `docs/benchmark-results.md`, each reporting the tuning and held-out sets separately, plus traceability %, runtime, and commit hash
- [ ] Earlier runs are kept below the newest one (last 5)
- [ ] `--mock` runs 3 matchups in CI
- [ ] The baseline is committed and its headline numbers pasted in the PR (target: at least 80% on held-out "obvious"; report the real result whatever it is)

---

## F08 · Machines, inert objects, and mythical abilities in the engine · M (2)

**Goal:** Toasters don't charge, bulldozers don't panic, and dragons breathe fire — all decided by code, with every new constant documented.
**When:** Wave 3–4 (Nov 16–19), after F04.
**Read first:** ARCHITECTURE §9 "Bodies" and "Abilities", §14; DECISIONS D-38.

**Prompt for Claude Code:**
```text
Task F08 from docs/plan/lane-4-felipe.md. Extend backend/app/simulation/ for StatSheet.body and lore abilities.
1. Bodies:
   - machine: no morale (never RETREAT or FLEE); when endurance_s (operating time) runs out it is out of action (counts as a loss for that fighter, with a clear text_hint); no fatigue before that.
   - inert: never approaches; attacks only a target in reach and only if it has an attack; spines deal damage back to whoever hits it.
   - ramming and crushing: damage per hit from mass and speed with a documented momentum formula (cite it in docs/simulation-model.md); attack rate from a constant labeled an assumption.
   - If neither side can damage the other, end immediately as no_contest with a text_hint the announcer can joke about; if one side can't finish the other in 600 s, it's a draw.
2. Abilities (lore): flight (can engage air and land targets; terrain penalties as for birds), breath_weapon (ranged attack using the square law; damage and reach from constants labeled assumptions), regeneration (heals a share of HP per second), extra_heads (attack rate times heads, default 3 if heads is None).
3. Deciding factor: add "abilities" to the sensitivity check (remove all abilities and re-run).
4. Every new constant goes in simulation/constants.py with a comment and in docs/simulation-model.md with a source or "assumption". Bump ENGINE_VERSION.
5. Tests: a toaster vs a goose ends in a draw or a goose win, never a toaster win; a rock vs a sword (both inert, no attack) is no_contest; a machine never produces RETREAT or FLEE events; a dragon with breath_weapon beats the same dragon without it more often; regeneration raises survival time; flight lets an air fighter engage a land fighter in open_field.
```

**Acceptance criteria**
- [ ] Tests: toaster vs goose never ends as a toaster win; rock vs sword (both inert, no attack) → `no_contest`; across 1,000 runs a machine never produces RETREAT or FLEE
- [ ] A machine whose operating time runs out is out of action with a text_hint saying so (test)
- [ ] Ability tests: breath_weapon raises win probability against the same opponent; regeneration raises mean survival time; extra_heads raises attack rate by the heads factor; flight lets an air fighter engage a land fighter
- [ ] `deciding_factor` can be `abilities` (test with a dragon whose breath_weapon decides it)
- [ ] Every new constant is in `constants.py` and `docs/simulation-model.md` with a source or "assumption"; `ENGINE_VERSION` bumped
- [ ] The existing property and timing tests still pass
