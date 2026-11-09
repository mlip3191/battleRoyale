# Simulation Model: where our numbers come from

This is the answer to "where do your numbers come from?" Every constant lives in `backend/app/simulation/constants.py`. The stat sheets (sourced, cited) say *what a fighter is*; these constants say *how a fight turns those stats into hits and hit points*. **No language model sets any of these numbers.**

Honesty note: published studies say how strong a bite is or how fast an animal runs (that is what the stat sheets cite), but nothing in the literature gives a conversion from "newtons of bite force" to "hit points in a fight." Where a constant has no published source, it is labeled **assumption** below and was chosen so that results look sensible across the benchmark matchups. The benchmark (F07) is how we check that choice.

## How a fight works (engine version 1)

1. **Sampling.** Each of the (default) 1,000 runs draws every stat uniformly between its `low` and `high` for each side, using a generator seeded from the matchup, both stat-sheet hashes, and `ENGINE_VERSION`. Uncertain inputs therefore spread the results.
2. **Approach.** The sides start `START_DISTANCE_M` apart and close at the sum of their speeds, minus the longer reach.
3. **Combat.** Time moves in 0.1 s ticks (the loop jumps straight to the next tick where someone acts). Every fighter attacks at `attacks_per_s`, starting at a random point in its first interval so neither side gets a built-in first strike. Each attack picks a random living enemy, hits with a probability from speed and size, and deals damage reduced by armor.
4. **End.** A side with no fighters left loses. A fight still going at `MAX_FIGHT_S` (600 s) is a **draw**. If neither side can damage the other, or nobody can close the distance, it is also a draw (the dedicated `no_contest` handling comes with F04/F08).
5. **Summary.** Win and draw shares, 95% Wilson intervals, mean survivors and duration. The representative fight is re-run with the event log on: the run closest to the median duration among the most common outcome, capped at 300 events.

## Constants

| Constant | Value | Meaning | Source / status |
|---|---|---|---|
| `ENGINE_VERSION` | 1 | Part of the seed; bump whenever results would change. | Bookkeeping |
| `TICK_S` | 0.1 s | Simulation time step. | Assumption (fine enough for attack rates up to ~10/s) |
| `MAX_FIGHT_S` | 600 s | A fight this long is a draw. | Design choice (DECISIONS / ARCHITECTURE §9) |
| `MAX_LOG_EVENTS` | 300 | Cap on the replay log. | `SimulationResult` contract |
| `START_DISTANCE_M` | 10 m | Starting gap. | Assumption |
| `HP_PER_KG` | 10 | Hit points per kg of mass. | Hit points proportional to body mass follows from volume scaling (mass ∝ L³), as in allometric scaling (Kleiber 1932; West, Brown & Enquist 1997). The factor 10 is an **assumption** that only sets the unit. |
| `DAMAGE_PER_NEWTON` | 0.05 hp/N | Damage per hit = attack force × this. | **Assumption**; calibrates force against `HP_PER_KG`. Force values themselves come from cited stat sheets (e.g. published bite-force studies). |
| `ARMOR_EFFECT` | 0.8 | Share of damage a full armor value (1.0) blocks. | **Assumption**. Armor stat itself is an assumable behavioral/defensive stat on the sheet. |
| `HIT_BASE` | 0.75 | Hit chance between equals. | **Assumption** |
| `HIT_SPEED_EXP` | 0.3 | Exponent on attacker/defender speed ratio. | **Assumption** (faster attackers land more, with diminishing returns) |
| `HIT_SIZE_EXP` | 0.2 | Exponent on defender/attacker size ratio. | **Assumption** (bigger targets are easier to hit, weakly) |
| `HIT_MIN`, `HIT_MAX` | 0.05, 0.95 | Clamp on hit chance. | **Assumption**: no fight is a certainty |
| `MIN_SPEED_MPS` | 0.1 m/s | Floor on speed in ratios. | Numerical safeguard |
| `WILSON_Z` | 1.96 | z for a 95% interval. | Standard statistics (Wilson 1927) |

## Why probabilities are shown as "range"

The 95% interval is a Wilson score interval on the share of runs won. Because every run draws different stats, the shares already blend in input uncertainty: when the stat ranges are narrow the fight's outcome is more predictable, so the win share moves toward 0 or 1 and the interval narrows (tested in `tests/property/test_simulation_engine.py`). The interval does *not* separately model uncertainty in the constants above.

## Not modeled yet

Group-fight limits and size scaling (Lanchester, square-cube: F03), terrain and morale (F04), deciding-factor analysis (F05), machines and abilities (F08), and fatigue from `endurance_s`. The placeholder `deciding_factor` in v1 is always `mass_kg`.

## References

- Lanchester, F. W. (1916). *Aircraft in Warfare: The Dawn of the Fourth Arm.* (used from F03)
- Kleiber, M. (1932). Body size and metabolism. *Hilgardia* 6, 315-353.
- West, G. B., Brown, J. H. & Enquist, B. J. (1997). A general model for the origin of allometric scaling laws in biology. *Science* 276, 122-126.
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *JASA* 22, 209-212.
