# Simulation Model: where our numbers come from

This is the answer to "where do your numbers come from?" Every constant lives in `backend/app/simulation/constants.py`, except the terrain table, which lives in `backend/app/simulation/terrain.py`. Each one is listed here with its source or an "assumption" label. The stat sheets (sourced, cited) say *what a fighter is*; these constants say *how a fight turns those stats into hits and hit points*. **No language model sets any of these numbers.**

Honesty note: published studies say how strong a bite is or how fast an animal runs (that is what the stat sheets cite), but nothing in the literature gives a conversion from "newtons of bite force" to "hit points in a fight." Where a constant has no published source, it is labeled **assumption** below and was chosen so that results look sensible across the benchmark matchups. The benchmark (F07) is how we check that choice.

## How a fight works (engine version 8)

1. **Sampling.** Each of the (default) 1,000 runs draws every stat uniformly between its `low` and `high` for each side, using a generator seeded from the matchup, both stat-sheet hashes, and `ENGINE_VERSION`. Uncertain inputs therefore spread the results.
2. **Approach.** The sides start `START_DISTANCE_M` apart and close at the sum of their speeds. Each side can attack once the gap is within its own reach, so a long-reach attacker (a breath weapon) opens fire first.
3. **Combat.** Time moves in 0.1 s ticks (the loop jumps straight to the next tick where someone acts). Every fighter attacks at `attacks_per_s`, starting at a random point in its first interval so neither side gets a built-in first strike. Each fighter's attack schedule is kept exactly (unrounded), and only the moment an event happens is rounded up to the next tick, so rounding never adds up: a fighter that attacks 1.5 times a second really does. An earlier version rounded every interval up to the next tick and compounded the error, so it made 1.43 attacks a second at a sheet rate of 1.5 (-5%), 2.5 at 3 (-17%), 3.3 at 4 (-17%), 5 at 7 (-29%), and never more than 5 at any higher rate (-44% at 9). Only rates that are a whole number of ticks apart (1, 2, 5, 10 a second) were exact. Each attack picks a random living enemy, hits with a probability from speed and size, and deals damage reduced by armor.
4. **End.** A side with no fighters left loses. A fight still going at `MAX_FIGHT_S` (600 s) is a **draw**. If neither side can damage the other, or nobody can close the distance, it is `no_contest` (see Terrain, habitat, and behavior and Machines, objects, and mythical abilities below).
5. **Summary.** Win and draw shares, 95% Wilson intervals, mean survivors and duration. The representative fight is re-run with the event log on: the run closest to the median duration among the most common outcome, capped at 300 events. Hits and misses fill only about the first half, so knock-outs have room; knock-outs that still do not fit are summed into one "more go down" event per side (its `group_size`) just before the ending, so the KO sizes add up to the number of fighters who fell.

## Constants

| Constant | Value | Meaning | Source / status |
|---|---|---|---|
| `ENGINE_VERSION` | 8 | Part of the seed; bump whenever results would change. | Bookkeeping |
| `TICK_S` | 0.1 s | Simulation time step. | Assumption (fine enough for attack rates up to ~10/s; event times only, the attack rate itself is exact) |
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
| `CLOSING_EVENTS` | 4 | Log slots kept free for the closing events: a stalemate, the end, and one "more go down" knock-out per side summarizing the falls that did not fit. | Bookkeeping |
| `LOG_FLOW_SHARE` | 0.5 | Share of the replay log that hits and misses may fill; the rest is kept for knock-outs, retreats and escapes, so a crowded fight still shows fighters going down. | Bookkeeping |
| `WILSON_Z` | 1.96 | z for a 95% interval. | Standard statistics (Wilson 1927) |
| `MAX_ENGAGERS` | 8 | Most melee attackers that can surround one target. | Geometry: about 6 neighbors fit around a circle of equal size, 8 allows for smaller attackers stacking. **Assumption** (cap from ARCHITECTURE §9) |
| `SWARM_THRESHOLD` | 200 | A side with more individuals than this runs in groups. | Design choice (ARCHITECTURE §9); chosen for speed |
| `SWARM_STEP_S` | 0.5 s | Shortest swarm step. | **Assumption** |
| `SWARM_STEP_GROWTH` | 0.1 | Swarm steps are at least this share of elapsed time. | **Assumption**: keeps 600 s swarm fights fast; early moments stay fine-grained |
| `MORALE_FLOOR`, `MORALE_SPAN` | 0.2, 0.8 | A side retreats once it has lost `0.2 + 0.8 x aggression_0_1` of its total hit points (timid 20%, fully aggressive never). | **Assumption**; no source measures this. Aggression is itself an assumable stat on the sheet. |
| `GROUP_TACTICS_BONUS` | 0.5 | With two or more attackers on one target, hit chance rises by up to this share at `group_tactics_0_1` = 1. | **Assumption** (cooperative hunting raises success in packs, e.g. Packer & Ruttan 1988, but no table gives a number) |
| `DECIDING_RUNS` | 200 | Runs per one-at-a-time sensitivity check. | Design choice (ARCHITECTURE §9) |
| `SURVIVOR_WEIGHT` | 0.5 | Weight of the favorite's average survivors next to its win share when ranking factors. | **Assumption**: keeps a lopsided fight (win share stuck at 100%) from hiding which factor matters most |
| `MIN_EFFECT` | 0.02 | If no factor moves the favorite's score by at least this much, the verdict is "too close to call". | **Assumption** (about the noise of a 200-run check) |
| `FAIR_RUNS` | 200 | Runs per fair-fight probe and per next-challenger duel. | Design choice (ARCHITECTURE §9) |
| `FAIR_TOLERANCE` | 0.05 | A fight is fair when the varied side's win share is within this of 50%. | Design choice (ARCHITECTURE §9) |
| `FAIR_MAX_PROBES`, `FAIR_MAX_COUNT` | 20, 10,000 | Most probes one search may use, and the largest count it tries. | Design choice (ARCHITECTURE §9; 10,000 is the app's count limit) |
| `RAM_DAMAGE_PER_MOMENTUM` | 0.005 hp per kg x m/s | Ramming and crushing damage = this x mass x speed. | Momentum (mass x speed) is the physical measure of how hard a moving mass hits; the hit-point conversion is an **assumption** (same role as `DAMAGE_PER_NEWTON`) |
| `RAM_ATTACKS_PER_S` | 0.4 | One ramming or crushing pass every 2.5 s. | **Assumption** |
| `CRUSH_MIN_SPEED_MPS` | 1.0 m/s | Crushing uses at least this speed in the momentum formula. | **Assumption**: crushing needs weight, not speed |
| `BREATH_DAMAGE_N` | 100,000 N-equivalent | A breath weapon's damage is at least this x `DAMAGE_PER_NEWTON`. | **Assumption**: legends give no numbers |
| `BREATH_RANGE_M` | 15 m | How far a breath weapon reaches. | **Assumption** |
| `REGEN_SHARE_PER_S` | 0.002 | Regeneration heals this share of max hit points per second (full heal in about 8 minutes). | **Assumption**; 1% per second made a regenerator effectively unkillable |
| `DEFAULT_HEADS` | 3 | Heads for `extra_heads` when the legend names no verified number. | ARCHITECTURE §9 (a design default) |
| `VENOM_BITE_SHARE` | 0.65 | Share of a lethal dose one landed venomous bite delivers to a target of equal mass (about two bites are lethal; smaller targets get more, scaled by (attacker mass / target mass)^0.5). | **Assumption** (D-44): legends and field notes give no usable dose numbers |
| `VENOM_ONSET_S` | 120 s | How long after the last blow a poisoned survivor dies ("minutes"). | **Assumption** (D-44) |
| `VENOM_RESISTANCE` | `honey-badger`: 0.85 | Per-fighter resistance from 0 (none) to 1 (immune), looked up by the base fighter id; each entry carries a one-line reason in `constants.py`. | **Assumption**: honey badgers are reported to survive cobra bites (G05's real sheets will refine this) |
| `STRENGTH_SCALE_EXP` | 2/3 | Strength and damage scale as k^(2/3) when resized by k. | Muscle force follows cross-section area, so mass^(2/3): the square-cube law (Galileo 1638; Hill 1950, "The Dimensions of Animals and their Muscular Dynamics") |
| `LENGTH_SCALE_EXP` | 1/3 | Size and reach scale as k^(1/3). | Geometric similarity: length = mass^(1/3) |
| `SPEED_SCALE_EXP` | 1/6 | Top speed scales as k^(1/6). | Maximum running speed grows about mass^0.17 across mammals (Garland 1983, *J. Zoology*); simplified to 1/6 and applied to all movement. Garland also finds speed falls for the very largest animals, which this does not model |

## Numbers and size (F03)

- **Engagement limits (Lanchester linear law).** Each target can be attacked by at most `max_engagers = clamp((size_target / size_attacker)^2, 1, 8)` melee attackers at once. Extra attackers wait in a queue and join when a slot opens (an engaged attacker dies, or its target does). A bear (2.4 m) facing wolves (1.6 m) allows 2 wolves at a time; wolves facing the bear allow 1 each. Fighters with `weapon_ranged` use the **square law**: everyone engages. Lanchester (1916) derived both laws; the linear law is for fights where combatants pair off, the square law for fights where all concentrate fire.
- **Size references.** For `size_reference` ("horse-sized duck"), the caller passes the reference entity's stat sheet to `run(..., reference_sheets=[...])`. Code computes `k = reference mass / own mass` from the sheets' central values. A resized fighter has mass ×k, hit points ∝ mass, strength and damage ×k^(2/3), size and reach ×k^(1/3), speed ×k^(1/6). Attack rate, armor, and behavior stats are unchanged (assumption). The result's first approach events carry the neutral phrase "scaled to horse size" for the UI and announcer. **Contract gap:** `SimulationResult` has no field for the scale factor; adding one is a `contract-change` for the PM, so for now `engine.scale_factors()` returns it and the phrase rides in `text_hint`.
- **Swarm mode.** If either side has more than 200 individuals, each side becomes one group of identical fighters. Each 0.5 s step (longer later in the fight), the engaged attackers make attempts (binomial draws), hits are drawn, and the hits are spread at random over as many defenders as can be engaged at once (the same cap of 8 attackers per target as the one-by-one engine), so some defenders fall early and others late. Hits are whole hits, and overkill is wasted, as in the one-by-one engine. Sides act in random order within a step so mirror swarms are fair. Events are group events with `group_size`. Grouped fighters share one set of sampled stats, as individuals do.

**Speed.** 1,000 runs of 100 v 1,000 take about 0.1 s, and 10,000 ants v 1 lion (a draw at 600 s, the slowest case) about 1 s. One-by-one fights cost roughly the number of attacks made, so big groups just under 200 per side are slow (about 17 s for 200 v 200 at 1,000 runs). Callers that run many fights (F05, F06) should lower the run count or the threshold for large groups.

## Terrain, habitat, and behavior (F04)

- **Terrain table.** `terrain.py` gives every Terrain x Habitat pair (28 rows, each commented) a speed, attack, and hit multiplier. Water-only fighters on dry land are stranded (speed x0.1, attack x0.3, hit x0.5); land fighters in deep water are crippled (speed x0.2, attack x0.4, hit x0.5); the shoreline lets both engage weakly (land x0.7/0.8/0.8, water x0.5/0.6/0.7). All values are **assumptions** chosen for clear, sensible handicaps; they are not measured.

The full table (each row is a multiplier on that fighter's speed, attack damage and hit chance; every value is an **assumption**, not a measurement):

| Terrain | Habitat | Speed | Attack | Hit | Reason (all values are assumptions) |
|---|---|---|---|---|---|
| arena | land | x1.0 | x1.0 | x1.0 | home ground for land animals |
| arena | water | x0.1 | x0.3 | x0.5 | stranded: gasping, can barely move or bite |
| arena | air | x0.8 | x1.0 | x0.95 | walls limit flight a little |
| arena | amphibious | x0.8 | x0.9 | x0.9 | amphibians are clumsy but fine on land |
| open field | land | x1.0 | x1.0 | x1.0 | baseline |
| open field | water | x0.1 | x0.3 | x0.5 | stranded on dry land |
| open field | air | x1.0 | x1.0 | x1.0 | open sky: fliers are unhindered |
| open field | amphibious | x0.8 | x0.9 | x0.9 | amphibious animal out of the water |
| forest | land | x0.9 | x1.0 | x1.0 | undergrowth costs a little speed |
| forest | water | x0.1 | x0.3 | x0.5 | stranded |
| forest | air | x0.6 | x1.0 | x0.85 | branches block flight paths and dives |
| forest | amphibious | x0.8 | x0.9 | x0.9 | damp ground helps a little, no more |
| water | land | x0.2 | x0.4 | x0.5 | deep water: paddling, no footing (heavy penalty) |
| water | water | x1.0 | x1.0 | x1.0 | home ground for fish and swimmers |
| water | air | x1.0 | x1.0 | x1.0 | fliers hover over the surface freely |
| water | amphibious | x0.9 | x1.0 | x1.0 | swimming amphibians are nearly at home |
| shoreline | land | x0.7 | x0.8 | x0.8 | wading slows footing |
| shoreline | water | x0.5 | x0.6 | x0.7 | shallows restrict a swimmer's movement |
| shoreline | air | x1.0 | x1.0 | x1.0 | open air above the shallows |
| shoreline | amphibious | x1.0 | x1.0 | x1.0 | amphibians' favorite ground |
| urban | land | x1.0 | x1.0 | x0.95 | hard ground, some cover |
| urban | water | x0.1 | x0.3 | x0.5 | stranded |
| urban | air | x0.8 | x1.0 | x0.9 | buildings clutter the air |
| urban | amphibious | x0.8 | x0.9 | x0.9 | out of its element |
| mountain | land | x0.85 | x1.0 | x0.95 | slopes cost speed |
| mountain | water | x0.1 | x0.3 | x0.5 | stranded |
| mountain | air | x0.9 | x1.0 | x0.95 | thin air and updrafts, small cost |
| mountain | amphibious | x0.7 | x0.9 | x0.85 | rough rock is hard on soft bodies |

- **`no_contest`.** If neither side can reach the other, `run()` returns immediately with outcome `no_contest`, zero probabilities, and an END event "no contest: neither can reach the other". The only unreachable pair is a flier against a strictly water-living fighter in open water (the swimmer is submerged and the flier is out of reach). On dry land a fish is stranded and reachable; in the shallows everyone is reachable.
- **Morale, retreat, and flee.** When a side's lost share of total hit points passes its morale threshold (see constants), it retreats (RETREAT event) and stops attacking. If it is faster than the other side (after terrain) it escapes (FLEE event): the fight ends, the pursuer wins, and the runner counts as a survivor (a loss for its side, but alive). If it is not faster, it is caught and finishes the fight defenseless. Machines will never retreat (F08).
- **Group tactics.** Two or more attackers on the same target (or, for ranged sides and swarms, a crowd of attackers) raise hit chance by `group_tactics_0_1 x 0.5`, capped by the normal hit-chance maximum.

## The deciding factor and its explanation (F05)

- **Method (one-at-a-time sensitivity).** For each of the ten stats, plus "numbers" and "terrain", we make that one factor equal for both sides, re-run the first 200 fights with the **same random seed**, and measure how much the favorite's score moves. The score is its win share plus half its average share of fighters left standing (so a fight where the favorite wins 100% either way still shows which factor mattered most). The largest mover is the deciding factor. Using the same seed means a factor that does nothing changes nothing, instead of adding noise.
- **How a factor is equalized.** A stat becomes the average of the two sides' values and ranges. "Numbers" sets both counts to the smaller one. "Terrain" removes the terrain multipliers for both. Factors that are already equal are skipped. Results are cached within a run.
- **Explanation.** A code template, never a language model. It quotes values straight from the stat sheets and the matchup counts, rounded to three significant figures; it never computes new numbers (a test checks that every number in an explainer is an input). If the deciding factor is aggression, teamwork, or armor, it adds "This rests on an assumption: behavior and armor are judgments, not measurements." Special cases: a stalemate (most runs drew) and "too close to call" (no factor moved the score by 0.02).
- **Cost.** About a dozen extra 200-run simulations: 0.3 s for a 1 v 1, about 1 s for a 6 v 1, and about 3 s extra for 10,000 ants v 1 lion. `run(..., explain=False)` skips this analysis; use it for quick probes such as the fair-fight search.
- **`summary()`** (`summary.py`) returns what the results page and the announcer need: win and draw percentages, average survivors, duration in seconds, the favorite (none for a draw, no contest, or an exact tie), and the deciding-factor text.

## Fair fight and next challenger (F06)

- **Fair-fight search (`fair.py`).** "How many house cats would make this a coin flip?" The search varies the count of the **losing** side (the side with the lower win share in the main result). It starts at the current count, doubles until the varied side's win share passes 55%, then bisects on whole numbers between the last count below 45% and the first above 55%. Each probe is a 200-run simulation (no deciding-factor analysis), at most 20 probes, counts capped at 10,000. It stops as soon as a probe lands within 5 points of 50% ("A fair fight needs 37 house cats against 1 gray wolf.").
- **When it can't.** If even 10,000 can't reach 45%, the answer is `count = None` with "No fair fight within 10,000 house cats." (a stalemate where neither side can win counts as this too). If the main fight is a draw or a `no_contest`, there is no loser to even up, so `count` is `None` with a plain explanation.
- **Whole numbers can't always hit 50%.** Near the balance point one extra fighter can move the win share by 10-20 points. When no integer lands within the 5-point band, the closest count found is returned with "about", and `win_prob_at_count` shows the real value.
- **Draws don't count as half a win.** The target is the varied side's win share alone, so a stalemate (for example ants against an elephant) can't masquerade as a fair fight.
- **Next challenger (`test_challengers`).** Given the winner's sheet and candidate sheets (the language model proposes the candidates elsewhere), it runs a 200-run 1 v 1 duel of the winner against each candidate and returns suggestions sorted by how close the candidate's win share is to 50%, with ties broken by name so results repeat exactly. A candidate that cannot meet the winner at all (`no_contest`) is left out. The reason text is a code template ("a coin flip", "a slight underdog", and so on) with no invented numbers.
- **Cost.** About 0.2 s for wolf vs house cats and about 4 s for the no-answer case (15 swarm probes up to 10,000 ants). One-by-one probes with many fighters (just under 200) are slower; see the speed note above.

## Machines, objects, and mythical abilities (F08)

**Bodies**
- **Machine** (vehicles, robots): never retreats or flees (no morale) and has no fatigue. When its sampled `endurance_s` (operating time) runs out it is **out of action**: a KO event with the hint "out of action: its operating time ran out", counted as a loss for that fighter. A whole swarm of machines stops together.
- **Inert** (objects, plants): never approaches, never retreats. It attacks only if it has an attack, and only once the other side has closed the distance. An inert fighter with `spines` hurts whoever hits it: each hit costs the attacker the inert fighter's own damage per hit (event hint "spines jab back").
- **Ramming and crushing:** damage per hit = `RAM_DAMAGE_PER_MOMENTUM x mass x speed` (momentum, the product of mass and velocity). Crushing floors the speed at `CRUSH_MIN_SPEED_MPS`. The attack rate is the constant `RAM_ATTACKS_PER_S`, replacing the sheet's. Mounted guns are not modeled (DECISIONS D-38).
- **No contest and draws:** if neither side can damage the other (no attack, or no way to close the distance) the result is `no_contest` with the hint "no contest: nobody can hurt anybody" (a rock vs a sword). If one side simply cannot finish the other in 600 s, the fight is a draw.

**Abilities** (from the stat sheet's `lore`)
- **Flight:** the creature uses air-terrain rules (forests hinder it more, open sky does not) and engages air and land targets. A flier cannot reach a swimmer in open water (`no_contest`), as for birds.
- **Breath weapon:** a ranged attack (square law: every individual can breathe on the same target, so no engagement cap), damage at least `BREATH_DAMAGE_N x DAMAGE_PER_NEWTON`, reaching `BREATH_RANGE_M`, so it attacks before melee fighters close in.
- **Regeneration:** heals `REGEN_SHARE_PER_S` of max hit points per second, up to full. Healing is applied lazily, when a fighter is next hit; the retreat (morale) check uses the same up-to-date totals, but a fighter nobody touches does not count unseen healing toward it. Fine for an assumption-level model.
- **Extra heads:** attack rate times the number of heads (`DEFAULT_HEADS` if the lore gives none).
- **Venom (D-44, #81):** a sheet with the `venom` weapon delivers `VENOM_BITE_SHARE` of a lethal dose per landed bite, scaled up for smaller targets and cut by the target's resistance. A fighter carries its doses until the fight is over. The fight itself is unchanged, but when one side is wiped out, any survivor on the other side carrying a full dose (1.0) dies `VENOM_ONSET_S` later (a "succumbs to venom" knock-out), and if that leaves nobody standing the result is a **draw**. So the badger kills the cobra, then either shrugs off the venom and wins, or succumbs and it is a draw. No constant is tuned to force a fight. The deciding factor is reported as `attack_force_n`, and the explainer names the venom or the resistance (no new contract value). Venom is modeled one by one (up to 200 per side); swarm mode does not apply it yet.
- The deciding-factor check also removes all abilities and re-runs (and, for a venomous fighter, removes the venom and then the resistance); if that moves the result most, the factor is `abilities` and the explainer says "according to legend".

**Certain results are not simulated.** Before running a fight, the engine asks whether the result is certain: if even the most damage possible (every fighter attacking as often as it can, every attack hitting, no healing) cannot kill a single fighter or push the other side past its morale limit before the fight must end, nothing can change. The fight is then a draw at 600 s, or, if a machine runs out of operating time first, a loss for that machine's side at that moment. This is exact, not an estimate: a test compares the shortcut with the full simulation on thousands of random fights with up to 12 fighters a side (0 differences found). Fights with more than 200 on a side are never shortcut, because swarm mode acts in coarse time steps and the bound would not be exact there; they are cheap to simulate anyway. A machine's operating-time stop is applied in order of operating time, and reported at the exact moment, in both modes. It keeps hopeless stalemates cheap (for example 150 feeble attackers against a mountain, or machines that never dent an object, which used to cost tens of seconds). A venomous bite that could add up to a full dose within the bound also makes the result uncertain (D-44), so those fights are simulated. Objects whose spines really hurt attackers are always simulated, and the replay of a representative fight is always simulated in full so the log shows real events.

**Calibration warning.** With these assumed constants a dragon built from the fixture sheet (6 t) cannot dent a 60 t tank with 80% armor in ten minutes. Showcase battle #5 (dragon vs main battle tank) will need its constants revisited once G09's real dragon sheet and the F07 benchmark exist.

## Why probabilities are shown as "range"

The 95% interval is a Wilson score interval on the share of runs won. Because every run draws different stats, the shares already blend in input uncertainty: when the stat ranges are narrow the fight's outcome is more predictable, so the win share moves toward 0 or 1 and the interval narrows (tested in `tests/property/test_simulation_engine.py`). The interval does *not* separately model uncertainty in the constants above.

## Not modeled yet

Fatigue for living fighters (`endurance_s` only stops machines). A `no_contest` reports `habitat` (cannot reach) or `attack_force_n` (cannot hurt) as its deciding factor.

## References

- Lanchester, F. W. (1916). *Aircraft in Warfare: The Dawn of the Fourth Arm.*
- Hill, A. V. (1950). The dimensions of animals and their muscular dynamics. *Science Progress* 38, 209-230.
- Garland, T. (1983). The relation between maximal running speed and body mass in terrestrial mammals. *Journal of Zoology* 199, 157-170.
- Kleiber, M. (1932). Body size and metabolism. *Hilgardia* 6, 315-353.
- West, G. B., Brown, J. H. & Enquist, B. J. (1997). A general model for the origin of allometric scaling laws in biology. *Science* 276, 122-126.
- Packer, C. & Ruttan, L. (1988). The evolution of cooperative hunting. *The American Naturalist* 132, 159-198.
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *JASA* 22, 209-212.
