# Showcase dry run (engine check with the real seed sheets)

The five showcase battles (PRODUCT_SPEC section 9) run through the engine to find problems early. Reproduce with `uv run --directory backend python scripts/showcase_dry_run.py` (about 12 s; `--runs` to shorten).

**Read this first.** Every fighter except the dragon is now a real, hand-verified seed sheet (G05, in `data/seed/fighters/`, with sources and quotes). The **dragon is still a stand-in with round numbers**: it is not sourced, not for display, and G09 builds the real mythical sheets from their analogs. The results below say how the *engine* behaves with the sheets as they are today, not the final demo wording.

| Stand-in | Mass kg | Size m | Speed m/s | Attack N | Attacks/s | Reach m | Armor | Aggression | Teamwork |
|---|---|---|---|---|---|---|---|---|---|
| Dragon | 6,000 | 10.9 | 12 | 60,000 | 0.5 | 4.0 | 0.7 | 0.9 | 0.1 |

## Results (1,000 runs each, engine version 8, with the deciding-factor analysis and fair-fight search)

| Battle | Verdict | Sensible? | Time |
|---|---|---|---|
| 100 duck-sized horses vs 1 horse-sized duck (open field) | Duck wins 99.9% (about 75 s). A fair fight needs 550 horses | Yes; the explanation credits the scaling (finding 1, fixed) | 5.8 s |
| Grizzly vs 6 wolves (forest) | **Wolves 76% / grizzly 24%**, about 37 s, "size decided it". A fair fight needs about 2 grizzlies | Yes: a believable "crowd wears down a tougher fighter" (finding 5) | 1.3 s |
| Honey badger vs king cobra | Badger wins 93.5%, cobra 6.4%, 0.1% draws, about 9 s; the explainer credits its venom resistance. A fair fight needs about 4 cobras | Yes: venom matters now, and the badger mostly shrugs it off (findings 2 and 6) | 0.5 s |
| Roman legionary vs gorilla (forest) | Gorilla 100% (about 8 s), "strength decided it". A fair fight needs 40 legionaries | Yes, but the legionary is weak: its sheet uses a 150 N stab (finding 6) | 1.5 s |
| A dragon vs a main battle tank (open field) | Tank wins 100% (about 78 s), "size decided it". A fair fight needs about 5 dragons | Possible, but a foregone conclusion (finding 3) | 1.8 s |

## Findings

### 1. The headline battle's explanation credited the wrong cause (fixed)
The first run of this dry run said "Attack rate decided it: Duck (2 attacks per second) against Horse (0.5 attacks per second)." The real reason is the size scaling (a duck grown to 500 kg against horses shrunk to 1.2 kg). The deciding-factor check equalized the *sheet* stats but left the scaling in place, so size never showed up as a factor.
- **Fix (merged in #69):** the check now also re-runs the fight without the scale factors. When that moves the result most, it reports size and quotes the sheets and the references. The battle now reads: "Size decided it: after scaling, Duck (1.2 kg normally, scaled to horse size) against 100 Horse (500 kg normally, scaled to duck size)." Every number is still an input.

### 2. Venom (modeled since #81, D-44)
The first run of this dry run found that a sheet could list `venom` but the engine had no venom mechanic, so a king cobra's 100 N bite did almost nothing to a 10 kg badger and the badger won 100%. **Decided (D-42, refined by D-44):** model venom as a dose that works after the fight, with assumption-labeled constants and a resistance entry for the honey badger. That is now in the engine (#81).
- With the stand-in cobra (100 N) and the badger using the `honey-badger` id, battle 3 was a **100% badger win in about 3 s**. With the real sheets (the cobra bites at 300 N and weighs 10 kg, D-54) it is a **93.5% badger win in about 9 s**, and the explainer still reads "Honey badger's venom resistance decided it: it shrugs off bites that would kill others."
- Without the resistance entry (the same badger under another id), the badger wins 83% and the other 17% are draws, because the poisoned badger dies after the fight; the fight lasts about 23 s, and the explainer says "Size decided it", which does not mention venom (the sensitivity check ranks size higher).
- Venom resolves 120 s after the last blow and only when a side is wiped out. Swarm mode ignores it, whatever made the fight a swarm (head count, or the work rule of D-50).

### 3. The dragon can't touch a main battle tank
The real tank sheet is 70 t (the top of the 40 to 70 t range, D-47), so it has 700,000 hit points (10 hp per kg); the table below was measured earlier against a 60 t stand-in tank at engine version 6 and shows the shape, not today's figures. The dragon's breath is about 5,000 damage per hit.

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
The duck/horse battle took 5.8 s end to end (4.4 s at engine version 6) (101 fighters one by one, the deciding-factor analysis, and the fair-fight search, which goes into swarm mode above 200 horses). That is fine for a pre-generated showcase battle, but not for a live user. Live runs of groups near 100 per side will be slow; see [swarm-validation.md](swarm-validation.md) (arrives with #75; the fix for swarm accuracy is tracked in #76).

### 5. Showcase battle 2 flips with the real grizzly and wolf sheets (unchanged since)
The earlier stand-in run (contract fixtures, engine version 5) gave grizzly 53% / wolves 47%. With engine version 6 (exact attack schedule, #84) and the hand-verified G05 seed sheets (#139), the same fight is **wolves 76% / grizzly 24%**, about 36 s, and the explainer says numbers decided it. The same engine on the old contract fixtures gives grizzly 49% / wolves 51%, so most of the shift comes from the sheets. The main causes are the grizzly's real bite (751 N from a skull-based estimate the sheet says likely runs low, against 4,000 N on the old fixture) and its mass, which the engine draws between 139 and 389 kg rather than at 389 (pinned at 389 kg it would be about 42% / 58%). The wolf's speed makes no difference, its 593 N bite is lower than the old fixture's, and its group tactics of 0.8 is an assumption, not a sourced figure. (These what-if figures are one-off runs.)
- It is still plausible and explainable ("a crowd can wear down even a tougher fighter"), and the fair-fight search works on it ("about 2 grizzly bears against 6 gray wolves"). The what-if figures can be repeated by editing one value on the seed sheets or the wolf count in `battles()` and re-running the script; the wolf count alone gives 3 wolves = 63.5% grizzly, 4 = 44.3%, 5 = 30.5%, 6 = 24.4%.
- The numbers are the same at engine version 8 (24.3% grizzly, 75.7% wolves). The grizzly sheet goes back to G05 for a recheck under D-47 first (#166) (its 751 N bite, and its 389 kg `value` at the top of a 139 to 389 kg range). After that the demo narrative or the wolf count for battle 2 is decided as part of showcase calibration (G08, #47), not an engine change.

### 6. The real cobra and legionary move battles 3 and 4
Replacing the stand-ins with the sourced sheets changes two battles, and neither is an engine problem.
- **Roman legionary vs gorilla:** the legionary's attack force is 150 N (Nolan et al. stab-force study, D-54(3)), against the 1,500 N stand-in. The gorilla still wins 100%, but a fair fight now needs **40 legionaries** instead of about 4, and "strength decided it" reads 3,420 N against 150 N. The same sheet makes the benchmark row cnt-05 (legionary v grizzly, expected fair count 2 to 8) fail with a count of 24; whether 150 N is a fair stand-in for a trained sword thrust is Mike's and Gunnar's call, not an engine change.
- **Honey badger vs king cobra:** the real cobra bites harder (300 N, 10 kg, venom), so the badger wins 93.5% instead of 100%, with a few draws from poisoned badgers, and a fair fight needs about 4 cobras instead of 30. The badger's venom resistance still decides it.

## What this does not check
The dragon's real sheet, the announcer, sprites, and the UI. It only checks that the engine produces a sensible, explainable verdict for each demo battle.
