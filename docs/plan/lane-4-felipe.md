# Lane 4 — Felipe: Simulation & Analytics

**Total effort: 13 points.** Felipe owns the "serious brain": the Monte Carlo engine that decides every outcome, the statistics shown to users, the fair-fight search, and the benchmark runner. The engine is pure Python with no network, so this lane can start as soon as the contracts land.

| ID | Task | Size | Depends on | Blocks | Wave |
|---|---|---|---|---|---|
| F01 | How-to-review guide + review practice | S | M08 | — | 1 |
| F02 | Engine core: seeded runs, combat loop, event log | M | M05 | F03–F06, D05 | 2 |
| F03 | Numbers and size: Lanchester laws, square-cube, swarm mode | M | F02 | F05, F06 | 2–3 |
| F04 | Terrain, habitat, and behavior | M | F02 | F05 | 3 |
| F05 | Summary stats + deciding factor | M | F03, F04 | A06, D04 | 3 |
| F06 | Fair-fight search + next-challenger testing | M | F05 | A05 | 4 |
| F07 | Benchmark runner + report | M | F05, G07, G06 | — | 4 |

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
6. How the QA bot on GitHub differs from your review (it's automatic and required; your approval is still required).
7. A one-screen checklist at the top.
Then use the review-prs skill to review the open dry-run PR from Mike's task M08, follow the skill to send the comments, and approve only if the report says Ready to merge. Link that review in this PR.
```

**Acceptance criteria**
- [ ] `docs/reviewing.md` with a one-screen checklist at the top
- [ ] Felipe completed the dry-run review with the skill (link in PR)

---

## F02 · Engine core: seeded runs, combat loop, event log · M (2)

**Goal:** A deterministic fight simulator that already produces valid `SimulationResult` objects for 1 v 1 fights.
**Read first:** ARCHITECTURE §5 (`FightEvent`, `SimulationResult`), §8 (seed), §9.

**Prompt for Claude Code:**
```text
Task F02 from docs/plan/lane-4-felipe.md. Build backend/app/simulation/ with no I/O and no providers.
1. rng.py: make_seed(matchup, sheet_hash_0, sheet_hash_1) using a stable hash (hashlib) plus ENGINE_VERSION; all randomness comes from numpy.random.Generator or random.Random created from that seed (ask me before adding numpy).
2. fighters.py: build combatant instances from a StatSheet: hp proportional to mass_kg, damage per hit from attack_force_n, hit chance from top_speed_mps and size_m ratio, armor_0_1 reduces damage, attacks_per_s sets the tick rate. Put every constant in simulation/constants.py with a comment explaining it.
3. engine.py: run_once(sides, terrain, rng, record_events) runs a time-stepped fight (0.1 s ticks, max 600 s) and returns the winner (0, 1, draw), survivors, duration, and optionally the event log using FightEvent with short neutral text_hint values.
4. run(matchup, stat_sheets, runs=settings.sim_runs) -> SimulationResult: runs N times, computes win/draw probabilities with 95% Wilson intervals, mean survivors, mean duration, picks the representative run (closest to the median duration among the most common outcome), re-runs it with events on, and caps the log at 300 events. deciding_factor can be a placeholder until F05.
5. Property tests (hypothesis) in backend/tests/property/: same inputs give identical results; probabilities sum to 1; mirror match is within 0.45–0.55 at 1,000 runs. A timing test: 1,000 runs of 1 v 1 under 1 second.
```

**Acceptance criteria**
- [ ] `simulation.run` returns a valid `SimulationResult` on the contract fixture
- [ ] Deterministic; mirror ≈ 50/50; 1,000 runs < 1 s
- [ ] All constants named and explained in one file

---

## F03 · Numbers and size: Lanchester laws, square-cube, swarm mode · M (2)

**Goal:** Make group fights and size differences realistic.
**Read first:** ARCHITECTURE §9 (Numbers).

**Prompt for Claude Code:**
```text
Task F03 from docs/plan/lane-4-felipe.md. Extend backend/app/simulation/.
1. Engagement limits (Lanchester linear law for melee): each target can be attacked by at most max_engagers = clamp((size_target / size_attacker)^2, 1, 8) attackers at once; idle attackers queue. Fighters with weapon_ranged use the square law (everyone can engage).
2. Square-cube scaling: hp scales with mass; strength and damage scale with mass^(2/3); apply when the user gives a variant like "horse-sized duck" (scale factor from the size words in FighterRequest.variant — coordinate with Adam on the variant format).
3. Swarm mode: when a side has more than 200 individuals, simulate in groups (bins of identical fighters with a count) so 10,000 ants run in under 3 seconds; events become group events with group_size.
4. Tests: more fighters on a side never lowers its win probability (monotonic, within noise); 100 v 1,000 runs under 3 seconds; "100 duck-sized horses vs 1 horse-sized duck" produces a sensible, explainable result (write the explanation in the PR).
```

**Acceptance criteria**
- [ ] Engagement limits and ranged square law implemented and tested
- [ ] Monotonic-numbers property test passes
- [ ] 10,000-individual swarm runs within the time budget

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
5. Tests: shark vs lion on land vs in water flips the favorite; eagle vs shark in water is no_contest; a timid side retreats earlier than an aggressive one.
```

**Acceptance criteria**
- [ ] Terrain table documented in code; habitat flips covered by tests
- [ ] `no_contest`, retreat, and flee behaviors visible in event logs

---

## F05 · Summary stats + deciding factor · M (2)

**Goal:** Plain-language "why it happened," computed by code.
**Prompt for Claude Code:**
```text
Task F05 from docs/plan/lane-4-felipe.md.
1. deciding_factor: one-at-a-time sensitivity — for each StatName plus "numbers" and "terrain", equalize that factor between the sides, re-run 200 times, and measure the change in the favorite's win probability. The biggest change wins. Cache within a run.
2. deciding_factor_explainer: a code template (no LLM), e.g. "Size did it: the grizzly outweighs each wolf about 8 to 1, and the pack couldn't surround it in the trees." Use values from the stat sheets; round sensibly.
3. A summary() helper that returns the numbers the UI and the announcer need: win % per side, survivors, duration in seconds, favorite, and the deciding factor text.
4. Tests: a size-dominated matchup reports SIZE or MASS; a swarm matchup reports numbers; the explainer contains no number that isn't in the inputs.
Keep total time for simulate + deciding factor under 5 seconds for 1 v 1.
```

**Acceptance criteria**
- [ ] Deciding factor + explainer filled in `SimulationResult`
- [ ] Tests for size-driven and numbers-driven outcomes; time budget met

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
- [ ] Fair-fight count found within 20 probes or "no fair fight" message
- [ ] Challenger testing returns sorted suggestions; deterministic

---

## F07 · Benchmark runner + report · M (2)

**Goal:** One command tells us how good the app's verdicts are.
**Read first:** `docs/benchmark.md` (G07).

**Prompt for Claude Code:**
```text
Task F07 from docs/plan/lane-4-felipe.md. Build backend/scripts/run_benchmark.py.
1. Load data/benchmark/matchups.yaml; for each, build stat sheets (seed sheets first), run the simulation and fair-fight search, and compare to the expected answer using the pass rules in docs/benchmark.md.
2. Also run Gunnar's traceability check (research/trace.py) on each result.
3. Output docs/benchmark-results.md: overall pass rate, pass rate by group (obvious/documented/count), a table per matchup (expected, our favorite, win %, pass/fail), traceability %, total runtime, and the git commit hash. Never overwrite silently: include the date in the heading and keep the previous run below it (latest first, keep the last 5).
4. Flags: --mock (CI-safe, uses fixtures) and --live.
5. A CI test that runs --mock on 3 matchups so the runner can't silently break.
Run it live once and paste the headline numbers in the PR.
```

**Acceptance criteria**
- [ ] `run_benchmark.py --live` produces `docs/benchmark-results.md`
- [ ] Traceability included; mock mode runs in CI
- [ ] First baseline committed (target: ≥ 80% pass on "obvious")
