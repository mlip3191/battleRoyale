# Lane 3 — Gunnar: Research & Knowledge Base

**Total effort: 13 points.** Gunnar owns the facts: where they come from, how they are retrieved, how they become a stat sheet, and how we prove every number is sourced. Also owns the benchmark set and the Docker setup.

| ID | Task | Size | Depends on | Blocks | Wave |
|---|---|---|---|---|---|
| G01 | Seed fighter list + source plan | S | M08 | G02, G05, G07 | 1 |
| G02 | Knowledge-base ingestion (parse, chunk, embed, store) | M | G01, M06 | G03 | 2 |
| G03 | Retrieval + rerank | M | G02 | G04 | 3 |
| G04 | Stat-sheet builder + fighter API | M | G03, M05 | A05 (real research), D04 | 3 |
| G05 | Hand-verified seed stat sheets | M | G01, M05 | F07, demo | 2 |
| G06 | Traceability checker | S | G04 | benchmark | 4 |
| G07 | Benchmark matchup set | M | G01 | F07 | 2–4 |
| G08 | Docker Compose one-command run | S | M04 | demo | 4 |

G07 pairs with Felipe's F07: Gunnar builds the benchmark data, Felipe builds the runner that scores it.

---

## G01 · Seed fighter list + source plan · S (1)

**Goal:** Decide which fighters we support first and where their facts come from. No coding.
**Read first:** PRODUCT_SPEC step 2; ARCHITECTURE §5 (`StatSheet`, `StatName`), §11.

**Prompt for Claude Code:**
```text
Task G01 from docs/plan/lane-3-gunnar.md. Help me write docs/research.md. Do not write code.
1. Propose 25 seed fighters across categories (big predators, small animals good for swarms, herbivores, birds, reptiles, aquatic, insects, 2–3 dinosaurs, 3 generic historical human archetypes). For each: fighter_id slug, display name, default variant, category, habitat, and the Wikipedia article title. Include classics: house cat, golden retriever, grizzly bear, gray wolf, African elephant, honey badger, chimpanzee, bald eagle, saltwater crocodile, great white shark, army ant, Tyrannosaurus rex, Roman legionary.
2. For each StatName, explain in plain English what it means, its unit, where it usually appears in Wikipedia/Wikidata (e.g. Wikidata property for mass), and what we do when it's missing (category default).
3. The source policy: allowed sources (Wikipedia, Wikidata, the Hugging Face datasets we choose — name them and their licenses), how we attribute (CC BY-SA), and what is not allowed (forums, AI-generated pages, fan wikis).
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
1. For each seed fighter in docs/research.md (store the list as data/seed/fighters.yaml so code can read it): fetch the Wikipedia article (REST API, plain text or HTML) and the Wikidata entity JSON (no key needed; send a descriptive User-Agent with the project name, not a personal email). Save raw files under data/kb/ (gitignored) with title, URL, license, retrieved_at.
2. Parse HTML/PDF through the DocParser provider (port 9005) when it is HTML or PDF; plain text skips parsing.
3. Chunk text (~800 characters, 100 overlap, keep section headings as chunk metadata), embed with the Embedder provider (port 9002) in batches, and store in SQLite: documents, chunks, and a sqlite-vec virtual table chunks_vec. Add the migration file in backend/app/db/migrations/.
4. Pull structured Wikidata facts too (mass, length, speed where present) into a wikidata_facts table with the property ID, value, unit, and reference — these are high-confidence sources for G04.
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

**Goal:** Fifteen gold-standard stat sheets the demo and the benchmark can trust. Mostly careful reading, little code.
**Read first:** `docs/research.md`; ARCHITECTURE §5 (`StatSheet`).

**Prompt for Claude Code:**
```text
Task G05 from docs/plan/lane-3-gunnar.md. Help me create hand-verified stat sheets for the first 15 seed fighters in docs/research.md, as data/seed/fighters/<fighter_id>.json, valid against the StatSheet model.
For each fighter, work one stat at a time: open the source (Wikipedia, Wikidata, or the paper it cites), show me the exact sentence and the number, convert units, and wait for me to confirm before writing it. Use method "hand_verified" and the real URL and quote. If no reliable source exists for a stat, use the category default with is_estimate=true and explain why in note.
Add a test that every file validates and that no hand_verified value lacks a source. At the end, show me a table of fighters x stats with H (hand-verified) or E (estimate).
```

**Acceptance criteria**
- [ ] 15 sheets, all validate, every non-estimate value has URL + quote
- [ ] Coverage table in the PR; at most 2 estimates per fighter

---

## G06 · Traceability checker · S (1)

**Goal:** Prove the promise "every stat on screen links to its source."
**Hermes task (DECISIONS D-02):** build this one with the course's Hermes Agent (port 9000) instead of Claude Code, with Mike pairing. Keep screenshots of the session for the final report. Same branch, PR, and review rules apply.
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
1. 30 matchups using seed fighters: 15 "obvious" (outcome follows from size/biology, e.g. house cat vs gray wolf), 10 "documented" (a zoologist, museum, or published source states a view — record the citation), 5 "count" cases where the expected fair-fight count range is known roughly (e.g. how many house cats to match one wolf).
2. Each entry: id, fighters (entity, count, variant), terrain, expected_winner (0, 1, or draw), confidence (high/medium), expected_fair_count range if any, source URL or "obvious: <one-line reason>".
3. Write docs/benchmark.md: how the set was built, what counts as a pass (favorite matches expected_winner; for high-confidence cases the favorite's probability ≥ 0.7), and known weaknesses.
Show me the draft before committing.
```

**Acceptance criteria**
- [ ] 30 entries, each with a reason or citation
- [ ] Pass rules written down before we run the simulator against it

---

## G08 · Docker Compose one-command run · S (1)

**Goal:** `docker compose up` gives anyone a working app for the demo.
**Prompt for Claude Code:**
```text
Task G08 from docs/plan/lane-3-gunnar.md. Create backend/Dockerfile (uv, Python 3.12, non-root user), frontend/Dockerfile (build with Node 24, serve the built files), and docker-compose.yml with services backend and frontend, env_file .env, a volume for ./data, and health checks. The frontend proxies /api and /media to the backend. Course endpoints are public URLs (DECISIONS D-03), so containers reach them directly; pass them in through .env. Add "docker:up" and "docker:down" scripts to the root package.json and a "Run with Docker" section in README.md. Test on my machine and tell me whether it was Windows or Mac; ask a teammate on the other OS to test it in their review.
```

**Acceptance criteria**
- [ ] `docker compose up` serves the app at http://localhost:8080 (or the documented port)
- [ ] Data persists across restarts; tested on both Windows and Mac
