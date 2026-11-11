# Research plan: seed fighters, stats, and sources

Task G01 (#19). This page decides which fighters we support first, what each stat means, what we do when a number is missing, and which sources we may use. G02, G04, G05, G07, and G09 build on it.

Mythical creatures are not seed fighters; G09 handles them in `data/seed/mythical.yaml`.

## Seed fighters

30 fighters: 25 animals and human archetypes, and 5 objects and machines. "Article" is the English Wikipedia title that resolves directly, with no redirect or disambiguation page (checked 2026-11-09).

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

The rules behind the table:

1. What the user says wins: "polar bear" or "wolf pup" is not replaced by a default.
2. Otherwise use the most familiar member of that group that is on the seed list.
3. Use a healthy adult. Where one sex is clearly larger, use that sex, because it is the size most sources report.

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

**G05's estimate limit.** No seed sheet may have more than 2 of its 7 physical stats as estimates. Every `category_default` counts, and `derived` values don't. The one exception, by PM decision on PR 139, is the duck and the honey badger, which may have 3 estimates, each labeled in its `note`.

**Machines that ram or crush.** The engine computes their damage from mass and speed and uses a fixed attack rate (task F08), but the stat sheet still requires `attack_force_n` and `attacks_per_s`, and neither may be an `assumption` on a non-mythical fighter. Mark both `derived` and store:

- `attack_force_n`: the force that gives the engine's ramming damage, `RAM_DAMAGE_PER_MOMENTUM × mass × speed ÷ DAMAGE_PER_NEWTON`, using the sheet's own mass and speed. For a fighter with `crushing`, use a speed of at least `CRUSH_MIN_SPEED_MPS`.
- `attacks_per_s`: the value of `RAM_ATTACKS_PER_S`.

The `note` names the formula or constant and says the engine works out the real hit from them. `RAM_DAMAGE_PER_MOMENTUM`, `RAM_ATTACKS_PER_S`, and `CRUSH_MIN_SPEED_MPS` are defined in PR #71 and are not on `main` yet. Derived ram/crush values do not count toward G05's limit of 2 estimates.

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
| **Wroe, McHenry and Thomason 2005** (*Proc. R. Soc. B* 272:619, Table 1) | Canine bite force: one data row per animal on hand-verified sheets, and the full 31 living-species rows in `backend/app/research/bite_force.py` to fit bite force against body mass | Publisher copyright, not an open license; approved by the PM for these uses (D-47, PR 148) | Cite the paper and link its PMC page. Set `license` to say it is not openly licensed |
| **Pennycuick, Åkesson and Hedenström 2013** (*J. R. Soc. Interface*, PMC3730693, Table 1) | Mean body mass and airspeed of migrating birds | CC BY 3.0 | Cite the paper and link its PMC page |
| **von Wachenfelt, Nilsson and Ventorp 2011** (SLU report 2011:20, *Säkra häststall*) | Horse kick force, one attributed sentence from the English conclusions | No license stated; approved by the PM for one short, attributed sentence (PR 148) | Cite the report and link its permanent page, https://res.slu.se/id/publ/34072 |
| **TreeOfLife-10M taxonomy metadata** (`imageomics/TreeOfLife-10M`, optional) | Common name to scientific name and class, for matching names. The taxonomy CSV only, never the images | CC0 for the compilation; images vary, and we do not use them | Dataset name and link |

**Not allowed:**

- Forums and fan wikis
- AI-generated pages
- Any dataset whose card says values were generated with AI or have no sources, such as `pcwoods/2026-animaldescription-text-dataset`
- Kaggle-style "animal facts" tables with no traceable source

Speed, bite force, and armor rarely appear in trait databases. They come from Wikipedia text through the verified-quote extractor, or from labeled estimates in code.

Rules for fetching: never download or stream a full Wikipedia dump, send a descriptive User-Agent with the project name and no personal email, and keep raw downloads in `data/kb/`, which is not committed.
