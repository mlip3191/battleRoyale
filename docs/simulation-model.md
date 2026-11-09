# Simulation Model: where our numbers come from

This is the answer to "where do your numbers come from?" Every constant lives in `backend/app/simulation/constants.py`. The stat sheets (sourced, cited) say *what a fighter is*; these constants say *how a fight turns those stats into hits and hit points*. **No language model sets any of these numbers.**

Honesty note: published studies say how strong a bite is or how fast an animal runs (that is what the stat sheets cite), but nothing in the literature gives a conversion from "newtons of bite force" to "hit points in a fight." Where a constant has no published source, it is labeled **assumption** below and was chosen so that results look sensible across the benchmark matchups. The benchmark (F07) is how we check that choice.

## How a fight works (engine version 3)

1. **Sampling.** Each of the (default) 1,000 runs draws every stat uniformly between its `low` and `high` for each side, using a generator seeded from the matchup, both stat-sheet hashes, and `ENGINE_VERSION`. Uncertain inputs therefore spread the results.
2. **Approach.** The sides start `START_DISTANCE_M` apart and close at the sum of their speeds, minus the longer reach.
3. **Combat.** Time moves in 0.1 s ticks (the loop jumps straight to the next tick where someone acts). Every fighter attacks at `attacks_per_s`, starting at a random point in its first interval so neither side gets a built-in first strike. Each attack picks a random living enemy, hits with a probability from speed and size, and deals damage reduced by armor.
4. **End.** A side with no fighters left loses. A fight still going at `MAX_FIGHT_S` (600 s) is a **draw**. If neither side can damage the other, or nobody can close the distance, it is also a draw (the dedicated `no_contest` handling comes with F04/F08).
5. **Summary.** Win and draw shares, 95% Wilson intervals, mean survivors and duration. The representative fight is re-run with the event log on: the run closest to the median duration among the most common outcome, capped at 300 events.

## Constants

| Constant | Value | Meaning | Source / status |
|---|---|---|---|
| `ENGINE_VERSION` | 3 | Part of the seed; bump whenever results would change. | Bookkeeping |
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
| `MIN_MASS_KG`, `MIN_SIZE_M` | 1e-6 kg, 1e-3 m | Smallest sampled mass and size. | Numerical safeguards |
| `CLOSING_EVENTS` | 2 | Log slots kept free for the closing events (a stalemate and the end). | Bookkeeping |
| `WILSON_Z` | 1.96 | z for a 95% interval. | Standard statistics (Wilson 1927) |
| `MAX_ENGAGERS` | 8 | Most melee attackers that can surround one target. | Geometry: about 6 neighbors fit around a circle of equal size, 8 allows for smaller attackers stacking. **Assumption** (cap from ARCHITECTURE §9) |
| `SWARM_THRESHOLD` | 200 | A side with more individuals than this runs in groups. | Design choice (ARCHITECTURE §9); chosen for speed |
| `SWARM_STEP_S` | 0.5 s | Shortest swarm step. | **Assumption** |
| `SWARM_STEP_GROWTH` | 0.1 | Swarm steps are at least this share of elapsed time. | **Assumption**: keeps 600 s swarm fights fast; early moments stay fine-grained |
| `MORALE_FLOOR`, `MORALE_SPAN` | 0.2, 0.8 | A side retreats once it has lost `0.2 + 0.8 x aggression_0_1` of its total hit points (timid 20%, fully aggressive never). | **Assumption**; no source measures this. Aggression is itself an assumable stat on the sheet. |
| `GROUP_TACTICS_BONUS` | 0.5 | With two or more attackers on one target, hit chance rises by up to this share at `group_tactics_0_1` = 1. | **Assumption** (cooperative hunting raises success in packs, e.g. Packer & Ruttan 1988, but no table gives a number) |
| `STRENGTH_SCALE_EXP` | 2/3 | Strength and damage scale as k^(2/3) when resized by k. | Muscle force follows cross-section area, so mass^(2/3): the square-cube law (Galileo 1638; Hill 1950, "The Dimensions of Animals and their Muscular Dynamics") |
| `LENGTH_SCALE_EXP` | 1/3 | Size and reach scale as k^(1/3). | Geometric similarity: length = mass^(1/3) |
| `SPEED_SCALE_EXP` | 1/6 | Top speed scales as k^(1/6). | Maximum running speed grows about mass^0.17 across mammals (Garland 1983, *J. Zoology*); simplified to 1/6 and applied to all movement. Garland also finds speed falls for the very largest animals, which this does not model |

## Numbers and size (F03)

- **Engagement limits (Lanchester linear law).** Each target can be attacked by at most `max_engagers = clamp((size_target / size_attacker)^2, 1, 8)` melee attackers at once. Extra attackers wait in a queue and join when a slot opens (an engaged attacker dies, or its target does). A bear (2.4 m) facing wolves (1.6 m) allows 2 wolves at a time; wolves facing the bear allow 1 each. Fighters with `weapon_ranged` use the **square law**: everyone engages. Lanchester (1916) derived both laws; the linear law is for fights where combatants pair off, the square law for fights where all concentrate fire.
- **Size references.** For `size_reference` ("horse-sized duck"), the caller passes the reference entity's stat sheet to `run(..., reference_sheets=[...])`. Code computes `k = reference mass / own mass` from the sheets' central values. A resized fighter has mass ×k, hit points ∝ mass, strength and damage ×k^(2/3), size and reach ×k^(1/3), speed ×k^(1/6). Attack rate, armor, and behavior stats are unchanged (assumption). The result's first approach events carry the neutral phrase "scaled to horse size" for the UI and announcer. **Contract gap:** `SimulationResult` has no field for the scale factor; adding one is a `contract-change` for the PM, so for now `engine.scale_factors()` returns it and the phrase rides in `text_hint`.
- **Swarm mode.** If either side has more than 200 individuals, each side becomes one group of identical fighters. Each 0.5 s step (longer later in the fight), the engaged attackers make attempts (binomial draws), hits are drawn, and damage is applied to one defender at a time, wasting overkill, as in the one-by-one engine. Sides act in random order within a step so mirror swarms are fair. Events are group events with `group_size`. Grouped fighters share one set of sampled stats, as individuals do.

**Speed.** 1,000 runs of 100 v 1,000 take about 0.1 s, and 10,000 ants v 1 lion (a draw at 600 s, the slowest case) about 1 s. One-by-one fights cost roughly the number of attacks made, so big groups just under 200 per side are slow (about 17 s for 200 v 200 at 1,000 runs). Callers that run many fights (F05, F06) should lower the run count or the threshold for large groups.

## Terrain, habitat, and behavior (F04)

- **Terrain table.** `terrain.py` gives every Terrain x Habitat pair (28 rows, each commented) a speed, attack, and hit multiplier. Water-only fighters on dry land are stranded (speed x0.1, attack x0.3, hit x0.5); land fighters in deep water are crippled (speed x0.2, attack x0.4, hit x0.5); the shoreline lets both engage weakly (land x0.7/0.8/0.8, water x0.5/0.6/0.7). All values are **assumptions** chosen for clear, sensible handicaps; they are not measured.
- **`no_contest`.** If neither side can reach the other, `run()` returns immediately with outcome `no_contest`, zero probabilities, and an END event "no contest: neither can reach the other". The only unreachable pair is a flier against a strictly water-living fighter in open water (the swimmer is submerged and the flier is out of reach). On dry land a fish is stranded and reachable; in the shallows everyone is reachable.
- **Morale, retreat, and flee.** When a side's lost share of total hit points passes its morale threshold (see constants), it retreats (RETREAT event) and stops attacking. If it is faster than the other side (after terrain) it escapes (FLEE event): the fight ends, the pursuer wins, and the runner counts as a survivor (a loss for its side, but alive). If it is not faster, it is caught and finishes the fight defenseless. Machines will never retreat (F08).
- **Group tactics.** Two or more attackers on the same target (or, for ranged sides and swarms, a crowd of attackers) raise hit chance by `group_tactics_0_1 x 0.5`, capped by the normal hit-chance maximum.

## Why probabilities are shown as "range"

The 95% interval is a Wilson score interval on the share of runs won. Because every run draws different stats, the shares already blend in input uncertainty: when the stat ranges are narrow the fight's outcome is more predictable, so the win share moves toward 0 or 1 and the interval narrows (tested in `tests/property/test_simulation_engine.py`). The interval does *not* separately model uncertainty in the constants above.

## Not modeled yet

Deciding-factor analysis (F05), machines and abilities (F08), and fatigue from `endurance_s`. The placeholder `deciding_factor` is always `mass_kg` (except `habitat` for a `no_contest`).

## References

- Lanchester, F. W. (1916). *Aircraft in Warfare: The Dawn of the Fourth Arm.*
- Hill, A. V. (1950). The dimensions of animals and their muscular dynamics. *Science Progress* 38, 209-230.
- Garland, T. (1983). The relation between maximal running speed and body mass in terrestrial mammals. *Journal of Zoology* 199, 157-170.
- Kleiber, M. (1932). Body size and metabolism. *Hilgardia* 6, 315-353.
- West, G. B., Brown, J. H. & Enquist, B. J. (1997). A general model for the origin of allometric scaling laws in biology. *Science* 276, 122-126.
- Packer, C. & Ruttan, L. (1988). The evolution of cooperative hunting. *The American Naturalist* 132, 159-198.
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *JASA* 22, 209-212.
