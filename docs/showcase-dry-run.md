# Showcase dry run (engine check with stand-in sheets)

The five showcase battles (PRODUCT_SPEC §9) run through the engine before the real stat sheets exist, to find problems early. Reproduce with `uv run --directory backend python scripts/showcase_dry_run.py` (about 10 s; `--runs` to shorten).

**Read this first.** Only the grizzly and the gray wolf are real sheets (the hand-verified G05 seed sheets in `data/seed/fighters/`, with Wikipedia and Wroe 2005 citations). Every other fighter is a **stand-in with round numbers** from common reference values. They are not sourced, they are not for display, and the results below say how the *engine* behaves, not what the final demo will show. G05 and G09 will replace the stand-ins.

| Stand-in | Mass kg | Size m | Speed m/s | Attack N | Attacks/s | Reach m | Armor | Aggression | Teamwork |
|---|---|---|---|---|---|---|---|---|---|
| Horse | 500 | 2.4 | 20 | 6,000 | 0.5 | 1.5 | 0.05 | 0.3 | 0.4 |
| Duck | 1.2 | 0.55 | 5 | 20 | 2.0 | 0.2 | 0.05 | 0.3 | 0.3 |
| Honey badger | 10 | 0.75 | 8 | 300 | 2.0 | 0.3 | 0.5 | 1.0 | 0.0 |
| King cobra | 6 | 3.5 | 5 | 100 | 1.5 | 1.2 | 0.1 | 0.5 | 0.0 |
| Roman legionary | 75 | 1.75 | 6 | 1,500 | 1.0 | 0.9 | 0.5 | 0.7 | 0.9 |
| Gorilla | 160 | 1.7 | 7 | 6,000 | 1.0 | 1.0 | 0.15 | 0.5 | 0.2 |
| Dragon | 6,000 | 10.9 | 12 | 60,000 | 0.5 | 4.0 | 0.7 | 0.9 | 0.1 |
| Main battle tank (machine, rams) | 60,000 | 10 | 18 | 0 (ramming) | 0.4 | 1.0 | 0.9 | 0 | 0 |

## Results (1,000 runs each, engine version 6, with the deciding-factor analysis and fair-fight search)

| Battle | Verdict | Sensible? | Time |
|---|---|---|---|
| 100 duck-sized horses vs 1 horse-sized duck (open field) | Duck wins 100% (about 94 s). A fair fight needs 275 horses | Yes; the explanation credits the scaling (finding 1, fixed) | 4.4 s |
| Grizzly vs 6 wolves (forest) | **Wolves 76% / grizzly 24%**, about 36 s, "numbers decided it". A fair fight needs about 2 grizzlies | Yes, but it changed with the real sheets (finding 5) | 1.4 s |
| Honey badger vs king cobra | Badger wins 100% in about 3 s | Overconfident: the cobra can't hurt it (finding 2) | 0.9 s |
| Roman legionary vs gorilla (forest) | Gorilla 100% | Yes. A fair fight needs about 4 legionaries, a nice talking point | 0.4 s |
| A dragon vs a main battle tank (open field) | Tank wins 100% (about 84 s) | Possible, but a foregone conclusion (finding 3) | 2.1 s |

## Findings

### 1. The headline battle's explanation credited the wrong cause (fixed)
The first run of this dry run said "Attack rate decided it: Duck (2 attacks per second) against Horse (0.5 attacks per second)." The real reason is the size scaling (a duck grown to 500 kg against horses shrunk to 1.2 kg). The deciding-factor check equalized the *sheet* stats but left the scaling in place, so size never showed up as a factor.
- **Fix (merged in #69):** the check now also re-runs the fight without the scale factors. When that moves the result most, it reports size and quotes the sheets and the references. The battle now reads: "Size decided it: after scaling, Duck (1.2 kg normally, scaled to horse size) against 100 Horse (500 kg normally, scaled to duck size)." Every number is still an input.

### 2. Venom (modeled since #81, D-44)
The first run of this dry run found that a sheet could list `venom` but the engine had no venom mechanic, so a king cobra's 100 N bite did almost nothing to a 10 kg badger and the badger won 100%. **Decided (D-42, refined by D-44):** model venom as a dose that works after the fight, with assumption-labeled constants and a resistance entry for the honey badger. That is now in the engine (#81).
- With the stand-in cobra carrying `venom` and the badger using the `honey-badger` id, battle 3 is still a **100% badger win in about 3 s**, and the explainer now reads "Honey badger's venom resistance decided it: it shrugs off bites that would kill others."
- Without the resistance entry (the same badger under another id), the badger wins 83% and the other 17% are draws, because the poisoned badger dies after the fight; the fight lasts about 23 s, and the explainer says "Size decided it", which does not mention venom (the sensitivity check ranks size higher).
- Venom resolves 120 s after the last blow and only when a side is wiped out. Swarm mode (above 200 per side) ignores it.

### 3. The dragon can't touch a 60-tonne tank
Hit points scale with mass (10 hp per kg), so the tank has 600,000. The dragon's breath is about 5,000 damage per hit.

| Change | Dragon win chance vs the tank |
|---|---|
| As built | 0% |
| Breath damage x10 | 12% |
| Breath damage x20 | 39% |
| Breath damage x40 | 76% |
| Tank armor 0.9 down to 0.3 (breath as built) | still 0% |
| Tank mass 60 t down to 30 t | 0% |
| Tank mass 15 t | 27% |
| Tank mass 8 t | 88% |

Armor barely matters because damage is dominated by the hit-point pool. (The what-if rows above are one-off runs with edited constants or sheet values; this script does not produce them.) If we want a real contest, the lever is the breath constant (`BREATH_DAMAGE_N`, an assumption) or how a machine's hit points scale. If we only want to show "legends and machines play by the same rules," a tank win is fine; the fair-fight line ("about 6 dragons against 1 tank") is a good demo moment either way. **Decided (D-43):** wait for G09's real dragon sheet; a tank win is acceptable for the demo; no constant changes until then.

### 4. Speed
The duck/horse battle took 4.4 s end to end (101 fighters one by one, the deciding-factor analysis, and the fair-fight search, which goes into swarm mode above 200 horses). That is fine for a pre-generated showcase battle, but not for a live user. Live runs of groups near 100 per side will be slow; see [swarm-validation.md](swarm-validation.md) (arrives with #75; the fix for swarm accuracy is tracked in #76).

### 5. Showcase battle 2 flips with the real grizzly and wolf sheets
The earlier stand-in run (contract fixtures, engine version 5) gave grizzly 53% / wolves 47%. With engine version 6 (exact attack schedule, #84) and the hand-verified G05 seed sheets (#139), the same fight is **wolves 76% / grizzly 24%**, about 36 s, and the explainer says numbers decided it. The same engine on the old contract fixtures gives grizzly 49% / wolves 51%, so most of the shift comes from the sheets. The main causes are the grizzly's real bite (751 N from a skull-based estimate the sheet says likely runs low, against 4,000 N on the old fixture) and its mass, which the engine draws between 139 and 389 kg rather than at 389 (pinned at 389 kg it would be about 42% / 58%). The wolf's speed makes no difference, its 593 N bite is lower than the old fixture's, and its group tactics of 0.8 is an assumption, not a sourced figure. (These what-if figures are one-off runs.)
- It is still plausible and explainable ("a crowd can wear down even a tougher fighter"), and the fair-fight search works on it ("about 2 grizzly bears against 6 gray wolves"). The what-if figures can be repeated by editing one value on the seed sheets or the wolf count in `battles()` and re-running the script; the wolf count alone gives 3 wolves = 63.5% grizzly, 4 = 44.3%, 5 = 30.5%, 6 = 24.4%.
- The grizzly sheet goes back to G05 for a recheck under D-47 first (its 751 N bite, and its 389 kg `value` at the top of a 139 to 389 kg range). After that the demo narrative or the wolf count for battle 2 is decided as part of showcase calibration (G08, #47), not an engine change.

## What this does not check
Real sheets, real sources, the announcer, sprites, and the UI. It only checks that the engine produces a sensible, explainable verdict for each demo battle.
