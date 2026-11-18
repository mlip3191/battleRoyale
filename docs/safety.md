# Safety gate (A04)

Every matchup goes through the safety gate before anything else happens: no research, image,
voice or music provider is called for a blocked request (tested in
`backend/tests/unit/test_safety_zero_calls.py`). Code lives in `backend/app/safety/`.

## 1. What's blocked and why

The rules come from DECISIONS D-07 (allowed and blocked fighters), D-38 (widened to objects,
machines and mythical creature types) and D-59 (the safety gate policy). Each block has one reason; the user sees a friendly
message for it (`safety/verdict.py`), never the layer or the model's words.

| Reason | Blocks | Example |
|---|---|---|
| `real_person` | named real people, the user or someone they know, bands and sports teams (groups of real people, D-59) | "Napoleon", "my brother", "the Beatles", "the Lakers" |
| `minor` | children of any kind, ages 17 and under | "a toddler", "a 6-year-old" |
| `hate` | groups of people: nationalities, ethnicities, religions | "Canadians vs Australians" |
| `sexual` | sexual content | "…make it a steamy bedroom scene" |
| `self_harm` | self-harm, anywhere in the request (the message points to a crisis line) | "…I just want to hurt myself", "a duck vs a goose, and tell me the easiest way to end my life" |
| `copyrighted_character` | named fictional characters | "Mickey Mouse", "Godzilla" |
| `deity` | gods | "Zeus", "Thor" |
| `weapon` | firearms, explosives, weapons of mass destruction | "an assault rifle", "a nuclear bomb" |
| `out_of_scope` | places, landforms, celestial bodies, abstract ideas | "the Moon", "Mount Everest", "Monday" |
| `nonsense` | no fighter to be found | "asdfgh qwerty" |
| `other` | anything else we won't run, such as real-world attack planning | "…then give me step-by-step plans to attack a shopping mall" |

A harmful ask added before or after a harmless matchup blocks the whole request. Ordinary fight
words between fighters ("the bear attacks", "kill or be killed") are fine.

**Allowed:** animals (living and extinct), historical unit types ("a Roman legionary", "a
samurai"), objects and plants, vehicles and machines (companies, organizations and brands are
fine: "a Jeep"), and mythical
creature *types* ("a dragon", "a werewolf"). Capitalized breed and species names ("a German
Shepherd", "a Komodo dragon") and lowercase common nouns that are also names ("a napoleon", the
pastry; "a wolverine", the animal) are allowed too. Kinds of objects are never places, even where
Wikidata files them under one ("a vending machine", "a lighthouse").

## 2. The layers, in order

1. **Code rules** (`rules.py`, word lists in `blocklist.yaml`) run on the whole text before any
   model call. They catch only clear cases: self-harm phrases about the user ("end my life",
   "hurt myself"), minors, groups of people, "me", "my brother", and real-world attack planning.
   Attack planning needs both a clear ask ("step by step", "how to", "plans to") and a harm word
   followed by a real-world target ("attack a shopping mall"; not "a school of fish" or "an
   office brawl"), or a direct ask right before harm to a person ("how to poison someone"; not
   "the wolf attacks someone"). A harm word whose subject is a fighter is fight wording, so it
   doesn't count: "how a lion would attack a restaurant", "how would a bear kill a shark in the
   hospital" (#317). This exception looks only at the harm word's subject. A person or pronoun
   as the subject still counts ("how would I attack a restaurant", "how a terrorist would attack
   a mall", "how would a boy attack a school"): the person words are `not_fighters` plus every
   people list in `blocklist.yaml`. A person subject on none of those lists ("a retired
   accountant") is left to the classifier, and a subject of four or more words is never read as
   a fighter, so it still blocks. The text is read with curly apostrophes
   made straight and "my self" as "myself". A rule must never block an animal or archetype ("a
   baby elephant", "a German Shepherd") or ordinary fight wording ("the bear attacks first", "a
   guide dog").
2. **The classifier** (`classify.py`, prompt `backend/prompts/safety_classify.md`) runs
   *alongside* the parse call. The model picks one label from a fixed list; code writes the
   message. A classifier block wins as soon as it arrives (the parse call is cancelled).
3. **On the parsed sides** (`gate.py: check_parsed_sides`): code rules again on each side's raw
   text, entity, variant and size reference; then, at the same time, the **Wikidata name check**
   and, only if the model's reading uses words the user never typed ("a wolf" → "godzilla"), a
   **second classifier pass** on that reading.

The first block wins, in that order. Wikidata never overrides a rules or classifier block; it can
only add one. `check_matchup` runs every layer on a `Matchup` that never went through intake
(the battle API, A05, must call it before research).

## 3. Failure handling

| Layer | When it fails | Why |
|---|---|---|
| Classifier | **Fails closed.** One retry, then `SafetyUnavailable`; intake turns that into `IntakeUnavailable` ("try again in a moment"). Nothing passes. | It is the only layer that reads intent (sexual, self-harm, "other"), so without it we can't say a request is safe. |
| Wikidata | **Fails open.** 2.5 s limit for all of one name's calls, no retry, a warning in the log, no verdict, nothing cached. Rules and the classifier still decide. | Wikidata is a public service we don't control. It adds precision for names; the classifier covers the same reasons, so an outage should slow nothing and block nothing. |
| Wikidata cache | **Fails open.** A read error is a miss and a write error is skipped, each with a warning. | A local database problem must never crash the safety check. |

## 4. The Wikidata check (`wikidata.py`, class map `wikidata_classes.yaml`)

**What's looked up:** each side's raw text, plus its entity when that names something else
("the short emperor" → also "napoleon"). The model writes entities in lowercase, so when every
entity word was typed by the user, the entity is looked up in the user's casing as a common noun
("moose" from "a moose …" is "a moose", never the bare name "Moose"). An entity with words the
user never typed is looked up bare, as a proper name. The variant is never looked up: in "a dog
named Napoleon" the fighter is the dog.

**Which item it picks:** the search's top 5 results, exact matches only (label or alias equals
the query, ignoring case), in search order, passing over:

- **Name items** (`skip_matches`): family names, given names, disambiguation pages. "Thor" the
  male given name is skipped, so "Thor" the god is judged; "Moon" the family name is skipped for
  the Moon.
- **Creative works** (`demote_matches`): magazines, films, albums, songs and the like, used only
  if nothing else fits ("Dragon" the magazine loses to the dragon).
- **Bands and sports teams**, when a *kind* item (anything with a "subclass of" value, or a
  taxon) also matched exactly: "Grizzly Bear" the band loses to the grizzly bear. A band must
  match by its label; a team may also match by an alias, since teams go by their nickname
  ("Lakers" matches the Los Angeles Lakers).

**Common nouns use the kind item.** When the top pick is not itself a kind of thing, the check
also finds the first *kind* item among the top 10 results. A name typed as a common noun (see
below) is judged by that kind item instead: "a wolverine" is the animal (result 6), not the
comic-book character ranked first. "Wolverine" and "a Wolverine" are still judged by the top
pick, so they block.

**How it climbs:** the picked item's own classes ("instance of" and "subclass of"), then "subclass
of" up to two more levels. If any class on the way is in the class map, the name is blocked with
that class's reason. `instance_only` classes (human, the band and team classes) count only on the
item's own "instance of", so the class "Roman legionary" is never a real person. `individuals_only`
classes (geographic location) count only for an item that is not a kind of thing: Paris and
Times Square are places, but the kind "vending machine" (which Wikidata files under shop →
workplace → geographic location) is not. Kinds of landforms ("a mountain") still block through
landform. "character" is `individuals_only` too (#340, D-38, D-60): a named character is one
individual, so "a centaur" and "a harpy" (kinds that Wikidata files under mythological Greek
character → mythical character → character) are allowed, while Cerberus and Medusa (the same
path, but individuals) still block. Kinds from a franchise still block through "fictional
species" (Pikachu, Dalek, Wookiee). "deity" is `individuals_only` as well (#400 review, D-38:
named deities only): Zeus, Thor and Anubis still block, while kinds such as "a valkyrie" pass
this layer and are left to the classifier.

**Proper names:** a name reads as a proper name, judged on the user's casing, when it has no
article or count ("Napoleon"), or when a word after "a", "the" or a number is capitalized ("a
Napoleon"). Otherwise it is a common noun ("a napoleon", "3 wolverines"). `real_person` counts
only for proper names: "a Napoleon" is blocked; "a napoleon" (the pastry) is not.

**Bare lowercase names (D-51, #186).** A bare name typed with no capital letters ("moose",
"shredder") is judged by the kind item, like a common noun, when the top pick is a person, a
fictional character or a creative work and a kind item also matched:

- Against a **person**, only when the kind item's *label* is the typed word. "a million ants vs
  moose" is allowed (the animal is labelled "moose"); "napoleon vs a goose" is still blocked
  (the pastry is labelled "mille-feuille" and has "napoleon" only as an alias).
- Against a **character or creative work**, an alias match is enough: "stapler vs shredder" is
  allowed ("paper shredder" has the alias "shredder").
- **Capitals mean a proper name**: "Moose vs a wolf" and "Shredder vs a stapler" still block, and
  so does a request that types the same name both ways ("moose" and "Moose"). A name only the
  model wrote ("napoleon" from "the short emperor") keeps the proper-name reading too.
- Deities, groups (bands and sports teams, which keep the group rule below) and other picks are
  unchanged: "thor" still blocks as a deity.
- Accepted on purpose: lowercase "hulk" passes this layer (a ship type is labelled "hulk"), so
  only the classifier blocks "hulk vs a goose" (case bn-04). The same goes for other real people
  and characters ("madonna", "superman"; cases bn-06 and bn-07); see section 8.

The label-or-alias test is made when the name is checked, from the cached kind item's label, so
the cache needed no new column.

**The band and sports-team rule** (D-59; D-38: groups of people). Bands and sports teams are
*groups* (`group: band` or `group: team` in the class map; any item whose own "instance of"
includes one is a group). A group blocks as `real_person` only when the typed name names it,
with capitals matching its name (a band's label, or the alias a team matched, such as "Lakers"):

- "the" (any capitals) plus the name without its own "the": "the Beatles", "the Eagles", "the
  Lakers" and "the Bulls" are blocked, and so are full team names ("the Chicago Bulls", "the
  Philadelphia Eagles"); "the eagles" is not.
- The bare name, only when it is **not a common word**. The check looks up the singular
  ("eagles" → "eagle") and asks whether any exact match among its top 10 results is a kind item.
  "Beatles" and "Lakers" are blocked (no kind item for "beatle" or "laker"); "Eagles", "Bulls"
  and "Wolves" are allowed (the eagle, the bull and the grey wolf, result 6 for "wolf"). This
  costs one extra search, only for group picks whose last word is plural.
- **ALL CAPS** counts as matching capitals: "THE BEATLES", "THE EAGLES" and "BEATLES" are
  blocked ("EAGLES" is still the birds). Mixed capitals must match the name.
- **A group that lost the pick** to a kind item is remembered with the lookup. If the kind is a
  common word (it has a "subclass of" value, or is an organism known by a common name), only the
  group's full name with its own "The" names it: "the Police" and "the Doors" are blocked (the
  item "police", and "doorway" through its alias "doors", win the pick); "Police", "the police"
  and "the Grizzly Bear" are not. If the kind is only a bare taxon, not a common word, the
  normal wording applies: "Metallica" is blocked (its rival is a moth genus), "metallica" is not.
  Sports teams follow the same rule; a team's alias has no "The" of its own, so "the Heat" (the
  kind "heat" wins) and "the Yankees" (the kind "Yankee" wins) are left to the classifier.
- **"the" + a capitalized name also searches "the " + the name** (#316), at the same time as the
  search for the name, so it adds no wait inside the 2.5 s limit. The search for "who" never
  reaches the band The Who (the World Health Organization ranks first and the band isn't in the
  top results), but the search for "the who" ranks it first. When nothing else recorded a group,
  the first band or team among that search's top 5 results whose label is "The" + the name
  (ignoring case) is kept like a group that lost the pick, as a common word, so only "the" + its
  name blocks: "the Who", "The Who", "THE WHO", "the Cure", "the Animals", "the Strokes" and "the
  Cars" are blocked; "Who", "WHO", "the who" and "the animals" are not. The extra search runs
  only when a typed name starts with "the" and reads as a proper name; a lowercase "the who"
  could never name the band, so it isn't searched. If only the extra search fails (a rate limit,
  say), the plain search's answer is used, so "the Beatles" still blocks (#329); if the plain
  search fails, the layer fails open as usual.

Companies, organizations and brands are not groups and stay allowed ("a Jeep" is a car brand).

**The cache:** SQLite table `wikidata_safety_cache` in `data/app.db`, one row per lookup text with
both the top pick and the kind item, so either reading works from a cache hit. A "the" lookup
("the Who") is stored under its own text, "the who", with what both searches found, and its
plain answer under "who", so neither ever answers the other's question. When only the "the"
search failed, just the plain answer is stored, so the next "the Who" searches again. A match
is kept 30 days and a no-match 7 days. Each row stores the class map's `classes_version`; rows
from another version are ignored, so a class-map change takes effect at once.

## 5. Adding a class

1. Find the class's Q-ID and **verify it live** (`https://www.wikidata.org/wiki/Special:EntityData/<QID>.json`).
   Check that the items you want to block reach it within two "subclass of" levels, and that
   common allowed fighters don't.
2. Add it to `classes:` in `backend/app/safety/wikidata_classes.yaml` with `qid`, `label` (the
   live English label) and `reason` (a contract `blocked_reason`). Add `instance_only: true` if it
   should only match an item's own "instance of", or `individuals_only: true` if kinds of things
   reach it that must stay allowed.
3. **Bump `classes_version`** and add a line to the version notes at the top of the file.
4. Add a mock entity to `backend/tests/fixtures/providers/wikidata/entities.json` and a case to
   `backend/tests/fixtures/safety_cases.yaml`.
5. Run `npm run check`, then the live eval (below).

## 6. Running the eval

The cases live in `backend/tests/fixtures/safety_cases.yaml`: blocked cases covering every
reason, allowed cases (objects, machines and mythical creatures among them) and prompt-injection
pairs. `tests/unit/test_safety_cases.py` checks the minimum counts (#27). Each case says what it
expects, which layer should decide on mocks, and how the stand-in models
answer.

- **Mock run, in CI:** `tests/unit/test_safety_cases.py` runs every case through
  `parse_matchup` with stand-in models and mock Wikidata. It requires 100% recall on blocked
  cases, zero false blocks, the exact reason and the expected layer.
  `tests/golden/test_safety_injections.py` checks each injection gives the same result as its
  clean case. Run them with `npm run test:backend`.
- **Live run, by hand only:** from the repo root,
  `uv run --directory backend python scripts/safety_eval.py`. It needs a working `.env`
  (`npm run env:check`). It ignores the `mock:` blocks and uses the live chat model, live
  Wikidata and a fresh temp cache. It never runs in CI and never prints hosts, keys or
  environment values (the report is scanned before printing).

**Reading the live output:** one row per case with what was expected, what came back
(`allowed`, a reason, `clarify` or `error`), the deciding layer and the time, then each miss
with what the model read and what Wikidata picked for each name, then precision and recall
overall (blocked vs not) and per reason. A `clarify` on a blocked case counts as a miss.

## 7. Appealing a false block

Open an issue with `/new-issue`, giving the exact input and the message shown. If it's a
Wikidata pick, the fix is usually a `skip_matches`, `demote_matches` or `kind_matches` entry
(with a `classes_version` bump) plus a new case in `safety_cases.yaml`.

## 8. Known limits

- **The mock run doesn't measure the classifier.** On mocks its verdict is written into each
  case, so CI checks the plumbing (rules, class map, reason routing). Classifier quality is
  only measured by the live eval.
- **Wikidata picks can be wrong.** The top pick comes from the top 5 search results (the kind
  item for common nouns from the top 10), so the right item can be missing. Some picks are odd
  but harmless, such as "a bulldozer" picking a record label (an organization, which isn't
  blocked).
- **Bare lowercase names of real people and characters can pass the Wikidata check** when some
  kind item shares the name (D-51), so only the classifier blocks them:
  - *Real people*, when a kind item has the name as its label: "madonna", "adele", "bono",
    "usher", "pink", "flea" (case bn-06).
  - *Characters*, when a kind item has the name even only as an alias: "hulk" (a ship type),
    "superman", "goku", "bowser", "grinch", "simba", "thanos", "cyclops", "wolverine", "link"
    (cases bn-04 and bn-07).

  A bare capitalized name ("Madonna", "Moose") still reads as a proper name and blocks here. If
  the live eval shows the classifier missing these, the fix is to tighten what counts as a kind.
- **Kinds reach "character" only as individuals (#340).** Since `classes_version` 11 a kind
  (anything with a "subclass of") is never blocked through "character"; that is what lets "a
  centaur", "a harpy", "a zombie", "a ghost" and "an ogre" through. Kinds from a franchise must
  reach "fictional species" within the walk to block here: Pikachu, Xenomorph, Dalek, Wookiee,
  Hobbit and Cyberman do (checked live 2026-11-17), but "a stormtrooper" (fictional soldier →
  character) now passes this layer and is left to the classifier. Named individuals with no
  "subclass of" (Cerberus, Medusa, Mickey Mouse) are unchanged. Live, bare "Cerberus" and
  "Medusa" pick other same-named items (for "Medusa", a ship), so the classifier blocks those cases
  (cc-05, cc-06), as before. A named character that carries a stray "subclass of" claim now
  counts as a kind here, so it relies on the classifier (or on "fictional species" when it is a
  franchise kind). Kryptonian and Goomba are newly blocked here through "fictional species".
- **Franchise kinds left to the classifier.** "a stormtrooper" and "a Minion" pass the Wikidata
  layer; the live classifier blocked both on 2026-11-17 (cases cc-07, cc-08). Lowercase "a
  minion" was also blocked by the classifier that day; it may mean a generic underling, so it is
  not a keeper case.
- **Deity kinds are allowed; named deities block (#400 review, D-38).** "a god", "an angel", "a
  demon", "a valkyrie" and "a titan" are kinds (cases my-09 to my-13). Wikidata now blocks only
  named deity individuals ("deity" is `individuals_only`); the classifier decides kinds, and its
  prompt says generic kinds are allowed while "Zeus", "Thor" or "God" stay deity. On the live
  probe of 2026-11-17, before this change, "a valkyrie" was blocked at Wikidata (its kind item
  reaches "deity", which then applied to kinds) and "a god" was blocked by the classifier (the
  prompt clarification is meant to fix that). A second live probe the same day, after those
  fixes, allowed "a god" and "a valkyrie" as well as the angel, demon and titan.
- **The attack-planning rule is a word list.** It catches clear phrasings only; the classifier
  covers the rest.
- **"step by step: a wolf would kill a deer at the airport" still blocks as `other`.** The
  fighter-subject exception needs "how" before the subject when the modal comes after it ("how a
  wolf would kill"). This is the safe direction (over-blocking); a follow-up can widen it.
- **Self-harm phrases also match fight text about a fighter.** "a cornered rat that doesn't want
  to die vs a cat" and "a suicide bomber vs a goose" block as `self_harm`. This is deliberate:
  over-blocking is the safer mistake, and the user can rephrase.
- **"Kraken" (capitalized, bare) blocks as `real_person`.** It names the band Kraken, which loses
  the Wikidata pick but whose rival is a bare genus, not a common word (the #164 rule that blocks
  "Metallica"). "a kraken" is allowed. Accepted trade-off (PM, #185 review); case band-11. Live,
  the parse model may ask a clarifying question for "Kraken vs a whale" before Wikidata runs (it
  did on the final #185 run), which is also not an allowed fight.
- **Lowercase full names after an article pass the Wikidata check.** "a barack obama" or "the
  abraham lincoln" reads as a common noun, and `real_person` counts only for proper names, so
  only the classifier blocks it (cases rp-07 and rp-08): a model's judgment, not a guarantee. A
  possible follow-up: treat a lowercase multi-word name whose top pick is a human as a person.
- **Capitalized brands that are also people's names** can be blocked as `real_person` ("a Tesla"
  may pick a person). Lowercase works.
- **Bands and sports teams** are blocked only through the band and sports-team rule; a band that
  matches only through an alias, or a group whose name differs from what was typed, is left to
  the classifier. Only the listed team classes count (sports team, professional sports team,
  basketball, American football, ice hockey and baseball teams, football and rugby union clubs);
  a team filed under another class, or one that isn't in the top 5 results, is missed. (Checked
  live 2026-11-15 for #310: the Chicago Bulls, Philadelphia Eagles, New York Yankees, Los
  Angeles Lakers, Manchester United, Real Madrid, FC Barcelona, Wolverhampton Wanderers and
  Chicago Bears all have a listed team class as their own "instance of", so "sports club" isn't
  needed.) A team whose nickname is also a kind of thing's name loses the pick, and its nickname
  has no "The" of its own, so it passes this check: "the Yankees" picks the item "Americans",
  and the kind "Yankee" (alias "Yankees") beats the New York Yankees ("the New York Yankees" is
  blocked here). "the Heat" is the same. The classifier is the backstop for these alias-only
  team names: its prompt names sports teams and clubs as groups of real people (#328; cases
  team-07 and team-08), while an animal kind that a team shares ("the Lions", "wolves",
  "bears") stays the animal (cases team-09, an-09, an-10). A model's judgment, not a
  guarantee: the live eval measures it. A band found only
  by the "the" search (#316) must be in that search's top 5 with the label "The" + the name;
  one labelled otherwise is left to the classifier.
- **The classifier can answer differently from run to run.** Re-run the live eval after any
  prompt change and compare.
