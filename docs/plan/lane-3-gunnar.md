# Lane 3 — Gunnar: Research & Knowledge Base

**Total effort: 15 points.** Gunnar owns the facts: where they come from, how they are retrieved, how they become a stat sheet, and how we prove every number is sourced. Also owns the benchmark set and the showcase battles that ship with the repo.

| ID | Task | Size | Depends on | Blocks | Wave |
|---|---|---|---|---|---|
| G01 | Seed fighter list + source plan | S | M08 | G02, G05, G07 | 1 |
| G02 | Knowledge-base ingestion (parse, chunk, embed, store) | M | G01, M06 | G03 | 2 |
| G03 | Retrieval + rerank | M | G02 | G04 | 3 |
| G04 | Stat-sheet builder + fighter API | M | G03, M05 | A05 (real research), D04 | 3 |
| G05 | Hand-verified seed stat sheets | M | G01, M05 | F07, demo | 2 |
| G06 | Traceability checker | S | G04 | benchmark | 4 |
| G07 | Benchmark matchup set | M | G01 | F07 | 2–4 |
| G08 | Showcase battles + fresh-clone run check | S | A05, M04, G09, F08 | demo, instructor | 4 |
| G09 | Objects, machines, plants, and mythical creatures | M | G04 | F08 (real sheets), A05 | 3–4 |

G07 pairs with Felipe's F07: Gunnar builds the benchmark data, Felipe builds the runner that scores it.

**Definition of Done for every task (CLAUDE.md §7), on top of its own acceptance criteria:** at least one test for every code change (docs-only tasks such as G01, G07, F01, D09, and D10 are checked by the reviewer instead); `npm run check` passes; the app still starts with `npm start`; the PR uses the template with `Closes #<n>`, explains the change in plain English, and ticks each criterion with its evidence (test name, command output, link, or screenshot); docs updated if behavior changed; a teammate approved and all required checks passed before merging. Criteria marked "live" are run by the task owner on their own machine (never in CI), and the pasted results never include endpoint hosts or keys.

---

## G01 · Seed fighter list + source plan · S (1)

**Goal:** Decide which fighters we support first and where their facts come from. No coding.
**Read first:** PRODUCT_SPEC step 2; ARCHITECTURE §5 (`StatSheet`, `StatName`), §11.

**Prompt for Claude Code:**
```text
Task G01 from docs/plan/lane-3-gunnar.md. Help me write docs/research.md. Do not write code.
1. Propose 30 seed fighters across categories (big predators, small animals good for swarms, herbivores, birds, reptiles, aquatic, insects, 2–3 dinosaurs, 3 generic historical human archetypes, and 5 non-animals: main battle tank, bulldozer, pickup truck, toaster, saguaro cactus). Mythical creatures are not seed fighters; G09 handles them. For each: fighter_id slug, display name, default variant, category, habitat, and the Wikipedia article title. Include classics: house cat, golden retriever, grizzly bear, gray wolf, African elephant, honey badger, chimpanzee, bald eagle, saltwater crocodile, great white shark, army ant, Tyrannosaurus rex, Roman legionary. Also include every fighter in the five showcase battles (docs/PRODUCT_SPEC.md section 9): horse, duck, honey badger, king cobra, Roman legionary, gorilla, grizzly bear, gray wolf, main battle tank, plus the showcase dragon's analogs, saltwater crocodile and African elephant (the dragon itself goes in G09's mythical.yaml, not the seed list).
2. For each StatName, explain in plain English what it means, its unit, where it usually appears in Wikipedia/Wikidata or the trait datasets, and what we do when it's missing (category default). Separate the seven physical stats (sourced or estimated) from the three behavioral stats (aggression_0_1, group_tactics_0_1, armor_0_1), which no source measures: write a rubric for each with 5 levels and one-line descriptions plus example animals (e.g. aggression 1 = flees from almost everything, 5 = attacks animals larger than itself), so every "assumption" value cites a rubric level.
3. The source policy, starting from the recommended datasets in docs/DECISIONS.md (D-20): Wikipedia Structured Contents (wikimedia/structured-wikipedia on Hugging Face) as the main text source, FineWiki as backup, Wikidata for referenced numbers, PanTHERIA and AnimalTraits for body mass and size, and optionally the TreeOfLife taxonomy metadata for name normalization. For each: what we take, license, and how we attribute. Not allowed: forums, fan wikis, AI-generated pages, and any dataset whose card says values were AI-generated or unsourced.
4. A short "variants" rule: what default we pick when a user says just "bear", "shark", "wolf", or "eagle".
Show me the draft, I'll edit it, then commit.
```

**Acceptance criteria**
- [ ] `docs/research.md` lists 30 seed fighters, each with slug, display name, default variant, category, habitat, and article title; the list includes the 13 animals named in step 1, the 5 non-animals, every real fighter in the five showcase battles (PRODUCT_SPEC §9), and the dragon's two analogs
- [ ] Each of the 7 physical stats has its meaning, unit, typical source, and fallback; each of the 3 behavioral stats has a 5-level rubric with a one-line description and an example animal per level
- [ ] The source-policy table lists every dataset from DECISIONS D-20 with what we take, its license, and how we attribute it, plus the not-allowed list
- [ ] The default-variant rule covers at least "bear", "shark", "wolf", and "eagle"
- [ ] Mike approves in review

---

## G02 · Knowledge-base ingestion · M (2)

**Goal:** Download and index the seed fighters' reference text so retrieval works offline and fast.
**Read first:** ARCHITECTURE §7 (DocParser, Embedder), §8; `docs/research.md`; `docs/providers.md`.

**Prompt for Claude Code:**
```text
Task G02 from docs/plan/lane-3-gunnar.md. Build backend/app/research/ingest.py and backend/scripts/ingest_seed.py.
1. For each seed fighter in docs/research.md (store the list as data/seed/fighters.yaml so code can read it): fetch the article HTML from the Wikipedia REST API (fast; same CC BY-SA text as the Hugging Face dumps) and the Wikidata entity JSON. For the Hugging Face part, try the Hugging Face Dataset Viewer API to look up the fighter's row in wikimedia/structured-wikipedia (parsed infobox) without downloading the dataset; if that's slow or unavailable, instead upload our small PanTHERIA/AnimalTraits subset as a team dataset on Hugging Face and load it from there, so the proposal's Hugging Face claim holds. Never stream or download a full Wikipedia dump (no key needed; send a descriptive User-Agent with the project name, not a personal email). Save raw files under data/kb/ (gitignored) with title, URL, license, retrieved_at.
2. Parse every fetched HTML article (and any PDF source) through the DocParser provider (port 9005) — this is the course Document Parsing endpoint's real job in our app; plain text skips parsing.
3. Chunk text (~800 characters, 100 overlap, keep section headings as chunk metadata), embed with the Embedder provider (port 9002) in batches, and store in SQLite: documents, chunks, and a sqlite-vec virtual table chunks_vec. Add the migration file in backend/app/db/migrations/.
4. Pull structured facts into a facts table with source, field, value, unit, and reference: Wikidata (mass, length, speed where present, with property IDs), PanTHERIA (adult body mass, head-body length) and AnimalTraits (body mass) matched by scientific name. Download the trait files once into data/kb/ by script; they are high-confidence sources for G04. Ask me before adding the datasets library.
5. Live adapters for DocParser and Embedder in backend/app/providers/live/ following docs/providers.md.
6. The script is idempotent (re-running skips unchanged docs) and prints a summary table: fighters, documents, parsed (HTML documents sent through DocParser), chunks, facts, failures.
7. Tests on mocks: chunking, idempotency, a fighter whose article is missing (logged, not fatal).
Run it live for the 30 seed fighters and paste the summary in the PR. Do not commit anything under data/kb/.
```

**Acceptance criteria**
- [ ] `uv run python -m scripts.ingest_seed` completes live for all 30 seed fighters; the summary table (fighters, documents, parsed, chunks, facts, failures) is pasted in the PR
- [ ] Every fetched HTML article went through the DocParser endpoint (parsed = HTML documents in the summary)
- [ ] At least one source is loaded through Hugging Face (Dataset Viewer lookup or the team dataset), and `docs/research.md` says which
- [ ] A second run finishes in under a minute and changes nothing (row counts identical)
- [ ] Every facts-table row has source, property ID or field name, unit, and reference
- [ ] After ingest, `git status` shows nothing under `data/kb/` or `data/app.db`; mock tests cover chunking, idempotency, and a missing article

---

## G03 · Retrieval + rerank · M (2)

**Goal:** Given a fighter and a stat, return the best few evidence passages.
**Read first:** ARCHITECTURE §7 (Reranker), §8.

**Prompt for Claude Code:**
```text
Task G03 from docs/plan/lane-3-gunnar.md. Build backend/app/research/retrieve.py.
1. retrieve(fighter_id, query, k=20) -> list[Passage] using sqlite-vec similarity over chunks for that fighter (filter by fighter first), plus Wikidata facts as passages with high priority.
2. rerank(query, passages, top_n=5) using the Reranker provider; live adapter in providers/live/rerank.py per docs/providers.md. If the reranker is down, fall back to vector order and note it.
3. evidence_for(fighter_id, stat_name) -> list[Passage]: builds a good query per StatName (e.g. "adult body mass weight kg" for mass_kg), retrieves, reranks, and returns passages with doc title, URL, and the exact text.
4. A small retrieval quality check: backend/tests/fixtures/retrieval_cases.yaml with 15 (fighter, stat, expected phrase) cases; on live mode, report hit@5. On mocks, test the plumbing only.
5. For fighters not in the seed list: fetch and ingest their article on demand (reuse G02 code), with a 30 s limit; if that fails, return no evidence (G04 will fall back).
```

**Acceptance criteria**
- [ ] `evidence_for(fighter_id, stat)` returns at most 5 passages, each with document title, URL, and exact text (test)
- [ ] Live hit@5 is at least 80% on the 15 cases in `retrieval_cases.yaml` (result pasted in the PR)
- [ ] With the reranker failing, results fall back to vector order and a note is logged (test)
- [ ] On-demand ingestion of one non-seed fighter finishes within 30 s live; a failure returns no evidence instead of an error (test)

---

## G04 · Stat-sheet builder + fighter API · M (2)

**Goal:** Produce a complete, validated `StatSheet` where every number is sourced or clearly an estimate.
**Read first:** ARCHITECTURE §5 ("The number rule, made precise"), §6 (`/api/fighters`).

**Prompt for Claude Code:**
```text
Task G04 from docs/plan/lane-3-gunnar.md. Build backend/app/research/statsheet.py.
1. get_stat_sheet(fighter_request) -> StatSheet. Order of preference per stat:
   a. hand-verified seed sheet in data/seed/fighters/<id>.json (method hand_verified);
   b. Wikidata fact (method extracted, quote = the property and value);
   c. Chat-model extraction from evidence_for(...) passages with ChatLLM.complete(..., json_schema=...) (prompt backend/prompts/stat_extract.md; D-41): the model must return value, unit, and the exact quote; code converts units (research/units.py) and accepts the value only if the number appears in the quote and the quote appears in the passage;
   d. derived by code from other stats (e.g. size from mass), documented in the note;
   e. category default from research/defaults.py (is_estimate=True, confidence low).
   The three behavioral stats (aggression_0_1, group_tactics_0_1, armor_0_1) are never extracted: use the hand-verified seed value if there is one, else method "assumption" at the category's rubric level from docs/research.md (defaults.py), with the level in note.
   Fill low/high on every value per ARCHITECTURE section 5 "Ranges": the source's range if it gives one, else ±10% / ±25% / ±50% for high / medium / low confidence.
2. No new provider is needed: extraction uses the existing chat adapter (providers/live/chat.py) in JSON-schema mode (D-41).
3. Cache sheets in the stat_sheets table keyed by fighter_id + sheet_hash; GET /api/fighters?q= and GET /api/fighters/{fighter_id}.
4. Sanity bounds per stat, wide enough for objects and vehicles (e.g. mass 0.000001–1,000,000,000 kg, speed 0–1,000 m/s); out-of-bounds values are rejected and logged.
   Objects, machines, plants, and mythical creatures are finished in G09; until then they get category defaults.
5. Tests on mocks: each preference level, a rejected quote mismatch, unit conversion (lb, km/h, ft), and a fighter with zero evidence (all estimates and assumptions), ranges filled on every value, behavioral stats always "assumption".
```

**Acceptance criteria**
- [ ] One test per preference level shows the chosen value follows the order hand-verified → Wikidata → extracted → derived → category default
- [ ] An extracted value whose number isn't in its quote, or whose quote isn't in the passage, is rejected and falls back (test); no model-produced number is accepted without a verified quote
- [ ] Unit-conversion tests pass for lb→kg, km/h→m/s, and ft→m
- [ ] A value outside its sanity bounds is rejected and logged (test)
- [ ] Every `StatValue` has `low`/`high` per ARCHITECTURE §5 "Ranges"; the 3 behavioral stats are `assumption` with a rubric level in `note` (tests)
- [ ] A fighter with zero evidence gets a valid sheet of estimates and assumptions (test)
- [ ] `GET /api/fighters?q=` and `GET /api/fighters/{id}` return cached sheets; A05's research stub is replaced by the real function

---

## G05 · Hand-verified seed stat sheets · M (2)

**Goal:** Fifteen gold-standard stat sheets the demo, the benchmark, and Mike's AI evaluation (M09) can trust. Mostly careful reading, little code.
**Order and timing:** the 15 sheets are the 9 real fighters in the five showcase battles (PRODUCT_SPEC §9), the dragon's two analogs (saltwater crocodile and African elephant — the dragon itself is never hand-verified; G09 builds it from these), and 4 more seed fighters. First five by Sat Nov 14 — horse, duck, grizzly bear, gray wolf, honey badger (showcase battles 1 and 2 complete, before your research pipeline exists, so these answers are independent of it); the other ten by Wed Nov 18.
**Read first:** `docs/research.md`; ARCHITECTURE §5 (`StatSheet`).

**Prompt for Claude Code:**
```text
Task G05 from docs/plan/lane-3-gunnar.md. Help me create hand-verified stat sheets for 15 seed fighters, as data/seed/fighters/<fighter_id>.json, valid against the StatSheet model: the 9 real fighters in the five showcase battles (docs/PRODUCT_SPEC.md section 9), the showcase dragon's two analogs, and 4 more from docs/research.md that I choose.
Order: horse, duck, grizzly bear, gray wolf, honey badger first (due Sat Nov 14), then king cobra, Roman legionary, gorilla, main battle tank, saltwater crocodile, African elephant, then my 4. The tank is an object sheet: body "machine", weapons ramming and crushing, a generic media_name, mass, size, and speed from its article; its behavioral stats are assumptions like everyone else's. For each fighter, work one physical stat at a time (mass, size, speed, attack force, attack rate, reach, endurance): open the source (Wikipedia, Wikidata, a trait dataset, or the paper it cites), show me the exact sentence and the number, convert units, and wait for me to confirm before writing it. Use method "hand_verified" with the real URL and quote, and a low/high range if the source gives one. If no reliable source exists, use the category default with is_estimate=true and explain why in note. For the three behavioral stats, use method "assumption" with the rubric level from docs/research.md in note — never "hand_verified".
Add a test that every file validates and that no hand_verified value lacks a source. At the end, show me a table of fighters x stats with H (hand-verified), E (estimate), or A (assumption).
```

**Acceptance criteria**
- [ ] Sheets for horse, duck, grizzly bear, gray wolf, and honey badger merged by Sat Nov 14; all 15 (the 9 real showcase fighters, saltwater crocodile, African elephant, and 4 more) by Wed Nov 18; all validate against `StatSheet`
- [ ] Every `hand_verified` value has a working URL and an exact quote that contains the number
- [ ] The 3 behavioral stats use `assumption` with a rubric level in `note`; none are `hand_verified`
- [ ] No fighter has more than 2 of its 7 physical stats as estimates; a coverage table (fighters × stats, marked H / E / A) is in each PR
- [ ] A test fails if any `hand_verified` value lacks a source or quote

---

## G06 · Traceability checker · S (1)

**Goal:** Prove the promise "every stat on screen links to its source."
**Hermes task (DECISIONS D-02):** build this one with the course's Hermes Agent (port 9000) instead of Claude Code, with Mike pairing. Treat it as a comparison: note in docs/build-log.md how long it took, what went well or badly, and how it compared with Claude Code, with screenshots. Same branch, PR, and review rules apply.
**Prompt for Claude Code:**
```text
Task G06 from docs/plan/lane-3-gunnar.md. Build backend/app/research/trace.py and a test.
check_battle(record: BattleRecord) -> TraceReport: for every StatValue in every stat sheet, verify: non-estimates have a source with URL and quote; extracted quotes still appear in the stored document text; estimates have method category_default or assumption (assumption only on the three behavioral stats, or on any stat of a mythical creature); derived values name their formula in note. Also scan all Script lines for numbers not present in the stat sheets or result (reuse A06's guard if it has landed).
Add backend/scripts/trace_report.py that runs the check on every stored battle and prints a summary; the benchmark (F07) calls it. Tests on fixtures: a clean battle passes ("0 issues"); each of these fails with a clear message: a non-estimate missing its URL or quote, a tampered quote, an estimate with the wrong method, a script with an invented number.
```

**Acceptance criteria**
- [ ] One test each shows `check_battle` flags: a non-estimate without URL or quote; an extracted quote no longer present in the stored document; an estimate or assumption with the wrong method; a script number not present in the inputs
- [ ] The clean fixture battle passes with a "0 issues" report
- [ ] `trace_report.py` runs on all stored battles and is called by F07's runner
- [ ] The Hermes comparison (time taken, what worked, what didn't, screenshots) is recorded in `docs/build-log.md`

---

## G07 · Benchmark matchup set · M (2)

**Goal:** A fair test set with "expert answers," so we can measure whether the simulator is sensible.
**Read first:** PRODUCT_SPEC "Evaluation"; DECISIONS D-10.

**Prompt for Claude Code:**
```text
Task G07 from docs/plan/lane-3-gunnar.md. Help me build data/benchmark/matchups.yaml. No app code.
1. 30 matchups using seed fighters (then move 10 of them, a mix of all three groups, into data/benchmark/heldout.yaml and don't look at their results while anyone tunes the engine — they're our honest test): 15 "obvious" (outcome follows from size/biology, e.g. house cat vs gray wolf; at least 3 involve an object or machine, e.g. house cat vs bulldozer), 10 "documented" (a zoologist, museum, or published source states a view — record the citation), 5 "count" cases where the expected fair-fight count range is known roughly (e.g. how many house cats to match one wolf).
2. Each entry: id, fighters (entity, count, variant), terrain, expected_winner (0, 1, or draw), confidence (high/medium), expected_fair_count range if any, source URL or "obvious: <one-line reason>".
3. Write docs/benchmark.md: how the set was built (mythical creatures are excluded because legends have no right answer), what counts as a pass (favorite matches expected_winner; for high-confidence cases the favorite's probability ≥ 0.7), and known weaknesses.
Show me the draft before committing.
```

**Acceptance criteria**
- [ ] `matchups.yaml` + `heldout.yaml` hold 30 entries: 15 obvious (at least 3 with an object or machine), 10 documented, 5 count; each has expected winner, confidence, and a citation URL or a one-line "obvious" reason; `docs/benchmark.md` says mythical creatures are excluded (no ground truth)
- [ ] `heldout.yaml` has 10 entries mixing all three groups and is committed before F07 runs anything; `docs/benchmark.md` says held-out results are never used to change constants
- [ ] `docs/benchmark.md` states the pass rules (favorite correct; high-confidence favorite ≥ 0.7; fair-fight count within the expected range) and known weaknesses
- [ ] Mike approves in review

---

## G08 · Showcase battles + fresh-clone run check · S (1)

**Goal:** The instructor's fresh clone runs with `npm start` and already shows our five showcase battles.
**Read first:** DECISIONS D-24, D-25; PRODUCT_SPEC §9 (demo plan); README "For the instructor".

**Prompt for Claude Code:**
```text
Task G08 from docs/plan/lane-3-gunnar.md.
1. backend/scripts/export_showcase.py: export the five showcase battles named in docs/PRODUCT_SPEC.md section 9 (BattleRecords plus their sprites, narration audio, and music) from the local database and data/media/ into data/showcase/ (committed). Keep the total under 20 MB; if it's bigger, drop music first, then audio, and say what was dropped.
2. backend/scripts/import_showcase.py, called automatically at backend startup: if the database has no battles, load data/showcase/ into it so the battles and their media appear without any endpoint calls.
   Also: in live mode, if the knowledge base is empty, the backend tells the user on startup to run `npm run ingest` (add that root script; it runs ingest_seed). Add the step to README "For the instructor".
3. A "Showcase" row on the Home page is Dillon's; give him a GET /api/battles?showcase=true route (list of battle_id and title) and tell him in the PR.
4. Fresh-clone check on my Windows machine: clone the repo into a new folder, follow README "For the instructor" exactly (copy .env.example to .env, fill it, node scripts/check-env.mjs, npm run setup, npm start), open http://localhost:8000, and confirm the showcase battles play. Then repeat with PROVIDER_MODE=mock and an empty .env to confirm the app still opens. Write down every step that was unclear and fix the README.
5. Tests: export then import round-trips identical records; import skips when battles already exist.
Mike repeats step 4 on his Mac during review.
```

**Acceptance criteria**
- [ ] `data/showcase/` is committed with the five showcase battles, under 20 MB in total
- [ ] In the dragon vs main battle tank battle, every dragon stat is tagged "assumption", the LoreCard shows both analogs, the script says "according to legend", and the tank only rams or crushes (checked by Mike in review)
- [ ] At startup the backend imports them into an empty database and skips the import when battles exist; an export → import round trip is identical (tests)
- [ ] `GET /api/battles?showcase=true` returns the five
- [ ] A fresh clone that follows README "For the instructor" exactly shows the showcase battles playing at http://localhost:8000 — on Windows (Gunnar) and Mac (Mike, in review)
- [ ] With an empty `.env` in mock mode the app opens; in live mode with an empty knowledge base, startup prints the `npm run ingest` instruction
- [ ] Every unclear README step found during the fresh-clone run is fixed in the same PR

---

## G09 · Objects, machines, plants, and mythical creatures · M (2)

**Goal:** Anything physical can fight — a toaster, a bulldozer, a cactus, a dragon — and every number is still sourced, labeled an estimate, or (for legends) built by code from real animals.
**When:** Wave 3–4 (Nov 16–19), after G04.
**Read first:** DECISIONS D-38; ARCHITECTURE §5 (`Body`, `LoreProfile`, the number rule), §9 "Bodies" and "Abilities", §14; `docs/research.md`.

**Prompt for Claude Code:**
```text
Task G09 from docs/plan/lane-3-gunnar.md. Extend backend/app/research/ so the stat-sheet builder handles every allowed kind of fighter (DECISIONS D-38).
1. Category and body: decide category and body (living / machine / inert) in code from Wikidata "instance of"/"subclass of" (e.g. motor vehicle -> vehicle/machine, household appliance -> object/inert, plant taxon -> plant/inert, legendary creature -> mythical/living). If Wikidata has no answer, the Structured Decisions model (StructuredLLM.decide, a choice question; D-41) may choose from the fixed lists only; code validates.
2. Objects, vehicles, machines, plants: pull mass, length/height, and speed from Wikidata (P2067 mass, P2043 length, P2048 height, P2052 speed) and the article infobox through the normal extract-and-verify path (G04). Add category defaults in research/defaults.py for object, plant, vehicle, and machine (attack force and rate for ramming/crushing are derived by F08's formula, so leave them to code). Behavioral stats: inert -> aggression 0 and group tactics 0 ("inert object"); machine -> the rubric's "operated to win" level; both as method "assumption". Armor for machines and objects uses a new 5-level durability rubric in docs/research.md (e.g. 1 = glass, 5 = tank armor).
3. media_name: a generic, brand-free name for image and music prompts ("electric pickup truck"). The model may propose it (no numbers involved); code checks the allowlist and a brand/franchise blocklist (backend/app/safety/brands.yaml) and falls back to the category name.
4. Mythical creatures: write data/seed/mythical.yaml with 12 creature types (dragon first — it is in a showcase battle: body_analog saltwater crocodile, size_analog African elephant, abilities flight and breath_weapon, unless the article supports better analogs; kraken, griffin, unicorn, minotaur, hydra, cerberus, phoenix, yeti, werewolf, basilisk, pegasus). For each: body_analog and size_analog (real seed fighters), abilities from the fixed Ability list, heads if relevant, and the exact sentence from the myth's Wikipedia article that justifies them, with its URL. Show me each one before saving.
   For a creature not in the file: fetch its Wikipedia article; the chat model (JSON-schema mode, D-41) picks body_analog and size_analog only from seed or cached real fighters, abilities only from the fixed list, and must return the exact quote that justifies them; code checks the quote is in the article (and the heads number is in the quote) or blocks the fighter as nonsense with a friendly message.
   Then code builds the sheet: copy the body_analog's sheet, scale to the size_analog with the same square-cube rules as size_reference (F03), set every stat to method "assumption" with a note naming both analogs, and fill lore.
5. Add 5 fighters to the seed list in docs/research.md and data/seed/fighters.yaml if G01 didn't (main battle tank, bulldozer, pickup truck, toaster, saguaro cactus) and ingest them.
6. Tests on mocks: a toaster is object/inert with sourced mass; a bulldozer is vehicle/machine; a dragon from mythical.yaml gets an all-"assumption" sheet scaled to its size_analog; an unknown creature with a quote that isn't in the article is blocked; a brand name never reaches media_name.
Ask me before adding any dependency.
```

**Acceptance criteria**
- [ ] Tests: toaster → `object` / `inert` with mass from a source; bulldozer → `vehicle` / `machine`; saguaro cactus → `plant` / `inert` with `spines`; a branded truck's `media_name` contains no brand word
- [ ] `data/seed/mythical.yaml` has 12 creature types, each with analogs from the seed list, abilities from the fixed list, and a quote that appears on its linked page (a test checks every entry validates)
- [ ] A dragon's sheet: every stat is `assumption`, the note names both analogs, and its mass equals the size analog's mass (test)
- [ ] On-demand creature: a mock returning a quote that isn't in the article is blocked as `nonsense`; a valid one builds a sheet (tests)
- [ ] Live: sheets for a toaster, a bulldozer, a dragon, and one creature not in the file, pasted in the PR as a coverage table (sourced / estimate / assumption per stat)
- [ ] `docs/research.md` has the durability rubric and the machine "operated to win" level
