# Swarm mode vs the one-by-one engine

Fights where either side has more than 200 individuals run in **swarm mode** (each side is one group; see [simulation-model.md](simulation-model.md)). Swarm mode exists for speed, but it is a different model from the one-by-one engine, so this page measures how far apart they are. The one-by-one engine is the reference.

Reproduce with `uv run --directory backend python scripts/validate_swarm.py` (about 10 s; `--scenario cats` for one group, `--runs` to change the 600 runs per engine). Each fight is simulated twice with the same sheets, once forced through each engine. The table has a **Noise (95%)** column (`1.96 x sqrt(2 p (1-p) / runs)`, with p the one-by-one win share) and marks gaps that are within it. The numbers below were re-run on this branch (merged with `main`) at engine version 8 and reproduce (the script is seeded); if the engine version changes, re-run the script and refresh the tables, since a new version reshuffles every run's random stream.

## Results (600 runs each, after the #76 fixes and #84, engine version 8)

Noise: a single win share at 600 runs near 50/50 has a 95% noise of about ±0.04, so the **gap between two such results is only reliable to about ±0.06** (the table printed by the script has a noise column and marks gaps within it). A teammate's check at 4,000 runs (`uv run --directory backend python scripts/validate_swarm.py --scenario mirror --runs 4000`) found the mirror gaps from 5 v 5 to 50 v 50 were 0.006 or less on the earlier engine.

In brackets, what it was before the fixes.

| Kind of fight | Win share: swarm minus one-by-one | Duration | Survivors |
|---|---|---|---|
| **One big target** (3-50 wolves vs a bear) | -0.012 to +0.007 | 0.98-0.99x | about 1.0x |
| **Even and uneven matches of the same animal** (5 v 5 up to 125 v 100 wolves) | -0.023 to +0.008 | 0.96-1.04x (was about 2x) | 0.96-1.00x (was about 0.65x) |
| **Ranged** (10-50 archers vs half as many wolves) | +0.003 to +0.015 | 0.92-0.96x | about 1.0x (was 0.4-0.5x for the loser) |
| **Many weak vs few strong** (10-100 cats vs a fifth as many wolves) | -0.023 to +0.012 at 600 runs; -0.021 to -0.003 at 3,000 runs (noise 0.025); -0.009 to -0.003 at 8,000 runs (noise 0.015). Was +0.06 to +0.22, then -0.04 to -0.06 before swarm mode remembered wounded defenders | 0.90-1.00x | 0.95-1.00x (crowd), 1.05-1.07x (wolves) |

Full tables are printed by the script. Speed is the point of swarm mode, but timings depend on the machine. After the replay-event speedup (#160), on the author's laptop a 100 v 100 fight of wolves takes about 1.7 s per 1,000 runs one by one, and 200 v 200 takes about 3.1 s (3.5 s with the deciding-factor analysis). Uneven fights are much slower one by one: 150 cats v 1 elephant took about 32 s with the analysis. **Swarm mode is slower than the old smooth model**: spreading each hit over the defenders costs time the old model did not. A first version of the new model took 2.3 s for 201 v 201 and 12.8 s for 1,000 v 1,000; handling fronts with identical hit points together (they are most of them after an equal split) brought it to about 0.5 to 0.9 s and 1.3 to 1.9 s per 1,000 runs. For comparison the old model took 0.14 s and 0.16 s. With the deciding-factor analysis a 201 v 201 fight takes about 0.7 s, 600 cats v 120 wolves about 1.9 s, and 10,000 ants v 1 lion about 1.7 s. On a teammate's machine, runs took about 3x longer than on the author's laptop, and CI runners are 2 to 3 times slower. The decision on when to use swarm mode is D-50 (by expected work, #183).

## What was wrong, and how swarm mode works now

- **Hits are whole hits.** Swarm mode used to carry leftover damage smoothly from one defender to the next, which made a lone strong attacker kill too fast (up to -0.09 against one big target). Hits now land one at a time on a front.
- **Each hit picks its own defender, as in the one-by-one engine.** The attackers' hits are spread at random over as many defenders as can be engaged at once (the cap of 8 per target still applies), so some defenders die early and others late. This removed the crowd-versus-few-strong overrating.
- **Fronts that die with nobody to replace them no longer count.** The group's average hit points used to include dead fronts, so survivors looked healthier and the end of every fight dragged on (about 2.5x too long when hunting down a side that had broken). `tests/property/test_simulation_swarm_parity.py` guards this.
- **Wounded defenders are remembered between steps.** The first version of this fix averaged the hit points of all fronts at the end of every step, so every front looked equally hurt and deaths were delayed (the crowd was underrated by 0.04 to 0.06). Swarm mode now keeps each wounded defender's hit points, keeps the fronts being fought from one step to the next (attackers stay on their target until it falls, as in the one-by-one engine), and splits each step's hits evenly across the fronts, with the remainder going to random fronts. Wounds never heal when fewer fronts are fought; those defenders wait in a reserve. A first attempt that re-drew a random front for every hit every step made matched groups last 12 to 33% too long, which is why the split is even.
- **Where the models still differ:** every kind of fight is now within about ±0.025 at 600 runs and the cats rows within ±0.009 at 8,000 runs, down from -0.04 to -0.06 for crowd v few strong, so the ±0.03 target in D-45 is met. Swarm mode is still a different model (it does not follow individual attackers), so it can drift in cases not in the script, and it is much slower than the old smooth model (see the timings above).

## Larger fights (above the swarm threshold)

Every scenario above is 125 per side or fewer, but swarm mode only runs above 200 per side. These larger fights can be reproduced with `uv run --directory backend python scripts/validate_swarm.py --scenario large --runs 300` (opt-in because it is the slowest group, about 8 s at 300 runs). A teammate first ran them at 150-300 runs each (one-by-one vs swarm, win share of the first side):

| Fight | Runs | One-by-one | Swarm | Gap |
|---|---|---|---|---|
| 250 v 250 wolves | 0.547 | 0.537 | -0.010 | 0.080 (within noise) |
| 312 v 250 wolves | 200 | 0.600 | 0.600 | 0.000 |
| 300 wolves v 1 bear | 300 | 1.000 | 1.000 | 0.000 |
| 300 cats v 60 wolves | 0.453 | 0.447 | -0.007 | 0.080 (within noise) |
| 600 cats v 120 wolves | 0.530 | 0.537 | +0.007 | 0.080 (within noise) |
| 400 archers v 200 wolves | 0.940 | 0.950 | +0.010 | 0.038 (within noise) |

The conclusions held at these sizes before the fixes: matched, one-big-target and ranged fights agreed, and a crowd of weak fighters against a few strong ones was overrated by 0.16 to 0.20.

**After the #76 fixes** (`--scenario large --runs 300`, engine version 8; win share of the first side, one-by-one then swarm, from the script's own output):

| Fight | One-by-one | Swarm | Gap | Noise (95%) |
|---|---|---|---|---|
| 250 v 250 wolves | 0.547 | 0.543 | -0.003 | 0.080 (within noise) |
| 300 cats v 60 wolves | 0.453 | 0.453 | +0.000 | 0.080 (within noise) |
| 600 cats v 120 wolves | 0.530 | 0.530 | +0.000 | 0.080 (within noise) |
| 400 archers v 200 wolves | 0.940 | 0.953 | +0.013 | 0.038 (within noise) |

Every gap is within the noise of a 300-run comparison, down from +0.16 to +0.20 for the two crowd fights. (These larger fights last 0.86 to 0.88x as long in swarm mode.) Timings are machine-dependent: 10,000 ants v 1 lion measured 0.6 s on one run and about 1.0 s on another.

## What this means for the app

- **Win probabilities from swarm mode are trustworthy** to about ±0.02 for every kind of fight in the validation script, including a crowd of weak fighters against a few strong ones.
- **Duration and survivor counts from swarm mode are now close** to the one-by-one engine's (durations 0.86 to 1.04x, survivors within a few percent), so a fight at 201 per side reads like the same fight at 199.
- **Fair-fight search:** probes above 200 per side use swarm mode, and their answers are now as reliable as those below.
- **F07 benchmark:** "count" cases above 200 per side are fine to include; still flag any swarm-mode matchup in the report.
- **Swarm mode is cheaper than a long one-by-one fight, not free.** A 201 v 201 fight costs about 0.5 to 0.9 s per 1,000 runs instead of 0.14 s, but 150 cats v 1 elephant costs about 32 s one by one, so D-50 (#183) chooses swarm mode by expected work, not head count. Every fight that newly switches must agree with the one-by-one engine within ±0.03.

## Fights that switch to swarm mode because of their work (D-50, #183)

`--scenario work --runs 600`, engine version 8: fights under 200 per side whose estimated work is above `SWARM_WORK_BUDGET`, swarm minus one-by-one (win share of the first side):

| Fight | Win-share gap | Duration | One-by-one time | Swarm time |
|---|---|---|---|---|
| 150 v 150 wolves | +0.002 | 1.05x | 1.5 s | 0.23 s |
| 200 v 200 wolves | +0.007 | 1.03x | 1.8 s | 0.23 s |
| 50 cats v 1 elephant | -0.010 | 0.96x | 2.6 s | 0.37 s |
| 100 cats v 1 elephant | +0.000 | 1.00x | 5.3 s | 0.65 s |
| 150 cats v 1 elephant | +0.015 | 1.00x | 6.0 s | 0.71 s |
| 100 archers v 50 wolves | +0.007 | 0.93x | 0.4 s | 0.09 s |
| 150 archers v 75 wolves | +0.018 | 0.96x | 0.7 s | 0.09 s |

(Times are for 600 runs without the analysis, on the author's laptop.) With the deciding-factor analysis, 150 cats v 1 elephant takes about 2.8 s in swarm mode, against about 32 s one by one.

**A time-step cap was needed for these.** Swarm steps used to grow to 10% of the elapsed time, so a 500 s fight took steps of 50 s, and 150 cats v 1 elephant overrated the crowd by +0.13 (100 v 1: +0.08). `SWARM_STEP_MAX_S` caps the step at 3 s: the gaps above are with the cap (+0.015 and +0.000), and fights shorter than about 30 s are unaffected. Steps of 2 s, 4 s and 5 s gave +0.010, +0.015 and +0.030 for 150 v 1 and 3.6, 2.3 and 1.9 s with the analysis; 3 s was the best balance.
