# Loadouts and tournament progression (design, prework for #283)

**Status: prework, not decided.** Nothing here is wired into battles or the API. Mike decides the scope on #283. Everything below is built to be safe to adopt, not to force the choice.

What exists in code today (PR #284, draft): four loadouts (attack, defense, speed, balanced) with five tiers, combined into a **kit** that is applied to a stat sheet by code (`backend/app/simulation/loadouts.py`), scaled by the fighter's own starting stats with a bonus for its primary attribute, and with the negative traits of carrying a lot. This page covers the items, how a fighter improves through the tournament, and what the simulator says about whether it matters.

## 1. The items: what each kind of fighter carries

What a fighter can carry depends on what it is. A warrior carries iron, a wolf grows claws and hide, a horse hardens its hooves, a bird sharpens its talons, a tank bolts on plating. There are nine kinds (`data/loadouts/items.yaml`), each with the same four loadouts and five items per loadout, so 180 items; the kind comes from the stat sheet (its category, and its weapons for hooves, horns and tusks). All are natural or pre-modern: D-07 and D-38 block firearms, explosives and modern vehicles as fighters, so none is offered. A test checks every name is safe to show and no item is modern. An item is only a name until a teammate sources its real-world facts with a URL and an exact quote, like a stat sheet; each kind has a `research` note saying what to find.

The effect of a loadout is the same for every kind of fighter (section 3); what differs is the **name of the item** and **how heavy it is** (which decides when the negative traits start).

**Warrior** (human warriors (the Roman legionary))

| Loadout | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|
| Attack | wooden club | iron war hammer | steel battle axe | two-handed greatsword | steel halberd |
| Defense | wooden shield | iron rimmed shield | tower shield and mail shirt | brigandine and heater shield | full plate harness |
| Speed | leather wraps | light leather armor and boots | skirmisher kit | runner kit with sling | scout gear and light bow |
| Balanced | short sword and cloak | arming sword and buckler | longsword and mail shirt | sword and half plate | knights kit |

**Mammal** (land mammals with claws and teeth (wolf, bear, lion, gorilla, honey badger, cat))

| Loadout | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|
| Attack | sharper claws | hardened claws | razor claws | crushing jaws | killer instinct |
| Defense | thicker hide | scarred hide | bony plates | layered hide | armored hide |
| Speed | lean muscle | sprint conditioning | light frame | long stride | burst speed |
| Balanced | hunting practice | trained instincts | seasoned fighter | veteran of many fights | apex predator |

**Hoofed** (mammals that fight with hooves, horns or tusks (horse, elephant))

| Loadout | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|
| Attack | stronger kicks | hardened hooves | crushing blows | battering charge | trampling charge |
| Defense | thick hide | toughened hide | muscle armor | heavy bulk | armored bulk |
| Speed | stronger legs | long stride | light gait | full gallop | charge speed |
| Balanced | herd instincts | steady nerves | seasoned veteran | old leader | herd leader |

**Reptile** (reptiles, amphibians and dinosaurs (crocodile, cobra))

| Loadout | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|
| Attack | sharper fangs | hardened claws | tail lash | crushing bite | death roll |
| Defense | thicker scales | ridged scales | bony scutes | armored back | plated hide |
| Speed | warmed muscles | quick strike | light body | burst sprint | coiled spring |
| Balanced | ambush practice | patient hunter | seasoned fighter | old survivor | apex hunter |

**Bird** (birds (eagle, duck))

| Loadout | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|
| Attack | sharper talons | hardened beak | razor talons | striking dive | crushing grip |
| Defense | thicker feathers | dense plumage | tough skin | armored breast | hardened plumage |
| Speed | stronger wings | steeper dive | lean flight muscle | tail steering | stooping speed |
| Balanced | hunting practice | sharp eyes | seasoned hunter | veteran flier | master of the air |

**Aquatic** (fish and mollusks)

| Loadout | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|
| Attack | sharper teeth | stronger jaws | serrated bite | crushing bite | thrashing strike |
| Defense | thicker scales | tough skin | hardened shell | ridged plates | armored scales |
| Speed | stronger fins | streamlined body | strong tail | burst swim | torpedo speed |
| Balanced | hunting practice | sharp senses | seasoned hunter | old survivor | apex hunter |

**Insect** (insects and arachnids)

| Loadout | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|
| Attack | sharper mandibles | hardened mandibles | longer stinger | crushing pincers | strong venom sac |
| Defense | thicker chitin | hardened shell | ridged plates | layered chitin | armored shell |
| Speed | stronger legs | lighter body | quick wings | burst sprint | darting speed |
| Balanced | swarm instinct | trained reflexes | seasoned fighter | old survivor | queen of the colony |

**Machine** (vehicles and machines (tank, bulldozer))

| Loadout | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|
| Attack | reinforced ram plate | hardened ram | spiked ram | heavy ram | siege ram |
| Defense | bolted armor plates | layered plating | sloped plating | heavy plating | reinforced hull |
| Speed | tuned engine | lighter wheels | stripped body | better gearing | racing tune |
| Balanced | service upgrade | field repairs | reinforced frame | veteran crew | full overhaul |

**Mythical** (mythical creatures (dragon, griffin))

| Loadout | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|
| Attack | sharpened claws | tempered fangs | fire-touched claws | fangs of legend | claws of legend |
| Defense | thicker hide | charmed hide | scales of bronze | scales of iron | scales of legend |
| Speed | stronger wings | swifter wings | wind-touched wings | storm wings | wings of legend |
| Balanced | old magic | ancient cunning | seasoned legend | hardened legend | legend of legends |

## 2. How a fighter improves: the kit

A fighter carries a **kit**: each loadout at its own tier (or not at all). **Each choice is one of two things: add a loadout it does not carry (it starts at tier 1), or upgrade one it carries by a tier** (up to tier 5). Tier N of a loadout needs tier N-1 of the same loadout first.

In the tournament (eight fighters, single elimination, three rounds):
1. **At entry** the fighter has **2 points** to spend (for example attack tier 2, or attack 1 and defense 1).
2. **Winning a round earns 1 point**, spent before the next round: add a loadout or upgrade one. Round 1 winners get one before the semifinal, round 2 winners one before the final. Losers are out.
3. So a champion makes **four choices** and enters the final with a kit worth 4 points (for example attack 2, balanced 1 and defense 1, or one loadout at tier 4). Tier 5 is out of reach in this format; it exists for longer formats (a 16-fighter bracket, a best-of series) and for stacking.
4. A fighter that makes no choice defaults to upgrading its highest loadout, so a bracket is always deterministic. The kit changes the sheet hash, so the seed and the cache key change with it; the same bracket with the same choices gives the same champion.

What it would need later: a kit per fighter and a choice per round on the tournament request (a contract change, with Mike's approval and the `contract-change` label), the explainer saying "with a kit of attack 2 and defense 1", and the research on the items.

## 3. What each tier does, and the negative traits

All numbers are **assumptions**, not sourced figures (`LOADOUTS`, `LOADOUT_TIER_SCALE` and the weight rules in `constants.py`). A tier-up deepens a loadout's trade-off: gains and costs both grow (x1.0, x1.4, x1.8, x2.2, x2.6). On top of that, gear has weight, which gives the negative traits:

- **Encumbrance (too much defense reduces speed):** every tier adds weight, and what it weighs depends on the kind of fighter. A warrior's iron is heaviest (attack 1.0, defense 1.5, balanced 0.8, speed 0.3 per tier, 2.0 carried free); an animal's claws and hide are lighter (for a land mammal 0.5, 1.0, 0.4 and 0.1); a hoofed animal's bulk and a bird's plumage weigh more on defense (1.2 each), and a bird starts to slow at 1.5 because it must fly; insects carry the most for free (2.5) and a machine more still (3.0). Above its free load, each unit of weight cuts top speed by 6% and attack rate by 3% (floors at half speed and 60% rate). Stacking two heavy loadouts is slower than either alone. The tables below are for a warrior; a land mammal is slowed far less.
- **Reckless:** attack above tier 3 cuts armor by 10% per tier (a fighter who only hits).
- **Fragile:** speed above tier 3 cuts attack force by 4% per tier (gear too light to hit hard).

Resulting multipliers for one loadout alone at each tier, for a warrior (force / rate / speed / armor):

| Loadout | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|
| Attack | 1.5 / 0.80 / 0.95 / 1.0 | 1.7 / 0.72 / 0.93 / 1.0 | 1.9 / 0.62 / 0.86 / 1.0 | 2.1 / 0.53 / 0.78 / 0.9 | 2.3 / 0.44 / 0.71 / 0.8 |
| Defense | 1.0 / 0.90 / 0.90 / 1.5 | 1.0 / 0.83 / 0.81 / 1.7 | 1.0 / 0.76 / 0.70 / 1.9 | 1.0 / 0.69 / 0.59 / 2.1 | 1.0 / 0.62 / 0.50 / 2.3 |
| Speed | 0.90 / 1.0 / 1.25 / 0.8 | 0.86 / 1.0 / 1.35 / 0.72 | 0.82 / 1.0 / 1.45 / 0.64 | 0.75 / 1.0 / 1.55 / 0.56 | 0.68 / 1.0 / 1.65 / 0.48 |
| Balanced | 1.15 / 1.0 / 0.97 / 1.2 | 1.21 / 1.0 / 0.96 / 1.28 | 1.27 / 0.99 / 0.92 / 1.36 | 1.33 / 0.96 / 0.87 / 1.44 | 1.39 / 0.94 / 0.81 / 1.52 |

### Starting stats matter, and a fighter's primary attribute pays extra

Every change is a **multiplier on the fighter's own stat**, never a flat number, so the starting stats decide how much a loadout is worth. The same tier-3 speed loadout takes a cheetah from 29 to 46 m/s (+17) but a gray wolf only from 17.8 to 28.2 (+10); the same tier-3 defense loadout takes a rhino's armor from 0.60 to 1.0 but a wolf's from 0.15 to 0.28. (Armor is multiplied from a floor of 0.05, so a fighter with none can still gain a little.)

On top of that each fighter has a **primary attribute**: what it is best at, measured on a fixed scale (attack = force times rate against 1,500 N per second, defense = armor against 0.4, speed against 20 m/s; `PRIMARY_REFERENCE`). The best one counts if it leads the next by 20%; otherwise the fighter is a generalist and the *balanced* loadout is its match. **Enhancing the primary attribute pays extra:** the matching loadout's gains (not its costs) grow by 30% (`PRIMARY_SYNERGY`), so a cheetah's speed loadout and a rhino's armor loadout get even better, while the same loadout on a fighter whose strength lies elsewhere does not.

| Fighter | Attack | Defense | Speed | Primary |
|---|---|---|---|---|
| Cheetah (a test sheet) | 0.47 | 0.12 | 1.45 | **speed** |
| Rhino (a test sheet) | 0.83 | 1.50 | 0.70 | **defense** |
| Gray wolf | 0.59 | 0.37 | 0.89 | speed |
| Horse | 1.92 | 0.37 | 0.67 | attack (its kick) |
| African elephant | 3.43 | 1.12 | 0.35 | attack (its tusks) |
| Roman legionary | 0.10 | 1.50 | 0.40 | defense |
| Honey badger | 0.19 | 0.75 | 0.60 | defense |
| Grizzly bear | 0.75 | 0.75 | 0.67 | generalist (balanced) |

(Scores are each stat against the reference scale, so a score above 1 means well above it. The reference scale is an assumption, like every number here; the machine and crocodile scores are dominated by their huge ram and bite forces.) The note on a changed stat says "primary attribute: speed" when the bonus applied, so the sheet stays honest.

Example, a gray wolf (a land mammal, so light gear) with attack tier 3, "razor claws": attack force 593 N becomes 1,127 N, attacks per second 1.5 becomes 0.96, top speed 17.8 m/s becomes 16.2 m/s. The same loadout on a Roman legionary ("steel battle axe") also costs speed and swing to the weight of iron: speed x0.86 and rate x0.62.

Tests check the design promises: every loadout gains in one stat and loses in another at every tier, with or without the primary bonus; a higher tier is never a strictly better set; no loadout at any tier is at least as good as another in all four stats; and over every kit of up to 6 points, spending one more point never gives a strictly better set. (Without the negative traits, the cross-loadout check fails, so the weight rules are what keep it a real choice.)

## 4. Does it matter? What the simulator says

I ran eight seed fighters (grizzly, elephant, gorilla, crocodile, horse, wolf, legionary and tank) through a sample bracket (arena, 200 runs per match) with everyone on the same loadout and tiering up each round, for all four loadouts. **The bracket was identical every time** (the tank beat the elephant in the final): size gaps between fighters are far bigger than any loadout. (That run used the single-loadout tiers without the weight rules; they would only slow the heavy kits further.)

It moves close fights, and the kind of fighter changes what works. Win share of the fighter with the kit against an unequipped opponent (500 runs; none / attack 3 / defense 1 / defense 5 / speed 4 / balanced 3 / balanced 2 + attack 1 + defense 1):

| Fight | none | attack 3 | defense 1 | defense 5 | speed 4 | balanced 3 | mixed |
|---|---|---|---|---|---|---|---|
| Roman legionary (primary defense) v gray wolf | 9% | 14% | 12% | **6%** | 4% | 21% | **27%** |
| Gray wolf (primary speed) v Roman legionary | 88% | 96% | 91% | **78%** | 86% | 94% | 97% |
| Honey badger (primary defense) v house cat | 91% | 92% | 94% | 89% | 88% | 96% | 97% |
| Horse (primary attack) v saltwater crocodile | 1% | 3% | 1% | 0% | 0% | 1% | 3% |
| Tank v elephant, house cat v wolf and similar | lopsided, unchanged by any kit | | | | | | |

What stands out:
- **Heavy gear hurts, and more for a warrior than an animal.** Full plate (defense 5) makes the legionary worse (9% to 6%) and the wolf worse too (88% to 78%) because the multiplier cuts its speed and swing; at tier 1 or 2 the same defense helps both.
- **A mixed kit is the best result** in every close fight above (27%, 97%, 97%), so each round's choice (add a new loadout or deepen one) is a real decision.
- **The primary-attribute bonus changes the stats a lot but the win share less:** the wolf's speed 4 takes it from 17.8 to over 30 m/s and the bonus applies, yet its win share barely moves (88% to 86%), because the engine rewards speed only a little (`HIT_SPEED_EXP` 0.3). Attack, which the engine rewards most, gives the biggest swings for a fighter of any primary (the wolf's attack 3 is +8 points). If speed and defense loadouts should matter more, the engine's use of speed (a dodge or initiative effect) or the tier scale has to change; that is an engine decision with a version bump, not a loadout constant.
- **Lopsided fights stay lopsided:** the sample bracket never changes, and a tank or elephant is untouched by any kit. With today's assumptions a loadout is a nudge for fights that were already close.

If that is too small, the options are bigger tier scales (which also grow the costs), a bigger primary bonus, giving speed and armor more weight in the engine, or seeding the bracket so early rounds are close. These are assumptions, so changing them is a design call.

## 5. Open questions for Mike

1. Is this in scope for the course project at all (code complete Nov 25), or post-MVP?
2. Is the pre-modern item list the right safety line, or should a few non-firearm machines (a siege engine, a chariot) be allowed? D-38 blocks modern vehicles; the tank is a seed fighter.
3. Entry points and points per win (2 and 1) give a champion four choices. Should a bracket give more, so tiers 4 and 5 matter?
4. Should the user choose every upgrade, or only the first loadout (with automatic tier-ups)?
5. Does a loadout need critical hits to feel different? That is a new mechanic (a seeded draw per attack, parity tests against swarm mode, an `ENGINE_VERSION` bump), so it is left out until you ask for it.
