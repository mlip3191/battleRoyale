# Slide: what we decided not to build, and what we learned (loadouts)

*One slide for the deck (Limitations and Build Process), from `docs/loadouts-design.md`. Mike's ruling: loadouts are post-MVP (D-56); this slide shows the work and the honest result.*

## Title
**Fighters that grow: designed, tested, and deliberately parked**

## Four lines
- **The idea:** after each round a fighter adds or upgrades one loadout (attack, defense, speed, balanced), with gear that fits its kind: claws for a wolf, a hardened hoof for a horse, plate for a legionary (180 item names, pre-modern and natural only, not yet sourced).
- **The rule that kept it honest:** every loadout is a multiplier on the fighter's own stat, labeled an assumption, and every choice gains one thing and costs another, so no gear is a free upgrade (a test checks it for every kind of fighter).
- **What our own balance check found:** the first version was a dominant strategy (one kit was best in 58% of close fights, as recorded in the design doc). We rebalanced until the best kit won about four to five in ten and most kits were best somewhere, but with only 19 close fights among 15 fighters, and a two-loadout kit still winning 74% at 4 points, it is not solved.
- **Why it is parked:** it needs a contract change, a cache key and narration, its multipliers are new assumptions the benchmark cannot check yet, and the engine rewards attack far more than speed or armor (changing that is an engine version bump).

## A number to show (all from the simulator)
| Fight | No kit | Best of the kits tried | Worst of the kits tried |
|---|---|---|---|
| Roman legionary v gray wolf | 11% | 18% (balanced, tier 3) | 2% (speed, tier 4) |
| Gray wolf v Roman legionary | 91% | 94% (attack, tier 3) | 75% (defense, tier 5: heavy gear slows it) |

*Win share of the first fighter, 2,000 runs, re-measured on engine 12 (`docs/loadouts-design.md` section 4 has the original 500-run figures from an earlier engine, which differ by up to 3 points).*

## Speaker note (20 seconds)
"We built the whole system and then asked our own harness whether it was fair. It was not, so we fixed it, and the honest result is that gear only nudges fights that were already close. With code complete near, the PM parked it, and the design and the harness are in the repo for next time."

## Sources
`docs/loadouts-design.md`, `backend/scripts/loadout_balance.py`, PR #284, D-56.
