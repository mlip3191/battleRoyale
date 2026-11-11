# Safety gate (A04)

Every matchup goes through the safety gate before anything else happens: no research, image,
voice or music provider is called for a blocked request (tested in
`backend/tests/unit/test_safety_zero_calls.py`). Code lives in `backend/app/safety/`.

## 1. What's blocked and why

The rules come from DECISIONS D-07 (allowed and blocked fighters) and D-38 (widened to objects,
machines and mythical creature types). Each block has one reason; the user sees a friendly
message for it (`safety/verdict.py`), never the layer or the model's words.

| Reason | Blocks | Example |
|---|---|---|
| `real_person` | named real people, the user or someone they know, bands (groups of real people) | "Napoleon", "my brother", "the Beatles" |
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
samurai"), objects and plants, vehicles and machines (brands are fine: "a Jeep"), and mythical
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
   "the wolf attacks someone"). The text is read with curly apostrophes made straight and "my
   self" as "myself". A rule must never block an animal or archetype ("a baby elephant", "a
   German Shepherd") or ordinary fight wording ("the bear attacks first", "a guide dog").
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
- **Bands**, when a *kind* item (anything with a "subclass of" value, or a taxon) also matched
  exactly: "Grizzly Bear" the band loses to the grizzly bear.

**Common nouns use the kind item.** When the top pick is not itself a kind of thing, the check
also finds the first *kind* item among the top 10 results. A name typed as a common noun (see
below) is judged by that kind item instead: "a wolverine" is the animal (result 6), not the
comic-book character ranked first. "Wolverine" and "a Wolverine" are still judged by the top
pick, so they block.

**How it climbs:** the picked item's own classes ("instance of" and "subclass of"), then "subclass
of" up to two more levels. If any class on the way is in the class map, the name is blocked with
that class's reason. `instance_only` classes (human, the band classes) count only on the item's
own "instance of", so the class "Roman legionary" is never a real person. `individuals_only`
classes (geographic location) count only for an item that is not a kind of thing: Paris and
Times Square are places, but the kind "vending machine" (which Wikidata files under shop →
workplace → geographic location) is not. Kinds of landforms ("a mountain") still block through
landform.

**Proper names:** a name reads as a proper name, judged on the user's casing, when it has no
article or count ("Napoleon"), or when a word after "a", "the" or a number is capitalized ("a
Napoleon"). Otherwise it is a common noun ("a napoleon", "3 wolverines"). `real_person` counts
only for proper names: "a Napoleon" is blocked; "a napoleon" (the pastry) is not.

**The band rule** (D-38: groups of people). A band item blocks only when the typed name names it,
with capitals matching the label:

- "the" (any capitals) plus the band's label without its own "the": "the Beatles" and "the
  Eagles" are blocked; "the eagles" is not.
- The bare label, only when the band's name is **not a common word**. The check looks up the
  singular ("eagles" → "eagle") and asks whether any exact match is a kind item. "Beatles" is
  blocked ("beatle" has no exact match); "Eagles" is allowed (the eagle is an animal). This costs
  one extra search, only for band picks whose last word is plural.

**The cache:** SQLite table `wikidata_safety_cache` in `data/app.db`, one row per lookup text with
both the top pick and the kind item, so either reading works from a cache hit. A match is kept
30 days and a no-match 7 days. Each row stores the class map's `classes_version`; rows from
another version are ignored, so a class-map change takes effect at once.

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

The cases live in `backend/tests/fixtures/safety_cases.yaml` (79 cases: 41 blocked covering every
reason, 38 allowed, 12 of them objects, machines or mythical creatures, and 7 prompt-injection
pairs). Each case says what it expects, which layer should decide on mocks, and how the stand-in
models answer.

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
- **Bare lowercase names read as proper names.** "moose vs a wolf" (no article) looks up "moose"
  as a name, and live Wikidata's top pick is a person called Moose, so it can be blocked as
  `real_person`. Likewise "stapler vs shredder" picks Shredder, the cartoon character. "a moose"
  and "a shredder" work. The classifier's lowercase rule doesn't help here, because any block
  wins.
- **The attack-planning rule is a word list.** It catches clear phrasings only; the classifier
  covers the rest.
- **Lowercase full names after an article pass the Wikidata check.** "a barack obama" or "the
  abraham lincoln" reads as a common noun, and `real_person` counts only for proper names, so
  only the classifier blocks it (cases rp-07 and rp-08): a model's judgment, not a guarantee. A
  possible follow-up: treat a lowercase multi-word name whose top pick is a human as a person.
- **Capitalized brands that are also people's names** can be blocked as `real_person` ("a Tesla"
  may pick a person). Lowercase works.
- **Bands** are blocked only through the band rule; a band that matches only through an alias,
  or whose label differs from what was typed, is left to the classifier.
- **The classifier can answer differently from run to run.** Re-run the live eval after any
  prompt change and compare.
