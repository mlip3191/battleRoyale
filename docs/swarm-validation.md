# Swarm mode vs the one-by-one engine

Fights where either side has more than 200 individuals run in **swarm mode** (each side is one group; see [simulation-model.md](simulation-model.md)). Swarm mode exists for speed, but it is a different model from the one-by-one engine, so this page measures how far apart they are. The one-by-one engine is the reference.

Reproduce with `uv run --directory backend python scripts/validate_swarm.py` (about 20 s; `--scenario cats` for one group, `--runs` to change the 600 runs per engine). Each fight is simulated twice with the same sheets, once forced through each engine.

## Results (600 runs each; win-share noise is about ±0.02)

| Kind of fight | Win share: swarm minus one-by-one | Duration | Survivors |
|---|---|---|---|
| **One big target** (3-50 wolves vs a bear) | within ±0.02 | within ~10% | identical |
| **Even and uneven matches of the same animal** (5 v 5 up to 125 v 100 wolves) | within ±0.02 | swarm fights last **about 2x longer** (14 s vs 6 s at 50 v 50) | swarm leaves **about 35% fewer** on both sides (22 vs 35 of 50) |
| **Ranged** (10-50 archers vs half as many wolves) | within +0.02 | within ~10% | the loser's survivors are 50-60% lower in swarm |
| **Many weak vs few strong** (10-100 cats vs a fifth as many wolves) | **+0.06 to +0.22** (swarm favors the crowd) | within ~15% | swarm has more crowd survivors and fewer wolves |

Full tables are printed by the script. Speed is the point of swarm mode: a 100 v 100 fight takes 2.8 s per 1,000 runs one by one and 0.19 s in swarm; 200 v 200 takes about 17 s one by one.

## Why they differ

- **The one-by-one engine pairs fighters up for the whole fight.** Damage is spread over many partly hurt fighters, so when one side hits its morale limit (it has lost 60% of its hit points, for aggression 0.5) almost nobody has died yet, and the winner keeps nearly everyone. The loser then runs or is chased down.
- **Swarm mode focuses every hit on one defender at a time.** Kills start immediately and both sides shrink together (like a continuous Lanchester decay), which makes fights longer and leaves fewer survivors on both sides.
- **For a crowd against a few strong fighters** the focusing matters most: swarm mode lets dozens of cats pile onto one wolf at a time (more than the 8 that physically fit around it), so wolves die early and stop killing cats. In the one-by-one engine the cats spread over all wolves, who die later and kill many cats first.
- **Where the models agree** is where focusing is physically forced anyway: one big target, or ranged fire.

## What this means for the app

- **Win probabilities from swarm mode are trustworthy** for one-big-target, same-animal, and ranged fights. Treat **crowd-vs-few-strong fights above 200 per side as unreliable by up to ±0.2.**
- **Duration and survivor counts from swarm mode are not comparable** with the one-by-one engine's. Matched-group swarm fights look about twice as long and bloodier than the same fight at 199 per side. The announcer and results page should not make a point of those numbers for swarms.
- **Fair-fight search:** probes above 200 per side use swarm mode, so "how many cats to match a wolf?" answers above 200 may come out too low (the crowd is overrated).
- **F07 benchmark:** keep the "count" cases at or below 200 per side, and flag any swarm-mode matchup in the report.
- **Lowering the threshold does not fix this** (the models differ at every size), and it costs time: with the deciding-factor analysis a 100 v 100 fight would take about 9 s.

## A prototype that did not make it in

I tried spreading hits over as many defenders as the engagement cap allows ("parallel fronts"). It brought survivors within about 1 of the one-by-one engine for even, uneven, and ranged fights and cut the duration gap from about +8 s to about -2 s at 50 v 50, but it overshot the other way for crowds (win share 0.11-0.17 *too low*) and cost 0.06-0.075 on pack-vs-bear (it drops the overkill waste). Neither model matches everywhere. Keeping it out avoids another engine-version bump for an unclear net gain.

**A proper fix would track the spread of damage across defenders** (so some die early, as in the real engine, which lets the crowd snowball) instead of treating all fronts as equal. That is a larger change to schedule after the benchmark shows whether it matters for the cases we grade.
