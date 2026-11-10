# Swarm mode vs the one-by-one engine

Fights where either side has more than 200 individuals run in **swarm mode** (each side is one group; see [simulation-model.md](simulation-model.md)). Swarm mode exists for speed, but it is a different model from the one-by-one engine, so this page measures how far apart they are. The one-by-one engine is the reference.

Reproduce with `uv run --directory backend python scripts/validate_swarm.py` (about 20 s; `--scenario cats` for one group, `--runs` to change the 600 runs per engine). Each fight is simulated twice with the same sheets, once forced through each engine. The table has a **Noise (95%)** column (`1.96 x sqrt(2 p (1-p) / runs)`, with p the one-by-one win share) and marks gaps that are within it. The numbers below were re-run after the stack was rebased on `main` (engine version 5) and reproduce exactly; if the engine version changes, re-run the script and refresh the tables, since a new version reshuffles every run's random stream.

## Results (600 runs each, after the #76 fixes and #84, engine version 7)

Noise: a single win share at 600 runs near 50/50 has a 95% noise of about ±0.04, so the **gap between two such results is only reliable to about ±0.06** (the table printed by the script has a noise column and marks gaps within it). A teammate's check at 4,000 runs (`uv run --directory backend python scripts/validate_swarm.py --scenario mirror --runs 4000`) found the mirror gaps from 5 v 5 to 50 v 50 were 0.006 or less on the earlier engine.

In brackets, what it was before the fixes.

| Kind of fight | Win share: swarm minus one-by-one | Duration | Survivors |
|---|---|---|---|
| **One big target** (3-50 wolves vs a bear) | -0.01 to +0.01 | 0.98-0.99x | about 1.0x |
| **Even and uneven matches of the same animal** (5 v 5 up to 125 v 100 wolves) | -0.02 to +0.01 | 0.90-1.05x (was about 2x) | 0.97-1.01x (was about 0.65x) |
| **Ranged** (10-50 archers vs half as many wolves) | 0.00 to +0.02 | 0.92-1.00x | about 1.0x (was 0.4-0.5x for the loser) |
| **Many weak vs few strong** (10-100 cats vs a fifth as many wolves) | -0.04 to -0.055 at 3,000 runs (was +0.06 to +0.22; noise 0.025) | 0.90-0.94x | 0.88-0.94x |

Full tables are printed by the script. Speed is the point of swarm mode, but timings depend on the machine. On the author's laptop a 100 v 100 fight takes about 3 s per 1,000 runs one by one and 0.2 s in swarm; 200 v 200 takes about 17 s one by one. On a teammate's machine 100 v 100 took about 9.8 s one by one and 0.67 s in swarm (about 3x slower, with the same ratio between the modes). Treat the stage budget in #91 with the slower numbers.

## What was wrong, and how swarm mode works now

- **Hits are whole hits.** Swarm mode used to carry leftover damage smoothly from one defender to the next, which made a lone strong attacker kill too fast (up to -0.09 against one big target). Hits now land one at a time on a front.
- **Each hit picks its own defender, as in the one-by-one engine.** The attackers' hits are spread at random over as many defenders as can be engaged at once (the cap of 8 per target still applies), so some defenders die early and others late. This removed the crowd-versus-few-strong overrating.
- **Fronts that die with nobody to replace them no longer count.** The group's average hit points used to include dead fronts, so survivors looked healthier and the end of every fight dragged on (about 2.5x too long when hunting down a side that had broken). `tests/property/test_simulation_swarm_parity.py` guards this.
- **Where the models still differ:** the largest gaps left are +0.04 (3 wolves v a bear) and -0.04 (25 v 5 cats), both inside the noise of a 600-run gap, and the average-front approximation forgets which fronts are weakened between steps. The crowd-vs-few-strong rows are the exception: at 3,000 runs the swarm underrates the crowd by 0.04 to 0.055, which is real (noise 0.025). That residual appeared once #84 made the one-by-one engine's attack schedule exact (the cats got stronger there, while swarm mode already used exact rates); without #84 the same rows were -0.007 to -0.032. A likely cause is that in the one-by-one engine each attacker stays on its target, so some defenders collect many attackers and fall early, while swarm mode re-spreads the hits every step. Closing it means tracking which defenders are already hurt between steps.

## Larger fights (above the swarm threshold)

Every scenario above is 125 per side or fewer, but swarm mode only runs above 200 per side. These larger fights can be reproduced with `uv run --directory backend python scripts/validate_swarm.py --scenario large --runs 300` (opt-in: the one-by-one reference takes minutes). A teammate first ran them at 150-300 runs each (one-by-one vs swarm, win share of the first side):

| Fight | Runs | One-by-one | Swarm | Gap |
|---|---|---|---|---|
| 250 v 250 wolves | 300 | 0.467 | 0.473 | +0.007 |
| 312 v 250 wolves | 200 | 0.600 | 0.600 | 0.000 |
| 300 wolves v 1 bear | 300 | 1.000 | 1.000 | 0.000 |
| 300 cats v 60 wolves | 300 | 0.427 | 0.623 | **+0.197** |
| 600 cats v 120 wolves | 150 | 0.533 | 0.693 | **+0.160** |
| 400 archers v 200 wolves | 150 | 0.973 | 0.980 | +0.007 |

The conclusions held at these sizes before the fixes: matched, one-big-target and ranged fights agreed, and a crowd of weak fighters against a few strong ones was overrated by 0.16 to 0.20.

**After the #76 fixes** (`--scenario large --runs 200`, engine version 7; win share of the first side, one-by-one then swarm):

| Fight | One-by-one | Swarm | Gap | Noise (95%) |
|---|---|---|---|---|
| 250 v 250 wolves | 0.465 | 0.465 | +0.000 | 0.098 |
| 300 cats v 60 wolves | 0.465 | 0.425 | -0.040 | 0.098 |
| 600 cats v 120 wolves | 0.510 | 0.440 | -0.070 | 0.098 |
| 400 archers v 200 wolves | 0.935 | 0.950 | +0.015 | 0.048 |

Every gap is within the noise of a 200-run comparison, down from +0.16 to +0.20 for the two crowd fights. Both crowd rows lean slightly negative (the crowd is now a little underrated); more runs would show whether that is real, and it is the first thing to check if anyone re-tunes swarm mode.

## What this means for the app

- **Win probabilities from swarm mode are trustworthy** to about ±0.04 for every kind of fight in the validation script.
- **Duration and survivor counts from swarm mode are now close** to the one-by-one engine's (durations about 10% short, survivors within a few percent), so a fight at 201 per side reads like the same fight at 199.
- **Fair-fight search:** probes above 200 per side use swarm mode, and their answers are now as reliable as those below.
- **F07 benchmark:** "count" cases above 200 per side are fine to include; still flag any swarm-mode matchup in the report.
- **Lowering the threshold** is now an option, since swarm mode agrees closely at every size, and it saves time: with the deciding-factor analysis a 100 v 100 fight takes about 9 s one by one (see #91).
