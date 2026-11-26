# Research plan: seed fighters, stats, and sources

Task G01 (#19). This page decides which fighters we support first, what each stat means, what we do when a number is missing, and which sources we may use. G02, G04, G05, G07, and G09 build on it.

Mythical creatures are not seed fighters; G09 handles them in `data/seed/mythical.yaml`. In a battle, a creature in that file is built from its two analogs. Any other name that isn't a fighter we have is modeled as a legend from its Wikipedia article, in live mode only. The model picks the analogs and abilities, and code checks its quote against the article. If the check fails, the battle stops with a friendly message. When the model answers "not a legend" (found false), it also picks one reason from a fixed list (`real_animal`, `object_or_machine`, `person`, `deity`, `named_character`, `weapon`, `nonsense`, in `prompts/lore_extract.md`), and code decides (#403): `real_animal` and `object_or_machine` mean "a plausible fighter, just not a legend" and the battle falls back to an all-estimate sheet (below); every other reason, a missing reason and an invalid one stay refused, so it fails closed. The model only picks a label and never sets a number. A name with no Wikipedia article is asked about too, with the name alone and a marker in place of the article: found false goes through the same reason check, found true is refused (there is no text to check a quote against), and no reply from the model is an outage. The article lookup tries "<Name> (mythology)" first, then the bare name, because a bare name such as "Hydra" can land on a disambiguation page. The sheet is saved, so later battles reuse it; `uv run --directory backend python scripts/forget_legend.py <name>` removes a bad one (and `--list` shows them), so the next battle models it again. A refused name (the model gave a refusal reason, or its quote or analogs failed code's check) isn't looked up again for 10 minutes, and at most two new legends are looked up at once; an outage is never remembered (#324). Saved legends are never offered as the next challenger or listed in fighter search, because they had no safety check of their own. A seed-list fighter is never modeled as a legend.

**A fighter with no sheet at all (#345).** When a name is not on the seed list, not in `mythical.yaml`, and no legend lookup gives a sheet (in mock mode there is no lookup), the battle still runs on an all-estimate sheet built by code (`backend/app/research/estimate_sheet.py`): every physical stat is the `other` category default and every behavioral stat its rubric assumption, all labeled `is_estimate` with a note saying so. No model sets a number. Code has no signal for what kind of thing the fighter is, except one: in live mode the legend lookup gives a fixed reason when it says a name is not a legend (#403). **`real_animal` gives a living land mammal with a bite** (the mammal defaults, `teeth` as its weapon: 50 kg, 500 N, 12 m/s; every stat still a labeled estimate), so "a moose" or "a tiger" fights back (#453). Everything else, an object or machine (`object_or_machine`), a name with no reason, and mock mode, fights like an object (inert, on land, no weapon). **A `generic_kind` reason (#444)**, a generic type of human or supernatural being such as a priest, a monk, "a god" or an angel (never a named individual), also gives a living fighter, built from the human archetype defaults (70 kg, 1.75 m, 8 m/s). The generic supernatural kinds D-65 allows (god, goddess, angel, demon, titan, valkyrie, and their plurals) skip the lookup: their article is about one named figure, so the model would answer `deity`, and code calls them `generic_kind` itself (`GENERIC_SUPERNATURAL_KINDS` in `lore.py`), in mock mode too. A capitalized "God" is a named deity and is stopped by the safety gate at intake. **D-69 adds two reasons:** `armed_unit` (a military or police unit, such as a Navy SEAL) gives a living human archetype with a firearm, a `weapon_ranged` attack whose reach, force and rate are the labeled estimates in `FIREARM_STATS` (`estimate_sheet.py`); `myth_deity` (a god of mythology, such as Zeus) fights like a generic kind. Common military types skip the lookup the same way (`MILITARY_KINDS` in `lore.py`: "navy seal", "green beret", "marine" and so on), because their article is about one real unit. A weapon on its own is `object_or_machine`, an inert object. The lookup's `weapon` reason is only a firearm, an explosive or a weapon of mass destruction (D-38); a sword, a bow or a vehicle is an `object_or_machine`. Named people, human religious figures (the Pope, a prophet, a saint), named deities (Zeus, Thor) and named characters are still refused. The reason is a membership check against a fixed list: no model text or number reaches the sheet, and the 10-minute "not a legend" memory keeps the reason, so a repeat gets the same fighter. Research ends "fallback" with a note such as "We have no stat sheet for 'wolverine', so its stats are estimates." The sheet is not saved to the sheet store. A blocked or refused legend, a legend lookup that is down, and a seed-list fighter whose build failed still stop the battle with their friendly message. In live mode the same path runs for an ordinary real name such as "a wolverine" or "a forklift" (#403): the legend lookup answers "not a legend" with a harmless reason (also when there is no article), so the battle fights on estimates. A refusal is remembered for 10 minutes, and so is "not a legend" (in its own table, #445), so the same unknown name is not looked up again within the window; an outage is never remembered.

## Seed fighters

30 fighters: 25 animals and human archetypes, and 5 objects and machines. "Article" is the English Wikipedia title that resolves directly, with no redirect or disambiguation page (checked 2026-11-09).

**Which ones have a hand-verified sheet (#623).** 16 of the 30: the 15 built for G05, plus the great white shark. A seed fighter with no sheet fights in mock mode on its category defaults (before its sheet, the shark weighed 10 kg). The other 14 are listed in `STILL_TO_BUILD` in `backend/tests/unit/test_seed_sheets.py`. That test fails if a seed fighter has neither a sheet nor a place on the list, and if a listed fighter's sheet lands without it being taken off the list.

| # | Slug | Display name | Default variant | Category | Body | Habitat | Article |
|---|---|---|---|---|---|---|---|
| 1 | `grizzly-bear` | Grizzly bear | Adult male | mammal | living | land | Grizzly bear |
| 2 | `gray-wolf` | Gray wolf | Adult male | mammal | living | land | Wolf |
| 3 | `african-lion` | African lion | Adult male | mammal | living | land | Lion |
| 4 | `house-cat` | House cat | Adult domestic cat | mammal | living | land | Cat |
| 5 | `golden-retriever` | Golden retriever | Adult male | mammal | living | land | Golden Retriever |
| 6 | `african-elephant` | African elephant | Adult bull, savanna | mammal | living | land | African elephant |
| 7 | `horse` | Horse | Adult domestic riding horse | mammal | living | land | Horse |
| 8 | `hippopotamus` | Hippopotamus | Adult male, common hippo | mammal | living | amphibious | Hippopotamus |
| 9 | `chimpanzee` | Chimpanzee | Adult male, common chimpanzee | mammal | living | land | Chimpanzee |
| 10 | `gorilla` | Gorilla | Adult male, western lowland | mammal | living | land | Gorilla |
| 11 | `honey-badger` | Honey badger | Adult male | mammal | living | land | Honey badger |
| 12 | `house-mouse` | House mouse | Adult | mammal | living | land | House mouse |
| 13 | `bald-eagle` | Bald eagle | Adult female | bird | living | air | Bald eagle |
| 14 | `duck` | Duck | Adult mallard | bird | living | amphibious | Mallard |
| 15 | `goose` | Goose | Adult Canada goose | bird | living | amphibious | Canada goose |
| 16 | `saltwater-crocodile` | Saltwater crocodile | Adult male | reptile | living | amphibious | Saltwater crocodile |
| 17 | `king-cobra` | King cobra | Adult | reptile | living | land | King cobra |
| 18 | `great-white-shark` | Great white shark | Adult female | fish | living | water | Great white shark |
| 19 | `army-ant` | Army ant | *Eciton burchellii* worker | insect | living | land | Army ant |
| 20 | `honey-bee` | Honey bee | Western honey bee worker | insect | living | air | Western honey bee |
| 21 | `tyrannosaurus-rex` | Tyrannosaurus rex | Adult | dinosaur | living | land | Tyrannosaurus |
| 22 | `triceratops` | Triceratops | Adult | dinosaur | living | land | Triceratops |
| 23 | `roman-legionary` | Roman legionary | Imperial era, sword and shield | human_archetype | living | land | Legionary |
| 24 | `medieval-knight` | Medieval knight | Plate armor, on foot | human_archetype | living | land | Knight |
| 25 | `samurai` | Samurai | Armored, on foot | human_archetype | living | land | Samurai |
| 26 | `main-battle-tank` | Main battle tank | Generic modern tank, ramming and crushing only | vehicle | machine | land | Main battle tank |
| 27 | `bulldozer` | Bulldozer | Medium crawler | vehicle | machine | land | Bulldozer |
| 28 | `pickup-truck` | Pickup truck | Full-size | vehicle | machine | land | Pickup truck |
| 29 | `toaster` | Toaster | Two-slice household toaster | object | inert | land | Toaster |
| 30 | `saguaro-cactus` | Saguaro cactus | Mature plant | plant | inert | land | Saguaro |

Notes:

- The five showcase battles (PRODUCT_SPEC §9) use horse, duck, grizzly bear, gray wolf, honey badger, king cobra, Roman legionary, gorilla, and main battle tank. The showcase dragon is built by G09 from saltwater crocodile and African elephant.
- `Gray wolf` and `Roman legionary` are redirects on Wikipedia, so the table lists the pages they lead to.
- Ducks and geese are `amphibious` so they can be reached on water. This has a real cost on dry ground: in the engine's terrain table (PR #68), an amphibious fighter gets about ×0.8 speed, ×0.9 attack, and ×0.9 hit chance on arena, open field, forest, and urban terrain, and a little worse on mountains, so it affects the 100-duck showcase battle. The engine treats `air` and strictly `water` fighters as unable to reach each other in open water.
- The Legionary, Knight, and Samurai articles describe the role more than the body. Expect body numbers for these three to come from category defaults unless G05 finds a better source.
- Army ant is the page for the whole group, but the default variant is *Eciton burchellii*. Its mass and size need a species-level source, not the group article.

## Fighter IDs

- The default variant uses the plain slug: `grizzly-bear`.
- Any other variant adds two hyphens and the variant, in lowercase with hyphens for spaces: `grizzly-bear--juvenile`, or "Adult female" as `grizzly-bear--adult-female`.
- File names, the benchmark, and every table keyed by fighter use this ID.

## Default variants

When a user names a kind of fighter without saying which one, we pick:

| User says | We use |
|---|---|
| bear | `grizzly-bear` |
| shark | `great-white-shark` |
| wolf | `gray-wolf` |
| eagle | `bald-eagle` |
| cat | `house-cat` |
| dog | `golden-retriever` |
| elephant | `african-elephant` |
| crocodile | `saltwater-crocodile` |
| snake | `king-cobra` |
| bee | `honey-bee` |
| ant | `army-ant` |
| mouse | `house-mouse` |
| tank | `main-battle-tank` |
| truck | `pickup-truck` |
| cactus | `saguaro-cactus` |
| lion | `african-lion` |
| badger | `honey-badger` |
| knight | `medieval-knight` |
| legionary | `roman-legionary` |
| retriever | `golden-retriever` |

The rules behind the table:

1. What the user says wins: "polar bear" or "wolf pup" is not replaced by a default.
2. Otherwise use the most familiar member of that group that is on the seed list.
3. Use a healthy adult. Where one sex is clearly larger, use that sex, because it is the size most sources report.

Code applies this table, never a model: `DEFAULT_KINDS` in `backend/app/research/seed_fighters.py` copies it, and a test keeps the two identical. A bare kind (or its plural, such as "bears") becomes its default only when nothing more exact was given: an exact name, a kind ("polar bear"), or raw words that name a seed fighter ("6 gray wolves") always win. The battle's assumptions name the pick, for example "Not sure which bear, so we used the grizzly bear." (#168).

Two details of the lookup (#415):

- **The user's own words count.** Only articles, numbers, group words ("a pack of", "a bunch of"), size words ("big", "small") and plain adjectives or possessives ("fierce", "adult", "my"; the full, closed list is `_FILLER_WORDS` in `seed_fighters.py`) may stand around a bare kind. "A bear", "6 bears", "a big bear" and "my fierce bear" get the grizzly and the note. "A polar bear" gets no default and no "Not sure which" note, even when the model reads it as the entity "bear" with no variant; it is then an unknown fighter, like any other name that is not on the seed list. A trailing place phrase ("in a forest", "on the ice") and a possessive "'s" are ignored, since they name no kind. Intake keeps the user's word as the variant (`named_kind_words`: "polar" for "a polar bear" or "a polar bear on the ice"), so the fighter reads "polar bear", not a bare "bear", in the estimate sheet and the battle text. A word that is not on the list counts as naming a kind; add one when a plain word turns up.
- **Common names reach their seed fighter.** Besides the spellings in `_ALIASES` (grey, wolves, ducks, mice, cacti), `_NAME_ALIASES` maps a whole common name: hippo and hippos to `hippopotamus`; cobra and cobras to `king-cobra`; t-rex, t rex, T. Rex, trex and tyrannosaurus to `tyrannosaurus-rex`. These are matched as the whole name, so the full "king cobra" still works. Add a name there when a user's usual word is not the seed fighter's name or id.

## The seven physical stats

These are sourced or labeled estimates. For each one we use the first of these that exists: a hand-verified seed sheet, a Wikidata fact, a number extracted with a verified quote, a value derived by code (the note names the formula), then the category default.

| Stat | What it means | Unit | Where it usually appears | If it is missing |
|---|---|---|---|---|
| `mass_kg` | Typical body weight, or vehicle or object weight | kg | Wikidata P2067; PanTHERIA `5-1_AdultBodyMass_g`; AnimalTraits body mass; Wikipedia article text | Category default |
| `size_m` | Longest body dimension: head-and-body length, or height if the fighter is taller than it is long. If a source gives only shoulder height, use that and say so in the `note` | m | Wikidata P2043 (length), P2048 (height); PanTHERIA `13-1_AdultHeadBodyLen_mm`; Wikipedia article text | Derived from mass if a formula applies, else category default |
| `top_speed_mps` | Fastest sustained movement on its home ground | m/s | Wikidata P2052; Wikipedia article text, usually in km/h or mph | Category default |
| `attack_force_n` | Force of one bite, strike, or blow | N | Wikipedia article text or the paper it cites (bite force is reported for some species) | Derived from other stats if a formula applies, else category default |
| `attacks_per_s` | Attacks per second in a fight | per second | Rarely published; occasional behavior studies | Category default. Ramming and crushing machines use the engine's own rate (see below) |
| `reach_m` | How far from its body it can land an attack | m | Rarely stated directly; a published horn, tusk, weapon, or arm length counts as reach (`hand_verified`, D-53). An arm span alone doesn't: half a span includes half the shoulder width, and halving by hand isn't `derived` | Derived as `0.25 × size_m` (a lunging bite) when nothing better is published, else category default |
| `endurance_s` | How long it can keep fighting. For a machine, its operating time before it stops | s | Rarely stated for animals. For vehicles, range and speed in article text | Vehicles: derived as range divided by speed, with the range extracted using a verified quote and cited in the `note`; if there is no quote, category default. Others: category default |

Every value gets a `low` and `high`: the source's range if it gives one, otherwise ±10% (high confidence), ±25% (medium), or ±50% (low, which includes all estimates and assumptions). When a source states a mean or typical figure, that figure is the `value`, and `low` and `high` keep the range. If it gives only a range, the `value` is one of the quoted figures, usually the upper one, and the `note` says which.

**Labeling rules (D-47).**
- `derived` means code computes the value from other values. A hand-worked formula doesn't count: the honey badger's bite from Wroe's 31-species regression counts as `derived` only once the fit runs in code, and the horse's gallop distance ÷ top speed is not `derived`, so its endurance stays a category default.
- A number taken from another page as a stand-in, such as the elephant's trunk lift used as blow force, is `hand_verified`, with its quote in `source`.
- A chase or pursuit figure isn't fighting endurance. Use the category default and keep the quote in the `note`.

**G05's estimate limit.** No seed sheet may have more than 2 of its 7 physical stats as estimates. Every `category_default` counts, and `derived` values don't. There are five exceptions, by PM decision, each estimate labeled in its `note`: the duck and the honey badger may have 3 (PR 139), the king cobra 4 and the Roman legionary 3 (D-54, #29), and the house cat 3 (D-55, #29). The list is closed; every other sheet stays at 2 or fewer.

**Machines that ram or crush.** The engine computes their damage from mass and speed and uses a fixed attack rate (task F08), but the stat sheet still requires `attack_force_n` and `attacks_per_s`, and neither may be an `assumption` on a non-mythical fighter. Mark both `derived` and store:

- `attack_force_n`: the force that gives the engine's ramming damage, `RAM_DAMAGE_PER_MOMENTUM × mass × speed ÷ DAMAGE_PER_NEWTON`, using the sheet's own mass and speed. For a fighter with `crushing`, use a speed of at least `CRUSH_MIN_SPEED_MPS`.
- `attacks_per_s`: the value of `RAM_ATTACKS_PER_S`.

The `note` names the formula or constant and says the engine works out the real hit from them. `RAM_DAMAGE_PER_MOMENTUM`, `RAM_ATTACKS_PER_S`, and `CRUSH_MIN_SPEED_MPS` are in `backend/app/simulation/constants.py`. Derived ram/crush values do not count toward G05's limit of 2 estimates.

## Category defaults

Used only when no evidence is found (`method: category_default`, `is_estimate: true`, confidence low). **These are round starting values chosen by judgment, not sourced numbers.** They only have to be plausible for a typical member of the category; G04 stores them in `backend/app/research/defaults.py`.

| Category | Mass (kg) | Size (m) | Speed (m/s) | Force (N) | Attacks per s | Reach (m) | Endurance (s) |
|---|---|---|---|---|---|---|---|
| mammal | 50 | 1.2 | 12 | 500 | 1.5 | 0.4 | 300 |
| bird | 2 | 0.5 | 18 | 30 | 2 | 0.15 | 300 |
| reptile | 20 | 1.5 | 4 | 300 | 1 | 0.3 | 120 |
| amphibian | 0.2 | 0.12 | 1 | 2 | 1 | 0.03 | 60 |
| fish | 10 | 0.8 | 6 | 150 | 1 | 0.2 | 300 |
| insect | 0.0001 | 0.01 | 0.5 | 0.01 | 3 | 0.003 | 600 |
| arachnid | 0.002 | 0.02 | 0.5 | 0.05 | 2 | 0.005 | 300 |
| mollusk | 0.2 | 0.2 | 0.2 | 2 | 0.5 | 0.05 | 600 |
| dinosaur | 1000 | 5 | 8 | 5000 | 0.8 | 1.2 | 180 |
| human_archetype | 70 | 1.75 | 8 | 400 | 1 | 1 | 600 |
| vehicle | 3000 | 5 | 25 | derived (see machines note) | derived (see machines note) | 1 | 3600 |
| machine | 1000 | 3 | 5 | derived (see machines note) | derived (see machines note) | 1 | 3600 |
| plant | 50 | 3 | 0 | 0 | 0 | 0 | 600 |
| object, other | 1 | 0.3 | 0 | 0 | 0 | 0 | 600 |

Objects and plants last the full 600-second fight limit and cannot attack unless their sheet says otherwise (a saguaro has `spines`).

**Unlisted animals researched at battle time (#518).** In live mode, a fighter the legend lookup calls a `real_animal` doesn't stop at its estimate sheet (`backend/app/research/on_demand.py`). The article is the fighter's name as typed. "An adult moose" is researched like "a moose", since the article describes adults; any other variant ("a baby moose", "an adult male lion") is not, since the adult's article would give it the wrong numbers (#535). An article without an animal taxobox (a disambiguation page, a band) gives nothing, so a name that lands on the wrong page never lends it its numbers. Otherwise code stores the animal's Wikidata measurements (mass, length, height, speed) as facts, as for seed fighters; reads the article's taxobox "Class:" row (Aves is a bird, Reptilia a reptile, and so on), so the animal kind comes from the article rather than the lookup's label (a flier stays a flier, #542); stores the article's passages (`ingest_on_demand`, reusing the same download, so the article is fetched once per build, #535); and runs the seed fighters' extraction with its quote check (`build_sheet_with_evidence`). Every stat that comes back sourced (a Wikidata fact or a checked quote) replaces the estimate's value; every other stat stays the labeled estimate, size class included. A stat code derives from others is worked out again once its inputs are sourced: a sourced size gives reach = 0.25 × size, labeled `derived` (#535). While any input is still an estimate, that stat stays the labeled estimate. So a sheet can mix a sourced mass with an attack force scaled from the size class's weight; both are labeled. The battle waits at most `ON_DEMAND_RESEARCH_S` (20 s), and never past the research stage's 45 s less `RESEARCH_MARGIN_S` (3 s), since the legend lookup before it can take up to 30 s; a slower build fights this battle on estimates, carries on in the background (up to `BUILD_LIMIT_S`, 90 s) and is cached for the next battle. A build with no sourced stat is not retried for 10 minutes and nothing is cached (a better animal kind from the taxobox is still used for that one battle). Researched sheets had no safety check of their own, so, like legends, they are never listed in fighter search or offered as the next challenger: both only show seed-list fighters. Objects, people and gods are not researched (their estimates don't depend on measurements), and mock mode is unchanged.

**Unlisted fighters: animal kind and size class (#517).** An estimate sheet for a name off the seed list starts from these defaults. When the legend lookup says it is a `real_animal`, it also picks the animal's kind from a fixed list (`ANIMAL_CATEGORIES` in `lore.py`), so an ostrich gets the bird defaults and a beak and a shark lives in water (`ANIMAL_KINDS` in `estimate_sheet.py`: mammal, reptile and fish bite, a bird and a mollusk peck, an insect and an arachnid sting; a fish and a mollusk live in water, an amphibian on land and in water). For a living animal, generic kind, god of mythology, or object or machine (#562) it also picks a size class. A size class means the same weight for every kind (`SIZE_MASSES`), because the prompt defines it by everyday size, not "big for a bird". Code scales the kind's defaults to that weight, with length and reach by the cube root of the mass factor and attack force by its two-thirds power (square-cube, as for legends). A kind whose own default already falls in the class's band keeps it: the band runs to the geometric midpoint with each neighboring class, so a medium mammal stays 50 kg, a medium person 70 kg and a tiny fly its 0.1 g default. Speed is not scaled. Soldiers (`armed_unit`) stay human-sized. An object or machine is sized the same way but stays inert (D-38): a "huge" school bus is 5,000 kg and about 5 m long instead of the 1 kg, 0.3 m `other` default (#562). An object the lookup gives no size class keeps that default, and its mass and size notes say it is a stand-in ("Stand-in: we couldn't tell how big this is, so it uses a placeholder size."), so a 1 kg bus never decides a fight silently. For a `real_animal` the lookup also says whether a typical adult **flies** (`true` or `false`, #542): one that flies (a hawk, a bat, a wasp) moves by `air`, so it gets the air rules on every battlefield and can fight in the sky (D-70); one that doesn't (an ostrich, a penguin) keeps its kind's habitat. Anything but a plain yes or no is ignored. A missing or unknown label means the medium mammal, as before. The model only picks words; every number comes from these tables, and every stat stays a labeled estimate. **The weights are judgment values, not sourced:**

| Size class | Weight | Band kept as is | For example |
|---|---|---|---|
| tiny (mouse-sized or smaller) | 0.05 kg | under 0.35 kg | a field mouse 0.05 kg; a tarantula keeps the arachnid 2 g, a fly the insect 0.1 g, a frog the amphibian 0.2 kg |
| small (cat-sized) | 2.5 kg | 0.35 to 11 kg | a house cat 2.5 kg; a hawk keeps the bird 2 kg, a pike the fish 10 kg |
| medium (person-sized) | 50 kg | 11 to 160 kg | an ostrich 50 kg (not the bird 2 kg); a wolf keeps the mammal 50 kg, a cobra the reptile 20 kg, a priest the human 70 kg |
| large (horse- or bear-sized) | 500 kg | 160 to 1,600 kg | a moose, a crocodile or a tuna 500 kg |
| huge (elephant-sized or bigger) | 5,000 kg | 1,600 kg and up | an elephant, a whale shark or a titan 5,000 kg |

## The three behavioral stats

No source measures these, so they are `assumption` values set from the rubrics below. Every `note` uses the same pattern, `<stat> level <N or M>: <reason>`, where the stat is `aggression`, `group tactics`, `armor`, or `durability`. For example: `aggression level 4: territorial apex predator`. Pick the level first; the value follows from it.

### Aggression (`aggression_0_1`)

The engine makes a side retreat once it has lost `0.2 + 0.8 × aggression` of its total hit points.

| Level | Value | Description | Example |
|---|---|---|---|
| 0 | 0.0 | Inanimate: objects and plants | Toaster (not an animal) |
| 1 | 0.1 | Flees from almost everything | House mouse |
| 2 | 0.3 | Flees first, fights when cornered | Horse |
| 3 | 0.5 | Hunts or defends itself, avoids risky fights | Gray wolf |
| 4 | 0.7 | Territorial, confident against most animals | Grizzly bear |
| 5 | 0.9 | Attacks animals larger than itself | Honey badger |
| M | 1.0 | Operated to win: a machine with a driver | Main battle tank (not an animal) |

### Group tactics (`group_tactics_0_1`)

When two or more attackers share a target, hit chance rises by up to `group_tactics × 0.5`.

| Level | Value | Description | Example |
|---|---|---|---|
| 0 | 0.0 | Inanimate: objects and plants | Toaster (not an animal) |
| 1 | 0.1 | Solitary: fights alone | Grizzly bear |
| 2 | 0.3 | Gathers in groups, but each acts alone | Mallard duck |
| 3 | 0.5 | Family or herd that defends together | African elephant |
| 4 | 0.8 | Pack that hunts in coordination | Gray wolf |
| 5 | 1.0 | Colony or drilled unit acting as one | Army ant; a Roman legion |

### Armor (`armor_0_1`), living fighters

How much of a blow the body turns aside.

| Level | Value | Description | Example |
|---|---|---|---|
| 1 | 0.15 | Fur, feathers, or bare skin | Gray wolf |
| 2 | 0.3 | Thick fur, fat, or loose tough skin | Grizzly bear |
| 3 | 0.45 | Very thick hide | African elephant |
| 4 | 0.6 | Bony plates in the skin, or metal body armor | Saltwater crocodile |
| 5 | 0.8 | A full hard shell, or full plate | Aldabra giant tortoise; a knight in plate |

### Durability (`armor_0_1`), machines, objects, and plants

Machines, objects, and plants use this scale instead, and the `note` says `durability level`. It has no animal examples because it only applies to non-living fighters.

| Level | Value | Description | Example |
|---|---|---|---|
| 1 | 0.1 | Brittle: shatters easily | Glass vase |
| 2 | 0.4 | Thin sheet metal, or a tough plant | Toaster |
| 3 | 0.55 | Ordinary vehicle body | Pickup truck |
| 4 | 0.7 | Heavy steel construction | Bulldozer |
| 5 | 0.8 | Tank armor | Main battle tank |

### Default level by category

G04 uses these when there is no hand-verified sheet. Mythical creatures are excluded because G09 copies theirs from their analogs.

| Category | Aggression | Group tactics | Armor or durability |
|---|---|---|---|
| mammal | 3 | 2 | Armor 1 |
| bird | 2 | 2 | Armor 1 |
| reptile | 3 | 1 | Armor 3 |
| amphibian | 1 | 1 | Armor 1 |
| fish | 3 | 2 | Armor 2 |
| insect | 3 | 3 | Armor 2 |
| arachnid | 3 | 1 | Armor 2 |
| mollusk | 2 | 1 | Armor 3 |
| dinosaur | 4 | 2 | Armor 3 |
| human_archetype | 4 | 4 | Armor 4 |
| vehicle | M | 2 | Durability 3 |
| machine | M | 2 | Durability 3 |
| plant, object, other | 0 | 0 | Durability 2 |

## Source policy

The sources approved in DECISIONS D-20. Licenses were checked against each source's own page on 2026-11-09.

| Source | What we take | License | How we attribute it |
|---|---|---|---|
| **Wikipedia Structured Contents** (`wikimedia/structured-wikipedia`, Hugging Face) | Abstracts, sections, and parsed infoboxes, looked up per fighter through the Dataset Viewer API. Never the whole dataset | CC BY-SA 4.0 | Article title and link with the license, on the results page |
| **Wikipedia REST API** (same text as above) | Article HTML for the seed fighters, because it is faster | CC BY-SA 4.0 | Same as above |
| **FineWiki** (`HuggingFaceFW/finewiki`, Hugging Face) | Backup article text and infobox JSON when the first source lacks an article or is stale | CC BY-SA 4.0 (source text also under GFDL) | Same as above, naming Wikipedia |
| **Wikidata** (live API) | Mass, length, height, and speed with property IDs and references; the "is this a real human?" check | CC0 | Entity link and property ID. Set `license` to `CC0 1.0` on these values |
| **PanTHERIA** (Ecological Archives E090-184) | Adult body mass and head-body length for mammals | No copyright restrictions, per its metadata page; the authors ask to be cited | Cite Jones et al. 2009, *Ecology* 90:2648 |
| **AnimalTraits** (animaltraits.org) | Body mass, including arthropods, reptiles, and birds | CC0 for the database; the paper is CC BY | Cite Herberstein et al. 2022, *Scientific Data* 9:265, and the original source the database names |
| **Team trait dataset** (`MBAX6418Bros/battle-royale-seed-traits`, Hugging Face) | The PanTHERIA and AnimalTraits rows for the seed fighters only (`data/seed/seed-traits.csv`, built by `backend/scripts/build_seed_traits.py`). The seed ingest downloads it first and falls back to the two original files | Each row keeps its original dataset's license (above) | Each fact keeps its original source and reference, plus "via" the dataset's file link |
| **Wroe, McHenry and Thomason 2005** (*Proc. R. Soc. B* 272:619, Table 1) | Canine bite force: one data row per animal on hand-verified sheets, and the full 31 living-species rows in `backend/app/research/bite_force.py` to fit bite force against body mass | Publisher copyright, not an open license; approved by the PM for these uses (D-47, PR 148) | Cite the paper and link its PMC page. Set `license` to say it is not openly licensed |
| **Pennycuick, Åkesson and Hedenström 2013** (*J. R. Soc. Interface*, PMC3730693, Table 1) | Mean body mass and airspeed of migrating birds | CC BY 3.0 | Cite the paper and link its PMC page |
| **von Wachenfelt, Nilsson and Ventorp 2011** (SLU report 2011:20, *Säkra häststall*) | Horse kick force, one attributed sentence from the English conclusions | No license stated; approved by the PM for one short, attributed sentence (PR 148) | Cite the report and link its permanent page, https://res.slu.se/id/publ/34072 |
| **IFAW, "9 mammals, sharks, and reptiles with the strongest bite"** (ifaw.org) | **No longer used for a value (#260):** the gorilla's bite is now the code's carnivore fit, and Eng et al. 2013 is named in its note only as context. Before that: gorilla bite force, one attributed sentence. It is second-hand: IFAW quotes a modeled maximum molar bite from Eng, Lieberman, Zink and Peters 2013, *Am. J. Phys. Anthropol.* 151:544, whose PDF could not be opened | Publisher copyright, not an open license; approved by the PM for one sentence, with low confidence and a ±50% range (PR 208) | Cite the IFAW page and name Eng et al. 2013 in the note. Set `license` to say it is not openly licensed. Replace with the paper's own wording once someone can open it |
| **Rosenbaum, Vecellio and Stoinski 2016** (*Sci. Rep.* 6:37018) | How long one mountain gorilla group attack lasted, as a low-confidence stand-in for gorilla endurance | CC BY 4.0; approved by the PM (PR 208) | Cite the paper and link the authors' accepted manuscript on NSF's public access site |
| **Nolan, Hainsworth and Rutty 2017** (*Int. J. Legal Med.* 132:229, doi:10.1007/s00414-017-1702-7) | Mean peak force of an unrestrained stab by a man's dominant hand (about 150 N), as a stand-in for a gladius thrust | CC BY 4.0; approved by the PM (#29) | Cite the paper and link its DOI |
| **Różycka, Skibniewska, Rajkowski, Skibniewski and Youlatos 2024** (*Animals* 14(9):1367, doi:10.3390/ani14091367) | Domestic-cat canine bite force (219 N, the upper figure of "around 219–126 N on canines"), one attributed value for the house cat | CC BY 4.0, confirmed on the publisher's page; approved by the PM (D-55) | Cite the paper and link its DOI |
| **TreeOfLife-10M taxonomy metadata** (`imageomics/TreeOfLife-10M`, optional) | Common name to scientific name and class, for matching names. The taxonomy CSV only, never the images | CC0 for the compilation; images vary, and we do not use them | Dataset name and link |

**Hugging Face in the ingest (G02).** The seed ingest loads its trait rows through Hugging Face, from the team trait dataset above. The Dataset Viewer lookup in `wikimedia/structured-wikipedia` was tried first, on 2026-11-13, and wasn't dependable enough: for the grizzly bear it answered "the dataset index is loading" after 36 s, then "authentication check timed out" twice, with no rows. Article text still comes from the Wikipedia REST API. To refresh the team dataset, run the seed ingest, then `uv run python -m scripts.build_seed_traits`, upload `data/seed/seed-traits.csv` to the dataset, and put the dataset's new commit id in `HF_TRAITS_REVISION` in `backend/app/research/traits.py`. The ingest reads that fixed version, so the numbers can only change through a reviewed code change. `HF_TOKEN` in `.env` is optional, because the dataset is public.

**Re-parsing stored articles (#380).** The seed ingest skips an article already stored at the same revision, so a parser fix doesn't reach it on its own. After a fix such as #34's check that puts back paragraphs the parser skipped, run `npm run ingest -- --refresh` (or `uv run --directory backend python -m scripts.ingest_seed --refresh --only <ids>`) to parse the stored articles again; storing replaces their passages and vectors. An unknown id in `--only` stops the run before anything is ingested.

**Matching trait rows by scientific name (#290).** The ingest matches PanTHERIA and AnimalTraits rows by the fighter's scientific name. A name pinned as `scientific_name` in `data/seed/fighters.yaml` comes first; Wikidata's taxon name (P225) is the fallback. A Wikidata name that isn't shaped like a species name (a capitalized genus, then a lowercase species, and at most a subspecies) is ignored for matching and logged, so vandalism such as "Spoderman" on the honey bee can't drop its rows. Every species in the team trait dataset has a pinned name; pin one for any new seed fighter whose trait rows should always match.

**Not allowed:**

- Forums and fan wikis
- AI-generated pages
- Any dataset whose card says values were generated with AI or have no sources, such as `pcwoods/2026-animaldescription-text-dataset`
- Kaggle-style "animal facts" tables with no traceable source

Speed, bite force, and armor rarely appear in trait databases. They come from Wikipedia text through the verified-quote extractor, or from labeled estimates in code.

Rules for fetching: never download or stream a full Wikipedia dump, send a descriptive User-Agent with the project name and no personal email, and keep raw downloads in `data/kb/`, which is not committed.
