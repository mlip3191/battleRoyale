# Showcase dry run (engine check with stand-in sheets)

The five showcase battles (PRODUCT_SPEC §9) run through the engine before the real stat sheets exist, to find problems early. Reproduce with `uv run --directory backend python scripts/showcase_dry_run.py` (about 25 s; `--runs` to shorten).

**Read this first.** Only the grizzly and the gray wolf are real sheets (contract fixtures with Wikipedia citations). Every other fighter is a **stand-in with round numbers** from common reference values. They are not sourced, they are not for display, and the results below say how the *engine* behaves, not what the final demo will show. G05 and G09 will replace the stand-ins.

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

## Results (1,000 runs each, with the deciding-factor analysis and fair-fight search)

| Battle | Verdict | Sensible? | Time |
|---|---|---|---|
| 100 duck-sized horses vs 1 horse-sized duck (open field) | Duck wins 100% (about 103 s) | Yes; the explanation now credits the scaling (finding 1, fixed) | 7.4 s |
| Grizzly vs 6 wolves (forest) | Grizzly 53% / wolves 47%, about 18 s | Yes: a close, believable fight. Fair fight is 6 wolves | 1.4 s |
| Honey badger vs king cobra | Badger wins 100% in about 3 s | Overconfident: the cobra can't hurt it (finding 2) | 1.1 s |
| Roman legionary vs gorilla (forest) | Gorilla 99.9% | Yes. A fair fight needs about 5 legionaries, a nice talking point | 0.6 s |
| A dragon vs a main battle tank (open field) | Tank wins 100% (about 83 s) | Possible, but a foregone conclusion (finding 3) | 4.6 s |

## Findings

### 1. The headline battle's explanation credited the wrong cause (fixed)
The first run of this dry run said "Attack rate decided it: Duck (2 attacks per second) against Horse (0.5 attacks per second)." The real reason is the size scaling (a duck grown to 500 kg against horses shrunk to 1.2 kg). The deciding-factor check equalized the *sheet* stats but left the scaling in place, so size never showed up as a factor.
- **Fix (merged into this stack):** the check now also re-runs the fight without the scale factors. When that moves the result most, it reports size and quotes the sheets and the references. The battle now reads: "Size decided it: after scaling, Duck (1.2 kg normally, scaled to horse size) against 100 Horse (500 kg normally, scaled to duck size)." Every number is still an input.

### 2. Venom is not modeled, so the cobra is toothless
A sheet can list `venom`, but the engine has no venom mechanic (F08 covers bodies and legendary abilities, not venom). A real king cobra can kill; here a 100 N bite does almost nothing against a 10 kg badger with 0.5 armor, so the badger wins 100% and the log is only 11 events.
- **Options:** (a) add a venom effect (damage over time, constants labeled as assumptions, venom resistance for the badger as a stat or note); (b) give venomous sheets an effective attack force through the number rule's `assumption` path; (c) accept it and pick a different matchup. Needs a decision from Mike.

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

Armor barely matters because damage is dominated by the hit-point pool. If we want a real contest, the lever is the breath constant (`BREATH_DAMAGE_N`, an assumption) or how a machine's hit points scale. If we only want to show "legends and machines play by the same rules," a tank win is fine; the fair-fight line ("about 6 dragons against 1 tank") is a good demo moment either way. **This needs a decision, and it should wait for G09's real dragon sheet.**

### 4. Speed
The duck/horse battle took 7.4 s end to end (101 fighters one by one, the deciding-factor analysis, and the fair-fight search, which goes into swarm mode above 200 horses). That is fine for a pre-generated showcase battle, but not for a live user. Live runs of groups near 100 per side will be slow; see `docs/swarm-validation.md`.

## What this does not check
Real sheets, real sources, the announcer, sprites, and the UI. It only checks that the engine produces a sensible, explainable verdict for each demo battle.
