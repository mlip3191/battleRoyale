# Architecture — Battle Royale

> Status: **Design baseline v1** (Phase 0). Owner: Mike (PM). Changes to this file go through a normal PR and need PM approval.
> Read with: [PRODUCT_SPEC.md](PRODUCT_SPEC.md) (what we build) · [TEAM_PROCESS.md](TEAM_PROCESS.md) (how we work) · [DECISIONS.md](DECISIONS.md) (why).

## 1. Principles

1. **Corny voice, serious brain.** Language models write words. Code decides outcomes. No language model invents a number that ends up on screen or in the simulation.
2. **Every number is traceable.** Each stat carries a source and a confidence level, or is labeled an estimate made by code.
3. **Contracts first.** All modules talk through the Pydantic models in `backend/app/models/`. Those models are the only shared surface, so the five lanes can build in parallel.
4. **Mock-first providers.** Every course endpoint has a mock twin. The whole app runs, and CI passes, with `PROVIDER_MODE=mock` and no network.
5. **Graceful degradation.** If audio, music, or images fail, the battle still finishes with text, captions, and placeholder sprites.
6. **Deterministic and cached.** Same matchup + same stat sheets + same seed → same result. Stat sheets and media are cached so repeat battles are fast and identical.

## 2. Tech stack (pinned)

| Layer | Choice | Version pin | Notes |
|---|---|---|---|
| Backend language | Python | 3.12 (`backend/.python-version`) | |
| Python packaging | uv | latest, `uv.lock` committed | `uv sync`, `uv run …` work the same on Windows and Mac |
| Web API | FastAPI + Uvicorn | per `uv.lock` | OpenAPI schema drives front-end types |
| Validation | Pydantic v2 + pydantic-settings | per `uv.lock` | all contracts + config |
| Database | SQLite (WAL mode) + sqlite-vec | per `uv.lock` | single file `data/app.db` (gitignored) |
| HTTP client | httpx (async) | per `uv.lock` | used only inside `providers/` |
| Backend tests | pytest, pytest-asyncio, hypothesis | | property tests for the simulation; `conftest.py` forces mock mode |
| Backend lint/format | ruff | | `ruff check`, `ruff format` |
| Front-end runtime | Node.js | 26 LTS (`.nvmrc`) | |
| Front end | React + Vite + TypeScript | per `package-lock.json` | |
| Game engine | Phaser 3 | per `package-lock.json` | replays the event log |
| Front-end tests | Vitest + Testing Library | | Playwright e2e is a later task |
| Front-end lint/format | ESLint + Prettier | | |
| API types | openapi-typescript | | generated from the backend schema, never hand-written |
| One-command run | `npm start` | — | builds the front end; FastAPI serves it plus the API on :8000. No Docker (D-25) |
| Task runner | root `package.json` scripts | | cross-platform: no bash- or PowerShell-only scripts |

**Banned without a PM-approved issue:** LangChain/LlamaIndex (too heavy for our needs), any paid API SDK, any new database, any CSS framework (D-11), any library that calls a model provider directly from the front end.

## 3. Repository layout

```
battleRoyale/
├── INIT.md                       # Phase 0: the one document that initializes the project
├── CLAUDE.md                     # rules every Claude Code session reads first   (critical)
├── .gitattributes                # LF line endings (keeps the git hook working on Windows) (critical)
├── README.md
├── package.json                  # root task runner: setup, dev, test, lint, check (critical)
├── .env.example                  # every config variable, placeholder values      (critical)
├── .gitignore  .gitattributes  .editorconfig  .nvmrc                              (critical)
├── .githooks/pre-commit          # shared secret/large-file guard                 (critical)
├── scripts/                      # check-env.mjs (checks .env without showing values), setup-check.mjs (D01)
├── .claude/                      # shared Claude Code config                      (critical)
│   ├── settings.json             # permissions + hooks (task M03)
│   ├── agents/code-reviewer.md   # QA reviewer subagent (review and self-check modes)
│   ├── qa/checklist.md           # the one QA rulebook: bot, /review, and /qa
│   ├── commands/review.md, qa.md, new-issue.md
│   └── skills/review-prs/        # "what can I review?" skill
├── .github/                      # workflows, templates, CODEOWNERS               (critical)
├── backend/
│   ├── pyproject.toml  uv.lock  .python-version                                   (critical)
│   ├── app/
│   │   ├── main.py               # FastAPI app factory, routers, CORS
│   │   ├── config.py             # Settings (pydantic-settings) — only place that reads env vars
│   │   ├── models/               # SHARED CONTRACTS (task M05)                      (critical)
│   │   ├── providers/            # one adapter per course endpoint + mocks (M06)
│   │   ├── safety/               # moderation + blocklists (A04)
│   │   ├── intake/               # step 1: matchup parsing + clarification (A02, D08)
│   │   ├── research/             # step 2: ingest, retrieve, rerank, stat sheets (G02–G06)
│   │   ├── simulation/           # step 3 + 7 + 8-sim: Monte Carlo engine (F01–F06)
│   │   ├── narration/            # steps 4–5 text: intro + play-by-play scripts (A06)
│   │   ├── media/                # steps 5–6 assets: tts, music, images (A07, A08)
│   │   ├── pipeline/             # orchestrator + stage runner + progress events (A05)
│   │   ├── api/                  # HTTP routes (thin; call pipeline/)
│   │   └── db/                   # sqlite connection, migrations, repositories
│   ├── prompts/                  # versioned prompt templates (*.md), never inline strings
│   ├── scripts/                  # ingest_seed.py, smoke_providers.py, run_benchmark.py
│   └── tests/                    # unit/, contract/, golden/, property/, fixtures/
├── frontend/
│   ├── package.json  package-lock.json                                             (critical)
│   └── src/
│       ├── api/                  # generated types + typed fetch client
│       ├── pages/                # Home (intake), Battle (broadcast), Results
│       ├── components/           # StatSheetCard, SourceBadge, ClarifyPrompt, AudioBar…
│       ├── game/                 # Phaser scenes: BattleScene, PreloadScene
│       └── fixtures/             # copies of backend contract fixtures for offline UI work
├── data/
│   ├── seed/fighters/*.json      # hand-verified stat sheets (committed)
│   ├── showcase/                 # five demo battles + small media (committed, D-24)
│   ├── benchmark/matchups.yaml   # evaluation set (committed)
│   ├── app.db, kb/, media/       # generated at runtime (gitignored)
└── docs/                         # this documentation set
```

## 4. The battle pipeline

```
 user text
    │
    ▼
[1 Intake] ──blocked──► refusal message
    │  └──vague──► one clarifying question ──► user answer ──┐
    ▼                                                         │
 Matchup ◄────────────────────────────────────────────────────┘
    │
    ▼
[2 Research] per fighter: cache hit? ─yes─► StatSheet
    │                      └no─► retrieve → rerank → extract (chat, JSON schema) → verify → StatSheet
    ▼
[3 Simulate] 1,000 seeded runs → SimulationResult + representative EventLog
    │
    ├──► [7 Summary + Fair fight]  (code only)          ──┐
    ├──► [8 Next challenger]  LLM ranks    → sim tests ───┤  text results ready → UI shows verdict
    ├──► [4 Intro script] + [5 Play-by-play script] (LLM) ┤
    │          └──► [5 TTS audio] [5 Music] (parallel) ───┤  media fills in progressively
    └──► [6 Sprites + battlefield] (image endpoint) ──────┘
                                   │
                                   ▼
                      BattleRecord status = done
```

Stages run in the orchestrator (`pipeline/`). Each stage records `pending | running | done | failed | fallback`. Steps 4–8 start as soon as their inputs exist; media stages run concurrently. The verdict never waits for media.

### Stage budget (targets, measured in the benchmark run)

| Stage | Cached fighter | New fighter | On failure |
|---|---|---|---|
| 1 Intake | about 7 s typical, 25 s limit (D-52) | same | the parser asks the model at most twice (each call waits up to 15 s per step, with one retry); an outage or the 25 s limit returns a 503 "try again in a moment"; unusable replies ask the user to rephrase |
| 2 Research | ≤ 0.5 s | ≤ 45 s | fall back to seed sheet or all-estimate sheet with a banner; size-reference entities are researched too |
| 3 Simulate (1,000 runs) | ≤ 3 s | — | must not fail; it is pure code |
| 4–5 Scripts | ≤ 10 s | — | template-based fallback script |
| 5 Audio + music | ≤ 60 s | — | captions only / no music |
| 6 Images | ≤ 60 s (cached per fighter) | — | placeholder shapes in the fighter's color |
| 7 Fair fight | ≤ 5 s | — | "no fair fight within limits" |
| 8 Next challenger | ≤ 10 s | — | candidates come only from seed/cached fighters (no new research), so the budget holds; fallback: closest odds from the seed list |

## 5. Shared contracts (backend/app/models)

These are the **only** shapes passed between lanes. Field names below are normative; task M05 implements them, exports JSON Schema to `backend/app/models/schema/`, and writes one valid fixture per model to `backend/tests/fixtures/contracts/`. Changing a contract after M05 needs an issue labelled `contract-change` and PM approval, because it affects every lane.

```python
# terrain.py
class Terrain(StrEnum): ARENA="arena"; OPEN_FIELD="open_field"; FOREST="forest"; WATER="water"; SHORELINE="shoreline"; URBAN="urban"; MOUNTAIN="mountain"

# matchup.py
class FighterRequest(BaseModel):
    entity: str                 # normalized name, e.g. "grizzly bear"
    count: int = Field(1, ge=1, le=10_000)
    variant: str | None = None  # e.g. "adult male", "polar"
    size_reference: str | None = None  # "horse-sized duck" -> entity "duck", size_reference "horse".
                                # The scale factor is computed by CODE from both stat sheets'
                                # mass_kg (reference mass / entity mass); the model only names the reference.
    raw: str                    # the user's words for this fighter

class Matchup(BaseModel):
    fighters: list[FighterRequest] = Field(min_length=2, max_length=2)   # MVP: exactly 2
    terrain: Terrain = Terrain.ARENA
    raw_text: str
    assumptions: list[str] = []   # e.g. "Assumed adult male grizzly"

class IntakeResult(BaseModel):
    status: Literal["ok", "clarify", "blocked"]
    matchup: Matchup | None = None
    question: str | None = None           # when status == "clarify"
    options: list[str] = []               # 2–4 suggested answers
    pending_id: str | None = None
    blocked_reason: Literal["real_person","minor","sexual","hate","self_harm","copyrighted_character",
                            "deity","weapon","out_of_scope","nonsense","other"] | None = None
                            # deity: named gods/religious figures; weapon: modern firearms, explosives, WMD;
                            # out_of_scope: abstract ideas, places, landforms, celestial bodies
    message: str | None = None            # user-facing text

# stats.py
class Confidence(StrEnum): HIGH="high"; MEDIUM="medium"; LOW="low"
class Source(BaseModel):
    title: str; url: HttpUrl; quote: str  # the exact evidence span the value came from
    retrieved_at: datetime; license: str = "CC BY-SA 4.0"

class StatValue(BaseModel):
    value: float; unit: str
    source: Source | None = None
    confidence: Confidence
    is_estimate: bool                      # True ⇒ not from a source (category_default or assumption)
    method: Literal["extracted", "derived", "category_default", "hand_verified", "assumption"]
    low: float | None = None               # plausible range used for uncertainty sampling;
    high: float | None = None              # filled by code (from sources if given, else by confidence)
    note: str | None = None                # required for "assumption": the rubric level and why

class StatName(StrEnum):
    MASS="mass_kg"; SIZE="size_m"; SPEED="top_speed_mps"; ATTACK_FORCE="attack_force_n"
    ATTACK_RATE="attacks_per_s"; REACH="reach_m"; ARMOR="armor_0_1"; ENDURANCE="endurance_s"
    AGGRESSION="aggression_0_1"; GROUP_TACTICS="group_tactics_0_1"

class Habitat(StrEnum): LAND="land"; WATER="water"; AIR="air"; AMPHIBIOUS="amphibious"

class Body(StrEnum):    # how it fights, not its biology
    LIVING="living"     # animals, human archetypes, mythical creatures: tire, have morale, can retreat or flee
    MACHINE="machine"   # vehicles and robots: no morale (never retreat); stop when endurance_s (operating time) runs out
    INERT="inert"       # objects and plants: never move toward anyone; hit back only if they have an attack in reach

class Ability(StrEnum): # mythical creatures only; each has one documented engine effect (F08)
    FLIGHT="flight"; BREATH_WEAPON="breath_weapon"; REGENERATION="regeneration"; EXTRA_HEADS="extra_heads"

class LoreProfile(BaseModel):              # mythical creatures only
    body_analog: str                       # real fighter whose sourced stats are the base, e.g. "saltwater crocodile"
    size_analog: str | None = None         # real fighter it is scaled to, e.g. "African elephant"; code computes k
    abilities: list[Ability] = []
    heads: int | None = Field(None, ge=2, le=9)   # only with extra_heads; quote-verified from lore, else None
    source: Source                         # the sentence in the myth's article that justifies the analogs and abilities

class StatSheet(BaseModel):
    fighter_id: str                        # slug: "grizzly-bear" (default variant; others add "--variant", e.g. "grizzly-bear--juvenile")
    display_name: str
    media_name: str                        # generic, brand-free name used in image/music prompts ("electric pickup truck")
    category: Literal["mammal","bird","reptile","amphibian","fish","insect","arachnid","mollusk","dinosaur",
                      "human_archetype","mythical","plant","vehicle","machine","object","other"]
    body: Body
    habitat: Habitat
    weapons: list[Literal["teeth","claws","horns","hooves","venom","constriction","tusks","beak","sting",
                          "weapon_melee","weapon_ranged","ramming","crushing","spines","breath_weapon","none"]]
    lore: LoreProfile | None = None        # required when category == "mythical", otherwise None
    stats: dict[StatName, StatValue]       # every StatName must be present
    schema_version: int = 1
    sheet_hash: str                        # hash of stats, used in cache + seed

# simulation.py
class EventType(StrEnum): APPROACH="approach"; ATTACK="attack"; HIT="hit"; MISS="miss"; KO="ko"; RETREAT="retreat"; FLEE="flee"; STALEMATE="stalemate"; END="end"

class FightEvent(BaseModel):
    t: float                               # seconds since start
    type: EventType
    side: Literal[0, 1]
    actor: int | None = None               # index within side, or None for group events
    target: int | None = None
    group_size: int = 1                    # >1 for aggregated swarm events
    damage: float | None = None
    text_hint: str                         # short neutral description for narration, e.g. "bite lands"

class SimulationResult(BaseModel):
    seed: int; runs: int
    win_prob: tuple[float, float]; draw_prob: float
    win_prob_ci95: tuple[tuple[float,float], tuple[float,float]]
    mean_survivors: tuple[float, float]; mean_duration_s: float
    outcome: Literal["win_0","win_1","draw","no_contest"]   # most likely; no_contest = cannot engage
    deciding_factor: StatName | Literal["numbers","terrain","habitat","abilities"]
    deciding_factor_explainer: str        # plain-language, generated by code template
    representative_log: list[FightEvent]   # capped at 300 events

class FairFight(BaseModel):
    varied_side: Literal[0, 1]; count: int | None   # None ⇒ no fair fight within limits
    win_prob_at_count: float | None; message: str

class ChallengerSuggestion(BaseModel):
    entity: str; tested_win_prob: float; reason: str

# narration.py
class ScriptLine(BaseModel):
    speaker: Literal["announcer","color_commentator"]; text: str
    at_event: int | None = None            # index into representative_log, for caption sync
class Script(BaseModel):
    kind: Literal["intro","play_by_play","outro"]; lines: list[ScriptLine]; fallback: bool = False

# media.py
class Asset(BaseModel):
    asset_id: str; kind: Literal["sprite","battlefield","narration_audio","music"]
    url: str; prompt_hash: str; fallback: bool = False
    script_kind: Literal["intro","play_by_play","outro"] | None = None

# battle.py
class StageStatus(BaseModel):
    stage: Literal["intake","research","simulate","summary","challenger","script","audio","music","images"]
    status: Literal["pending","running","done","failed","fallback"]; detail: str | None = None

class BattleRecord(BaseModel):
    battle_id: str; created_at: datetime
    matchup: Matchup
    stat_sheets: list[StatSheet] = []
    result: SimulationResult | None = None
    fair_fight: FairFight | None = None
    challenger: ChallengerSuggestion | None = None
    scripts: list[Script] = []
    assets: list[Asset] = []
    stages: list[StageStatus]
    status: Literal["running","done","failed"]

# api.py (small HTTP replies, §6)
class BattleCreated(BaseModel):  battle_id: str
class ShowcaseBattle(BaseModel): battle_id: str; title: str
class FighterMatch(BaseModel):   fighter_id: str; display_name: str; cached: bool
```

### The number rule, made precise

The proposal says "no language model sets a number." Because the chat model reads the evidence and extracts from it (D-41), the rule is:

| Method | Who produces the value | Allowed when |
|---|---|---|
| `extracted` | Chat model (JSON-schema mode) copies a number **and** the exact quote it came from | Code verifies the number (after unit conversion) appears in `source.quote`, and the quote appears in the retrieved passage. Otherwise the value is rejected. |
| `derived` | Code (e.g. size from mass via allometric formula) | An input stat exists; note says which formula |
| `category_default` | Code, from `backend/app/research/defaults.py` | No evidence found. `is_estimate=True`, confidence `low` |
| `hand_verified` | A teammate, in `data/seed/fighters/*.json` | Seed fighters only; source required |
| `assumption` | A teammate or code, from the written rubric in `docs/research.md` | (a) The behavioral stats that no source measures: `aggression_0_1`, `group_tactics_0_1`, `armor_0_1`; `note` cites the rubric level (e.g. "aggression level 4: territorial apex predator"). (b) **Every** stat of a mythical creature: code copies the `lore.body_analog`'s sourced sheet and scales it to `lore.size_analog` with the square-cube rules; `note` says so ("modeled on saltwater crocodile, scaled to African elephant mass"). Always `is_estimate=True`, confidence `low`. Shown in the UI with an "assumption" tag. |

**Honest scope of the claim:** the seven *physical* stats (mass, size, speed, attack force, attack rate, reach, endurance) are sourced or labeled estimates. Objects, vehicles, and machines follow the same rule (Wikipedia and Wikidata list their mass, size, and speed; what they don't list is a labeled estimate). Mythical creatures have no measurable stats, so every number is an assumption built by code from real animals the legend compares them to, and the UI says "according to legend". The three *behavioral* stats are documented assumptions, and the engine's constants (`simulation/constants.py`) cite their source or reasoning in `docs/simulation-model.md`. The results page and the Limitations material say so plainly.

**Ranges:** every `StatValue` gets `low`/`high`. If a source gives a range, use it; otherwise code sets ±10% (high confidence), ±25% (medium), ±50% (low, estimates and assumptions). The simulation samples each stat from its range on every run, so the reported win-probability interval reflects input uncertainty, not just Monte Carlo noise.

Unit conversion lives in code (`research/units.py`). The model returns the unit string it saw; code converts.

## 6. HTTP API (backend/app/api)

| Method + path | Body / query | Returns | Owner |
|---|---|---|---|
| `GET /api/health` | — | `{status, provider_mode, providers: {name: up/down/mock}}` | M06 |
| `POST /api/intake` | `{text}` | `IntakeResult` | A02 |
| `POST /api/intake/{pending_id}/answer` | `{answer}` | `IntakeResult` | D08 |
| `POST /api/battles` | `Matchup` | `202 BattleCreated` `{battle_id}` | A05 |
| `GET /api/battles/{id}` | — | `BattleRecord` (partial while running) | A05 |
| `GET /api/battles?showcase=true` | — | `list[ShowcaseBattle]` `[{battle_id, title}]` for the five saved showcase battles | G08 |
| `GET /api/battles/{id}/events` | — | Server-Sent Events: `StageStatus` updates; poll fallback every 1 s | A05 |
| `GET /api/fighters?q=` | search text | `list[FighterMatch]` `[{fighter_id, display_name, cached: bool}]` | G04 |
| `GET /api/fighters/{fighter_id}` | — | `StatSheet` | G04 |
| `GET /media/{asset_id}` | — | file | A07/A08 |

The front end only calls these. It never calls a course endpoint.

## 7. Provider layer (backend/app/providers)

One adapter per course endpoint, each behind an interface:

| Interface | Course endpoint | Port | Mock behavior |
|---|---|---|---|
| `ChatLLM.complete(messages, json_schema=None)` | Chat/Classification LLM | 9001 | canned responses keyed by prompt name + input hash, from `tests/fixtures/providers/` |
| `StructuredLLM.decide(state, questions, *, prompt_name)` | Structured Decisions | 9010 | first option per question with equal odds, unless a fixture in `tests/fixtures/providers/structured/<prompt_name>.json` overrides it (D-41: decisions only; stat extraction uses `ChatLLM` with `json_schema`) |
| `Embedder.embed(texts)` | Text Embeddings | 9002 | deterministic hash-based vectors (fixed dimension from config) |
| `Reranker.rerank(query, passages)` | Multimodal Reranking | `.env` | keyword-overlap score |
| `DocParser.parse(bytes, mime)` | Document Parsing | 9005 | returns plain text |
| `ImageGen.generate(prompt)` / `.edit(image, prompt)` | Image Generation & Editing | 9006 | colored silhouette PNG |
| `TTS.speak(text, voice_id)` | Text-to-Speech / Voice Cloning | `.env` | 1 s silent WAV per line |
| `MusicGen.compose(prompt, seconds)` | Music Generation | `.env` | silent track |
| `STT`, `MultimodalEmbedder` | stretch | `.env` | not built in MVP |
| *(not used by the app)* | Hermes Primary Model + Hermes Agent | 9000 | — |

Rules:
- `config.py` reads `PROVIDER_MODE` (`mock` | `live`) and one base URL per service (see `.env.example`). Nothing else reads environment variables.
- Every live call has a timeout and retries with backoff (by default `PROVIDER_TIMEOUT_S`=30 and 2 retries; intake's chat calls use `INTAKE_TIMEOUT_S`=15 and `INTAKE_RETRIES`=1, D-52), and logs latency but never logs payloads that could contain keys.
- `backend/scripts/smoke_providers.py` (task M06) calls each live endpoint once and writes what it learned (URL shape, auth, request/response format, latency) to `docs/providers.md`. Run it before building any live adapter beyond the chat LLM.
- CI and all automated tests run with `PROVIDER_MODE=mock` (`backend/tests/conftest.py` forces it and ignores `.env`). The endpoints are public URLs, but their keys never go to GitHub, and tests must not depend on them.
- Course endpoint URLs go in `.env`, never in code: they are public URLs, so anyone holding them could spend the course's quota.

## 8. Data and caching

| Table | Key | Purpose |
|---|---|---|
| `fighters` | `fighter_id` | canonical names, aliases, Wikidata QID, category |
| `documents` | `doc_id` | source title, URL, license, retrieved_at, raw text |
| `chunks` + `chunks_vec` (sqlite-vec) | `chunk_id` | passages + embeddings for retrieval |
| `stat_sheets` | `fighter_id`, `sheet_hash` | cached sheets; newest wins; seed sheets marked `hand_verified` |
| `battles` | `battle_id` | serialized `BattleRecord` |
| `assets` | `prompt_hash` | generated media paths; reused across battles |

- **Seed:** `simulation_seed = hash(matchup normalized, sheet_hash_0, sheet_hash_1, ENGINE_VERSION)`. Re-running a battle reproduces it exactly.
- **Knowledge base build:** `uv run python -m scripts.ingest_seed` downloads Wikipedia/Wikidata text for seed fighters into `data/kb/`, parses, chunks (≈800 characters, 100 overlap), embeds, and stores. Raw text is not committed (size + license); seed stat sheets are.
- **Migrations:** numbered SQL files in `backend/app/db/migrations/`, applied at startup.
- SQLite runs in WAL mode; one writer at a time is fine for a demo app.

## 9. Simulation model (backend/app/simulation)

Pure Python, no I/O, no providers. Lane owner: Felipe.

- **Inputs:** each of the ~1,000 runs samples every stat from its `low`–`high` range (seeded), so uncertain inputs widen the result's interval. Constants are documented with sources or reasoning in `docs/simulation-model.md` (F02).
- **Size references:** for a `size_reference` ("horse-sized duck"), code scales the duck's stat sheet to the horse's mass with square-cube rules (mass × k, strength × k^(2/3), speed per documented allometry) and records the scaling in the result.
- **Individuals:** each fighter instance has HP ∝ mass (square-cube: volume), damage per hit from `attack_force_n` scaled by mass^(2/3) (muscle cross-section), armor reduces damage, hit chance from speed and size ratio.
- **Numbers (Lanchester):** melee uses the linear law: only as many attackers engage one target as fit around it (`max_engagers = clamp((size_target/size_attacker)², 1, 8)`). Ranged weapons use the square law. Swarms above 200 individuals switch to aggregated "group" mode for speed.
- **Terrain/habitat:** a habitat mismatch (e.g. shark on land) applies speed and attack penalties; if neither side can reach the other the result is `no_contest`.
- **Behavior:** each side retreats when losses pass a morale threshold derived from `aggression_0_1`. Fights time out at 600 simulated seconds → draw.
- **Bodies (F08):** `living` fighters behave as above. `machine` fighters never retreat or flee and are "out of action" when `endurance_s` (operating time) runs out; `ramming` and `crushing` damage is derived by code from mass and speed (a documented momentum formula). Mounted guns on vehicles are not modeled (PG; we don't model real weapon effects). `inert` fighters never approach; they hit back only with an attack in reach (e.g. `spines` damage whoever bites a cactus). If neither side can damage the other, the result is `no_contest`; if one side can't finish the other in 600 s, it's a draw.
- **Abilities (mythical, F08):** `flight` lets a fighter engage air and land targets; `breath_weapon` is a ranged attack (square law); `regeneration` heals a share of HP per second; `extra_heads` multiplies attack rate by `heads` (default 3 when the lore gives no verified number). Every ability constant is labeled an assumption in `docs/simulation-model.md`.
- **Outputs:** win/draw probabilities with 95% intervals (labeled "range" in the UI; they include input uncertainty), survivors, duration, the representative run's event log (closest to the median outcome, capped at 300 events), and the deciding factor by one-at-a-time sensitivity (equalize one stat, re-run 200 times, biggest swing wins).
- **Fair fight:** vary the count of the side the user did not fix (default: the losing side) with doubling then binary search on integers, 200 runs per probe, max 20 probes, count cap 10,000; target |p − 0.5| ≤ 0.05.
- **Performance:** 1,000 runs for 1 v 1 in under 1 s; 100 v 1,000 under 3 s on a laptop.
- `ENGINE_VERSION` constant bumps whenever results would change; it is part of the seed.

## 10. Front end (frontend/)

- **Serving:** in development Vite serves the front end on :5173 and proxies `/api` and `/media`; with `npm start` the backend serves the built files from `frontend/dist` on :8000, falling back to `index.html` for front-end routes.
- Routes: `/` intake (text box, examples, clarification chips), `/battle/:id` (broadcast: intro card → Phaser arena + narration captions + music → verdict), `/battle/:id/results` (stats, stat sheets with source links, fair fight, next challenger button).
- State: a `useBattle(id)` hook subscribes to SSE and falls back to polling.
- **Phaser** lives in `src/game/`, mounted by one React component. `BattleScene` takes `representative_log` + asset URLs and plays events on a timeline; it never computes outcomes. Controls: play/pause, 1×/2×, skip to result, mute, reduced-motion mode (static frames).
- Every stat shown has a `SourceBadge`: link to the source, confidence dot, and an "estimate" tag when `is_estimate` ("assumption" when the method is `assumption`). Mythical fighters also get a `LoreCard`: what the legend compares them to, their abilities, and the quoted sentence with its link.
- Types come from `npm run gen:api` (openapi-typescript against the running backend or the exported schema).
- Works offline against `src/fixtures/` so UI work never waits on the backend.

## 11. Safety, security, and content

- **Blocked fighters:** named real people (checked two ways: LLM classifier, and Wikidata "instance of human (Q5)" lookup), anyone under 18 or "a child", sexual content, ethnic/religious/national groups, self-harm, real-world attack planning. Copyrighted fictional characters are blocked in MVP (see DECISIONS D-07).
- **Also blocked (D-38):** named deities and religious figures (`deity`); modern firearms, explosives, and weapons of mass destruction as fighters (`weapon`); copyrighted or trademarked characters, including named robots and vehicles from films, games, and toys (`copyrighted_character`); abstract ideas, places, landforms, and celestial bodies (`out_of_scope`, with a joke and a suggestion).
- **Allowed (D-38):** animals (living and extinct); generic historical human archetypes ("Roman legionary"); mythical and folklore creature *types* ("dragon", "kraken", "werewolf"); objects, plants, vehicles, and machines ("toaster", "saguaro cactus", "bulldozer", "main battle tank"). Brand-name products are allowed but drawn and scored under a generic `media_name` ("electric pickup truck"); named individual fictional characters are not.
- **Prompt injection:** user text is wrapped as data in every prompt; media and narration prompts use the resolved `display_name` from the stat sheet (validated against an allowlist of letters, digits, spaces, hyphens), never the raw user text; Wikipedia text fetched on demand is also treated as untrusted data; outputs are schema-validated; the simulation, not the model, decides the winner, so "make the duck win" cannot change a result.
- **Tone:** PG. Knockouts and retreats, no gore or blood descriptions. Announcer jokes never target groups of people.
- **Voice cloning:** only a voice whose owner gave written consent (e.g. a teammate). Never imitate a celebrity or real announcer.
- **Music and images:** prompts never name real artists, songs, franchises, characters, or brands; they use the stat sheet's `media_name`, checked against the same allowlist and a brand/franchise blocklist.
- **Attribution:** Wikipedia/Wikidata text is CC BY-SA / CC0; the results page lists sources with links and license.
- **Repo hygiene:** the repo is public (DECISIONS D-48), so no endpoint URLs, keys, or student data in commits, PRs, issues, or comments. See TEAM_PROCESS Step 8.

## 12. Testing strategy

| Level | Where | Runs in CI | What it proves |
|---|---|---|---|
| Contract | `backend/tests/contract/` | yes | fixtures validate against models; front-end fixtures match backend schema |
| Unit | `backend/tests/unit/`, `frontend/src/**/*.test.tsx` | yes | each module in isolation, mock providers |
| Property | `backend/tests/property/` (hypothesis) | yes | sim invariants: determinism, mirror ≈ 50/50, more fighters never lowers win rate |
| Golden | `backend/tests/golden/` | yes (mock) | prompt outputs parse; scripts contain no numbers not in the stat sheets |
| Live smoke | `scripts/smoke_providers.py` | no — run by hand | course endpoints reachable and shaped as expected |
| Benchmark | `scripts/run_benchmark.py` | no — run weekly | accuracy vs expert answers, traceability = 100% |
| E2E | Playwright (later) | yes (mock) | type a matchup → see a verdict |

## 13. Configuration (.env)

See `.env.example` for the full list with comments. Groups: app (`APP_ENV`, `PORT`, `FRONTEND_ORIGIN`), provider mode, one `*_URL` and `*_MODEL` per course service, the required `COURSE_API_KEY` plus optional per-service `<SERVICE>_API_KEY` overrides, simulation defaults (`SIM_RUNS`, `SIM_MAX_COUNT`), storage paths, and `VITE_*` front-end settings. `config.py` reads the **root** `.env` (resolved from the repo root, whatever the working folder), ignores keys it doesn't know, resolves relative paths against the repo root, and holds every key as a `SecretStr`. Vite reads the same root `.env` (`envDir: '..'`).

## 14. Edge cases the design must handle

| Case | Expected behavior | Owner |
|---|---|---|
| Vague fighter ("bear") | One clarifying question with 2–4 options; if the answer is still vague, pick the most common variant and add it to `assumptions` | A02/D08 |
| Unknown or made-up fighter | Block as `nonsense` with a friendly message, or (if plausible) all-estimate sheet with a red banner | A04/G04 |
| Everyday object ("a toaster vs a goose") | `body=inert`; mass and size sourced; the goose attacks, the toaster can't; draw if the goose can't break it in 600 s | G09/F08 |
| Inert vs inert ("a rock vs a sword") | `no_contest` with a joke: nobody can hurt anybody | F08 |
| Vehicle or machine ("a bulldozer vs 50 wolves") | `body=machine`; ramming/crushing from sourced mass and speed; never retreats; stops when operating time runs out | G09/F08 |
| Mythical creature ("a dragon vs a main battle tank") | Lore profile from `data/seed/mythical.yaml` or built on demand from the myth's article; every stat an "assumption"; "according to legend" in the UI and script | G09/F08 |
| Brand-name product ("a Cybertruck vs a rhino") | Allowed; stats from its article; sprite and music use the generic `media_name` | G09/A08 |
| Fictional character, deity, or firearm | Blocked as `copyrighted_character`, `deity`, or `weapon` with a friendly suggestion | A04 |
| Abstract or enormous ("Monday vs coffee", "the Moon vs a whale") | Blocked as `out_of_scope` with a joke and a suggestion | A04 |
| Mirror match ("wolf vs wolf") | ~50/50; property test enforces it | F07 |
| Huge counts ("1,000,000 ants") | Clamp to 10,000 with an assumption note; swarm mode | A02/F02 |
| Count words ("a dozen", "half a horse") | Parse words to integers; fractions rejected with a joke | A02 |
| More than two fighters | Explain MVP is two-sided; offer to group ("3 wolves" is one side) | A02 |
| Habitat mismatch (shark vs lion) | Terrain chosen by user wins; if none, pick shoreline and note it; `no_contest` if no engagement possible | F03 |
| Extreme size gap (ant vs whale) | Valid; fair-fight search reports "no fair fight within 10,000" | F05 |
| Real person / child / group of people | Blocked with reason; never researched | A04 |
| Prompt injection in input | Treated as text; result unchanged; golden test | A04 |
| A course endpoint down | Stage → `fallback`; verdict still shown; health page shows which | A05/M06 |
| Same battle requested twice | Cache returns identical result instantly | A05/G04 |
| Two users at once | Each battle runs as its own background task; SQLite WAL handles writes | A05 |
| Stat missing for one fighter | Category default, flagged estimate; counted in the "estimate" banner | G04 |
| Source quote doesn't contain the number | Value rejected, falls back to estimate; logged | G04/G06 |
| Draw / timeout | Verdict "draw"; next challenger still suggested | F04/A05 |
| Screen reader / no sound | Captions always on; reduced-motion mode; mute | D05/D07 |
