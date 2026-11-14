# Loadouts and tournament progression (design, prework for #283)

**Status: prework, not decided.** Nothing here is wired into battles or the API. Mike decides the scope on #283. Everything below is built to be safe to adopt, not to force the choice.

What exists in code today (PR #284, draft): four loadouts (attack, defense, speed, balanced), applied to a stat sheet by code (`backend/app/simulation/loadouts.py`), with tiers 1 to 3. What this page adds: the list of items, how they improve through the tournament, and what the simulator says about whether it matters.

## 1. The items

Twelve items, three per loadout, all pre-modern (D-07 and D-38 block firearms, explosives and modern vehicles as fighters, so none is offered). The list lives in `data/loadouts/items.yaml`; a test checks that every name is safe to show, no item is modern, and no sourced number is stored there yet.

| Loadout | Tier 1 (from the start) | Tier 2 (after winning round 1) | Tier 3 (after winning round 2) |
|---|---|---|---|
| **Attack** | wooden club | iron war hammer | steel battle axe |
| **Defense** | wooden shield | iron rimmed shield | tower shield and mail shirt |
| **Speed** | leather wraps | light leather armor and boots | skirmisher kit |
| **Balanced** | short sword and cloak | arming sword and buckler | longsword and mail shirt |

An item is only a name until a teammate sources its real-world facts (typical mass, material), with a URL and an exact quote like any stat sheet; the `research` list on each item says what to find. Until then no real-world number is shown next to an item.

## 2. What each tier does (assumptions, not sourced figures)

A tier-up deepens the trade-off instead of just adding strength: gains and costs both grow, by 1.4 at tier 2 and 1.8 at tier 3 (`LOADOUT_TIER_SCALE` in `constants.py`). So a higher tier is a bigger commitment, never a strictly better set of stats (a test checks it, and that no loadout at any tier is at least as good as another in all four changed stats).

| Loadout | Tier | Attack force | Attack rate | Top speed | Armor |
|---|---|---|---|---|---|
| Attack | 1 / 2 / 3 | x1.5 / x1.7 / x1.9 | x0.80 / x0.72 / x0.64 | x0.95 / x0.93 / x0.91 | +0 |
| Defense | 1 / 2 / 3 | x1.0 | x0.90 / x0.86 / x0.82 | x0.90 / x0.86 / x0.82 | +0.20 / +0.28 / +0.36 |
| Speed | 1 / 2 / 3 | x0.90 / x0.86 / x0.82 | x1.0 | x1.25 / x1.35 / x1.45 | -0.10 / -0.14 / -0.18 |
| Balanced | 1 / 2 / 3 | x1.15 / x1.21 / x1.27 | x1.0 | x0.97 / x0.958 / x0.946 | +0.08 / +0.112 / +0.144 |

Example, a gray wolf on the attack path: attack force 593 N, then 890 N, 1,008 N, 1,127 N; attacks per second 1.5, then 1.2, 1.08, 0.96; top speed 17.8 m/s, then 16.9, 16.5, 16.2; armor unchanged.

## 3. How a fighter improves over the tournament

The bracket is eight fighters, single elimination, three rounds (`simulation/tournament.py`).

1. **Entry:** each fighter picks one loadout and starts at tier 1.
2. **Winning a round earns one upgrade point.** Round 1 winners get one before the semifinal, round 2 winners one before the final. Losers are out, so only the champion path ever gets two.
3. **Spending a point:** either **tier up** (the same loadout, next tier) or **switch** to another loadout at the tier it already has. A fighter with no choice made tiers up by default, so a bracket is always deterministic.
4. **At most tier 3, in the final**, and only by tiering up twice.
5. **Reproducible:** the loadout enters the sheet, so the sheet hash changes and with it the seed and the cache key. The same bracket with the same choices gives the same champion.

What it would need later: a loadout field per fighter and an upgrade choice per round on the tournament request (a contract change, with Mike's approval and the `contract-change` label), the explainer saying "with an attack loadout, tier 2", and the research on the items.

## 4. Does it matter? What the simulator says

I ran eight seed fighters (grizzly, elephant, gorilla, crocodile, horse, wolf, legionary and tank) through a sample bracket (arena, 200 runs per match) with everyone on the same loadout and tiering up each round, for all four loadouts, and compared it with no loadouts. **The bracket was identical every time** (the tank beat the elephant in the final): the size gaps between fighters are far bigger than a loadout's change.

Where it does move results is close fights. A fighter with a loadout against an opponent without one, win share of the loadout fighter (300 runs):

| Fight | No loadout | Best loadout | Worst loadout |
|---|---|---|---|
| Roman legionary v gray wolf | 10% | balanced tier 3: 23% | speed tier 3: 5% |
| Horse v saltwater crocodile | 1% | balanced tier 3: 3% | speed tier 3: 0% |
| Gray wolf v gorilla | 0% | 0% | 0% |
| Grizzly v African elephant | 0% | 0% | 0% |

So with today's assumptions a loadout is a modest nudge: it changes a fight that was already close, not a lopsided one, and the best loadout depends on the fight (a speed loadout hurt in both close fights above and in 3 wolves v a grizzly, where balanced helped most). That is the intended trade-off, but it means "get stronger over the tournament" will not feel dramatic unless one of these changes:
- **Bigger tier scales** (for example x1.0 / x2.0 / x3.0), which also makes the costs bigger.
- **Closer brackets:** seed the eight so early rounds are close fights, which is where loadouts matter.
- **Accept it as flavor** for close fights and keep the story in the explainer ("the shield decided it").
These are assumptions, so changing them is a design call and a number to label, not an engine change.

## 5. Open questions for Mike

1. Is this in scope for the course project at all (code complete Nov 25), or post-MVP?
2. Which scale: modest nudges (as now), bigger tiers, or seeding for close fights?
3. Is the pre-modern item list the right safety line, or should a few non-firearm machines (a siege engine, a chariot) be allowed? The engine models vehicles already (the tank is a seed fighter), but D-38 blocks modern ones.
4. Should the user pick the loadout and each upgrade, or only the loadout (with automatic tier-ups)?
5. Does a loadout need critical hits to feel different? That is a new mechanic (a seeded draw per attack, parity tests against swarm mode, an `ENGINE_VERSION` bump), so it is left out until you ask for it.
