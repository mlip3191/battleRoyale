# Lane 3 — Gunnar: Research & Knowledge Base

**Total effort: 13 points.** Gunnar owns the facts: where they come from, how they are retrieved, how they become a stat sheet, and how we prove every number is sourced. Also owns the benchmark set and the showcase battles that ship with the repo.

| ID | Task | Size | Depends on | Blocks | Wave |
|---|---|---|---|---|---|
| G01 | Seed fighter list + source plan | S | M08 | G02, G05, G07 | 1 |
| G02 | Knowledge-base ingestion (parse, chunk, embed, store) | M | G01, M06 | G03 | 2 |
| G03 | Retrieval + rerank | M | G02 | G04 | 3 |
| G04 | Stat-sheet builder + fighter API | M | G03, M05 | A05 (real research), D04 | 3 |
| G05 | Hand-verified seed stat sheets | M | G01, M05 | F07, demo | 2 |
| G06 | Traceability checker | S | G04 | benchmark | 4 |
| G07 | Benchmark matchup set | M | G01 | F07 | 2–4 |
| G08 | Showcase battles + fresh-clone run check | S | A05, M04 | demo, instructor | 4 |

G07 pairs with Felipe's F07: Gunnar builds the benchmark data, Felipe builds the runner that scores it.

---

## G01 · Seed fighter list + source plan · S (1)

**Goal:** Decide which fighters we support first and where their facts come from. No coding.
**Read first:** PRODUCT_SPEC step 2; ARCHITECTURE §5 (`StatSheet`, `StatName`), §11.

**Prompt for Claude Code:**
```text
Task G01 from docs/plan/lane-3-gunnar.md. Help me write docs/research.md. Do not write code.
1. Propose 25 seed fighters across categories (big predators, small animals good for swarms, herbivores, birds, reptiles, aquatic, insects, 2–3 dinosaurs, 3 generic historical human archetypes). For each: fighter_id slug, display name, default variant, category, habitat, and the Wikipedia article title. Include classics: house cat, golden retriever, grizzly bear, gray wolf, African elephant, honey badger, chimpanzee, bald eagle, saltwater crocodile, great white shark, army ant, Tyrannosaurus rex, Roman legionary.
2. For each StatName, explain in plain English what it means, its unit, where it usually appears in Wikipedia/Wikidata or the trait datasets, and what we do when it's missing (category default). Separate the seven physical stats (sourced or estimated) from the three behavioral stats (aggression_0_1, group_tactics_0_1, armor_0_1), which no source measures: write a rubric for each with 5 levels and one-line descriptions plus example animals (e.g. aggression 1 = flees from almost everything, 5 = attacks animals larger than itself), so every "assumption" value cites a rubric level.
3. The source policy, starting from the recommended datasets in docs/DECISIONS.md (D-20): Wikipedia Structured Contents (wikimedia/structured-wikipedia on Hugging Face) as the main text source, FineWiki as backup, Wikidata for referenced numbers, PanTHERIA and AnimalTraits for body mass and size, and optionally the TreeOfLife taxonomy metadata for name normalization. For each: what we take, license, and how we attribute. Not allowed: forums, fan wikis, AI-generated pages, and any dataset whose card says values were AI-generated or unsourced.
4. A short "variants" rule: what default we pick when a user says just "bear" or "shark".
Show me the draft, I'll edit it, then commit.
```

**Acceptance criteria**
- [ ] 25 seed fighters with slugs, variants, categories, habitats, article titles
- [ ] Every `StatName` explained with unit, typical source, and fallback
- [ ] Source policy with licenses named
- [ ] Mike approves the list (it shapes the benchmark and demo)

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
6. The script is idempotent (re-running skips unchanged docs) and prints a summary table: fighters, documents, chunks, facts, failures.
7. Tests on mocks: chunking, idempotency, a fighter whose article is missing (logged, not fatal).
Run it live for the 25 seed fighters and paste the summary in the PR. Do not commit anything under data/kb/.
```

**Acceptance criteria**
- [ ] `uv run python -m scripts.ingest_seed` builds the index for all seed fighters
- [ ] Re-running is fast and changes nothing
- [ ] Wikidata facts stored with property IDs and references
- [ ] Nothing under `data/kb/` or `data/app.db` committed

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
- [ ] `evidence_for` returns ranked passages with URL + exact text
- [ ] hit@5 ≥ 80% on the 15 live cases (result in the PR)
- [ ] Reranker outage falls back gracefully
- [ ] On-demand ingestion works for one non-seed fighter

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
   c. Structured Decisions extraction from evidence_for(...) passages (prompt backend/prompts/stat_extract.md): the model must return value, unit, and the exact quote; code converts units (research/units.py) and accepts the value only if the number appears in the quote and the quote appears in the passage;
   d. derived by code from other stats (e.g. size from mass), documented in the note;
   e. category default from research/defaults.py (is_estimate=True, confidence low).
2. Live StructuredLLM adapter in providers/live/structured.py per docs/providers.md.
3. Cache sheets in the stat_sheets table keyed by fighter_id + sheet_hash; GET /api/fighters?q= and GET /api/fighters/{fighter_id}.
4. Sanity bounds per stat (e.g. mass 0.000001–100,000 kg); out-of-bounds values are rejected and logged.
5. Tests on mocks: each preference level, a rejected quote mismatch, unit conversion (lb, km/h, ft), and a fighter with zero evidence (all estimates).
```

**Acceptance criteria**
- [ ] Every value has a source + quote, or is labeled an estimate by code
- [ ] No model-produced number is accepted without a verified quote
- [ ] Fighter API returns cached sheets; orchestrator stub can be swapped for the real function

---

## G05 · Hand-verified seed stat sheets · M (2)

**Goal:** Fifteen gold-standard stat sheets the demo, the benchmark, and Mike's AI evaluation (M09) can trust. Mostly careful reading, little code.
**Order and timing:** the five showcase fighters first (by Sat Nov 14, before your research pipeline exists, so these answers are independent of it), then the other ten by Wed Nov 18.
**Read first:** `docs/research.md`; ARCHITECTURE §5 (`StatSheet`).

**Prompt for Claude Code:**
```text
Task G05 from docs/plan/lane-3-gunnar.md. Help me create hand-verified stat sheets for the first 15 seed fighters in docs/research.md, as data/seed/fighters/<fighter_id>.json, valid against the StatSheet model.
Start with the five showcase fighters (docs/PRODUCT_SPEC.md section 9), then the rest. For each fighter, work one physical stat at a time (mass, size, speed, attack force, attack rate, reach, endurance): open the source (Wikipedia, Wikidata, a trait dataset, or the paper it cites), show me the exact sentence and the number, convert units, and wait for me to confirm before writing it. Use method "hand_verified" with the real URL and quote, and a low/high range if the source gives one. If no reliable source exists, use the category default with is_estimate=true and explain why in note. For the three behavioral stats, use method "assumption" with the rubric level from docs/research.md in note — never "hand_verified".
Add a test that every file validates and that no hand_verified value lacks a source. At the end, show me a table of fighters x stats with H (hand-verified) or E (estimate).
```

**Acceptance criteria**
- [ ] Five showcase sheets merged by Nov 14; all 15 by Nov 18; all validate
- [ ] Every hand_verified value has URL + quote; behavioral stats are "assumption" with a rubric level
- [ ] At most 2 of the 7 physical stats are estimates per fighter; coverage table in the PR

---

## G06 · Traceability checker · S (1)

**Goal:** Prove the promise "every stat on screen links to its source."
**Hermes task (DECISIONS D-02):** build this one with the course's Hermes Agent (port 9000) instead of Claude Code, with Mike pairing. Treat it as a comparison: note in docs/build-log.md how long it took, what went well or badly, and how it compared with Claude Code, with screenshots. Same branch, PR, and review rules apply.
**Prompt for Claude Code:**
```text
Task G06 from docs/plan/lane-3-gunnar.md. Build backend/app/research/trace.py and a test.
check_battle(record: BattleRecord) -> TraceReport: for every StatValue in every stat sheet, verify: non-estimates have a source with URL and quote; extracted quotes still appear in the stored document text; estimates have method category_default or derived. Also scan all Script lines for numbers not present in the stat sheets or result (reuse A06's guard if it has landed).
Add backend/scripts/trace_report.py that runs the check on every stored battle and prints a summary; the benchmark (F07) calls it. Tests on fixtures: a clean battle passes, a tampered quote fails.
```

**Acceptance criteria**
- [ ] Clean fixture passes; tampered fixture fails with a clear message
- [ ] Report reachable from the benchmark runner

---

## G07 · Benchmark matchup set · M (2)

**Goal:** A fair test set with "expert answers," so we can measure whether the simulator is sensible.
**Read first:** PRODUCT_SPEC "Evaluation"; DECISIONS D-10.

**Prompt for Claude Code:**
```text
Task G07 from docs/plan/lane-3-gunnar.md. Help me build data/benchmark/matchups.yaml. No app code.
1. 30 matchups using seed fighters (then move 10 of them, a mix of all three groups, into data/benchmark/heldout.yaml and don't look at their results while anyone tunes the engine — they're our honest test): 15 "obvious" (outcome follows from size/biology, e.g. house cat vs gray wolf), 10 "documented" (a zoologist, museum, or published source states a view — record the citation), 5 "count" cases where the expected fair-fight count range is known roughly (e.g. how many house cats to match one wolf).
2. Each entry: id, fighters (entity, count, variant), terrain, expected_winner (0, 1, or draw), confidence (high/medium), expected_fair_count range if any, source URL or "obvious: <one-line reason>".
3. Write docs/benchmark.md: how the set was built, what counts as a pass (favorite matches expected_winner; for high-confidence cases the favorite's probability ≥ 0.7), and known weaknesses.
Show me the draft before committing.
```

**Acceptance criteria**
- [ ] 30 entries, each with a reason or citation
- [ ] Pass rules written down before we run the simulator against it
- [ ] 10 matchups sealed in `data/benchmark/heldout.yaml` (held out from tuning)

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
- [ ] `data/showcase/` committed, under 20 MB, five battles
- [ ] A fresh clone + `npm start` shows them at http://localhost:8000 (Windows: Gunnar, Mac: Mike)
- [ ] Mock mode with an empty `.env` still opens the app
- [ ] README "For the instructor" steps corrected from the fresh-clone run
