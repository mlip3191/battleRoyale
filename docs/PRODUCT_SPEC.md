# Product Spec — Battle Royale: The Science-Backed Fight Simulator

> Source: the approved project proposal (MBAX 6418 AI Business Solutions, Oct 26, 2026), expanded with the details the team needs to build it. Where this spec adds something the proposal didn't say, it is marked **[added]**. Open questions live in [DECISIONS.md](DECISIONS.md).

## 1. The situation

"Who would win" debates are a lasting online pastime, from forum threads and YouTube breakdowns to memes like *100 duck-sized horses versus one horse-sized duck*. The *Who Would Win?* children's book series shows the same hook works for teaching. Yet most online answers rest on myths and made-up statistics. General-purpose chatbots take the question, but they invent numbers, cite nothing, and offer no visual payoff. That gap is an edutainment opportunity: people will happily learn real biology, history, and physics when it is framed as a fight.

## 2. The product

A web app built on one principle: **corny voice, serious brain.** Users name two combatants in plain language. The app researches each one from vetted sources into a cited stat sheet, and a simulation written in code decides the outcome. No language model sets a number.

The result is staged as a cheesy late-night sports broadcast: an announcer, a soundtrack, and a crude animated battle. Users leave with a defensible verdict, the reasoning behind it, the quantity needed for a fair fight, and a suggested next challenger. Every stat on screen links to its source, and gaps are labeled as estimates.

**Who it's for [added]:** curious teens and adults, teachers looking for a hook, and anyone settling a group-chat argument. Desktop browser first; mobile layout is a "Should."

## 2a. Business case [added]

**The problem in business terms.** "Who would win" content is a proven attention magnet (the *Who Would Win?* book series, millions of YouTube views on animal-matchup videos, endless forum threads), but the answers people consume are unsourced, and general chatbots invent numbers with confidence. There's no product that is at once **sourced, transparent about uncertainty, and entertaining**.

**Who it's for, and the value to each:**

| Segment | Job to be done | What they get |
|---|---|---|
| Teachers (grades 4–12) and museum/zoo educators | A hook that gets students reading about biology, physics, and history | A shareable verdict with every number linked to its source and the reasoning shown; a "fair fight" question that invites math |
| Readers of *Who Would Win?*-style books and their parents | Settle debates with something better than a guess | A fun broadcast plus a verdict they can defend |
| Content creators (YouTube, TikTok) | Fast, defensible matchup content | Ready-made stat sheets, verdicts, and short clips with citations |
| Group chats and the curious | Settle the argument | A link to a sourced result |

**How it compares:**

| | Sourced numbers | Transparent about uncertainty | Entertaining | Reproducible |
|---|---|---|---|---|
| General chatbot (e.g. ChatGPT) | rarely; may invent | no | somewhat | no |
| YouTube matchup videos | sometimes | rarely | yes | no |
| Forums / Reddit | rarely | no | yes | no |
| **Battle Royale** | **yes, with links and quotes** | **yes: ranges, estimates and assumptions labeled** | **yes: broadcast + animation** | **yes: same input, same result** |

**Business model options** (not built this term; discussed as next steps): free consumer app with sponsored "matchup of the week"; classroom licenses with lesson plans and teacher dashboards; a licensed API/clip generator for creators and museums.

**Unit economics.** Every battle uses a known number of endpoint calls (parse, retrieve/extract per new fighter, scripts, audio, music, images). Caching makes repeat and popular matchups nearly free: stat sheets and sprites are generated once per fighter. M09 measures calls per battle and cache hit rate, so the deck can show cost per battle for a new vs. a repeat matchup.

**Success metrics:** benchmark accuracy on the held-out set; share of displayed stats that are sourced (vs. estimated); live intake and safety accuracy; time to verdict; and, from usability sessions, "would you trust it?" and "would you share it?"

## 3. Scope

| Priority | Feature |
|---|---|
| **Must (MVP)** | Two-sided matchups with counts and terrain · any physical fighter: animals, historical archetypes, objects, plants, vehicles, machines, and mythical creatures (D-38) · one clarifying question · safety blocking · cited stat sheets with estimate labels · Monte Carlo verdict with win % · deciding factor · fair-fight count · next challenger · announcer captions · crude animation replaying the event log · results page with sources · runs with one command |
| **Should** | Announcer voice (TTS) · soundtrack · generated sprites and battlefields · benchmark ≥ 80% on "obvious" cases · shareable result link — the results URL reopens the stored battle **[added]** |
| **Could (stretch)** | 3+ combatants · voice input (speech-to-text) · photo-based fighters (multimodal embeddings) · mobile layout |
| **Won't (this term)** | User accounts · real people, named fictional characters, deities, or firearms as fighters · paid APIs · public deployment beyond the demo |

## 4. The eight-step pipeline

GenAI handles language, retrieval, and media; plain code handles the math. Owners are lane tasks (see [plan/LANES.md](plan/LANES.md)).

### Step 1 — Matchup intake (Adam: A02, A04; Dillon: D08)
The chat LLM (port 9001) parses free text into a structured matchup: entity, count, variant, and terrain. If a fighter is vague, it asks **one** clarifying question ("grizzly or polar bear?"). The same model, plus code rules and a Wikidata check **[added]**, blocks real people and inappropriate requests.
- **[added]** Counts, number words, clamping (max 10,000 per side), and normalization are done by code, not the model.
- **[added]** Size phrases like "horse-sized duck" are parsed into a `size_reference`; the scale factor is computed by code from both fighters' sourced masses, never by the model.
- **[added]** If the answer to the clarifying question is still vague, the app picks the most common variant and shows it as an assumption.
- **[added]** Any physical thing can fight (D-38): objects, plants, vehicles, and machines get sourced mass, size, and speed like animals; mythical creature types ("dragon") are modeled by code on the real animals their legends compare them to, and every one of their stats is labeled an assumption. Named fictional characters, deities, firearms and explosives, and abstract ideas are politely turned away.
- **Done when:** 25+ test phrasings parse correctly; 50-case safety set passes.

### Step 2 — Research, RAG (Gunnar: G01–G06)
Reference text from Wikipedia, Wikidata, and Hugging Face datasets is parsed (port 9005), embedded (port 9002), and stored in a local vector index. At fight time, the app retrieves and reranks the best passages for each fighter. The Structured Decisions model fills a fixed stat schema using only that evidence, recording a source and confidence for each value. A seed set of popular fighters is verified by hand.
- **[added] The number rule:** the model may only *copy* a number together with the exact quote it came from; code checks the number is in the quote and the quote is in the source. Estimates are made by code from category defaults, never by the model. (ARCHITECTURE §5.)
- **[added]** Fixed stat schema: seven physical stats (mass, size, top speed, attack force, attack rate, reach, endurance) that are sourced or labeled estimates, and three behavioral stats (aggression, group tactics, armor) that no source measures, so they're labeled **assumptions** set from a written rubric. Every stat carries a plausible range.
- **[added]** 30 seed fighters (25 animals and archetypes, 5 objects and machines); 15 hand-verified sheets; 12 mythical creatures in a lore table with quoted sources.
- **Done when:** every displayed stat has a source link or an estimate tag (traceability 100%).

### Step 3 — Simulation (Felipe: F02–F04)
A Monte Carlo engine runs about 1,000 seeded fights from the stat sheets. It applies Lanchester's laws for numbers, square-cube scaling for size, terrain effects, and realistic behavior such as retreat. It outputs a win probability and a fight event log.
- **[added]** Deterministic: the same matchup and sheets always give the same result. Each run samples stats from their ranges, so the win % is shown with a 95% range that reflects input uncertainty. Every engine constant is documented with a source or stated as an assumption (`docs/simulation-model.md`). Fights time out at 10 simulated minutes (draw). Habitat mismatch can produce "no contest."
- **Done when:** property tests pass (determinism, mirror ≈ 50/50, more fighters never hurts) and 1,000 runs finish in seconds.

### Step 4 — Background (Adam: A06)
The chat LLM writes a corny announcer intro grounded in the stat sheets.

### Step 5 — Narration and soundtrack (Adam: A06, A07)
The LLM turns the event log into a play-by-play script, read by the text-to-speech endpoint in a consistent announcer voice. The music endpoint generates a short track matched to the matchup's mood.
- **[added]** Captions are always shown and synced to the animation; audio is optional.
- **[added]** A number guard rejects any script line containing a number not in the stats or results; a template script is the fallback.
- **[added]** Voice cloning only with a teammate's written consent (DECISIONS D-09); no celebrity voices.

### Step 6 — Battlefield (Adam: A08; Dillon: D05)
The image endpoint (port 9006) generates crude fighter sprites and a battlefield, and its editing mode cleans up backgrounds. A 2D game engine (Phaser 3) replays the event log, so the animation always matches the math.
- **[added]** Sprites are generated once per fighter and cached; placeholders appear if the image endpoint is down.

### Step 7 — Summary and fair fight (Felipe: F05, F06)
Statistics come straight from the simulation: win rate, survivors, duration, and the deciding factor, explained in plain language. The app then searches over fighter counts until the odds are near 50/50 ("a fair fight needs 37 house cats").
- **[added]** The deciding factor is found by sensitivity analysis in code, and explained by a code template.
- **[added]** If no count up to 10,000 reaches ~50/50, say so ("No fair fight within 10,000 ants").

### Step 8 — Next challenger (Adam A05 + Felipe F06)
The Structured Decisions model proposes candidate opponents for the winner (from seed and cached fighters); the simulation quick-tests each and suggests the closest matchup.

## 5. Tone guide [added]

- **Voice:** cheesy late-night sports broadcast. Puns welcome. A gruff, deep-voiced, hard-hitting fight announcer delivers the corny lines dead serious; a deadpan color commentator backs him up.
- **Rating:** PG. Knockouts, retreats, and "taps out." No blood, gore, or suffering described.
- **Respect:** jokes are about the fighters and the absurdity, never about groups of people.
- **Legends:** a mythical creature's numbers are introduced as legend ("according to legend, this dragon…"); objects get the same dead-serious treatment as a grizzly.
- **Honesty:** estimates are called estimates on air ("our best guess puts this badger at…").
- **Length:** intro 4–8 lines; play-by-play 8–20 beats; every line under 200 characters.

## 6. Look and feel [added]

Dark navy studio, neon scoreboard accents, lower-third banners, a ticker while research runs. Sprites are deliberately crude 16-bit style. Buttons say things like **FIGHT!** and **Next challenger**. WCAG AA contrast; reduced-motion mode; captions always on.

## 7. Evaluation

The proposal commits to two checks; the spec makes them measurable, and adds a live evaluation of the AI itself (M09), because the benchmark alone tests the simulator, not the GenAI:

| Check | How | Target |
|---|---|---|
| Benchmark accuracy | 30 matchups with expert or obvious answers (G07), 10 of them **held out** from all tuning; scored by `run_benchmark.py` (F07) twice: with hand-verified sheets and with research-only sheets | held-out set: ≥ 80% favorite-correct on "obvious"; report the rest honestly |
| Traceability | Every displayed stat traces to a retrieved source or is labeled an estimate or assumption (G06) | 100% (by design) — so the meaningful number is the next row |
| Sourced share [added] | Share of the seven physical stats that come from sources rather than estimates, for seed and for 10 new fighters (M09) | reported; target ≥ 70% for seed fighters |
| Extraction accuracy [added] | Research-only sheets vs. the 15 hand-verified sheets, stat by stat (M09) | reported: share within 10% / 25% |
| Retrieval [added] | hit@5 on 15 labeled cases (G03, M09) | ≥ 80% |
| Intake accuracy, live [added] | 25+ phrasings on the live chat model (M09) | reported |
| Stability [added] | Same input twice → same result | 100% |
| Latency [added] | Cached fighters: verdict ≤ 20 s; full show ≤ 2 min | met in the demo set |
| Safety, live [added] | 50-case safety set + injection cases on the live model (A04, M09) | 100% of blocked cases blocked; ≤ 2 false blocks |
| Usability [added] | 3–5 outside users (D10) | findings filed and top issues fixed before the freeze |
| Cost [added] | Endpoint calls per battle and cache hit rate (M09) | reported for new vs. repeat matchups |

## 8. Models, APIs, and software

All GenAI calls use course-provided endpoints, so no paid API keys are needed for evaluation.

| Service | Port | Used for | Status |
|---|---|---|---|
| Chat/Classification LLM | 9001 | parsing, moderation, scripts, challenger names | confirmed in proposal |
| Structured Decisions | in `.env` | schema-validated stat extraction | ports and keys in each person's `.env` (D-03) |
| Document Parsing | 9005 | HTML/PDF → text | confirmed |
| Text Embeddings | 9002 | vector index | confirmed |
| Multimodal Reranking | in `.env` | passage ranking | |
| Image Generation and Editing | 9006 | sprites, battlefields, background removal | confirmed |
| Text-to-Speech and Voice Cloning | in `.env` | gruff, deep stock announcer voice (D-09) | |
| Music Generation | in `.env` | soundtrack | |
| Speech-to-Text, Multimodal Embeddings | ? | stretch only | not in MVP |
| Hermes Primary Model + Hermes Agent | 9000 | Claude Code builds the app; Hermes Agent builds one task (G06) to show it in use (D-02) | app never calls it |
| Wikipedia Structured Contents + FineWiki (Hugging Face), Wikidata, PanTHERIA, AnimalTraits | public | knowledge base and trait numbers (D-20) | no key |

App software: Python 3.12 (FastAPI), React + Vite + TypeScript, Phaser 3, SQLite + sqlite-vec, Pydantic v2; runs with one command (`npm start`), no Docker. Full detail in [ARCHITECTURE.md](ARCHITECTURE.md).

## 9. Demo plan [added]

The deck and presentation are prepared outside this repo starting Nov 25; this section only makes sure the app is demo-ready. Everything shown should be pre-generated: on presentation day the whole class may be hitting the same course endpoints.


1. Pre-generate five showcase battles (cached, so they play instantly): *100 duck-sized horses vs 1 horse-sized duck*, *grizzly vs 6 wolves (forest)*, *honey badger vs king cobra*, *Roman legionary vs gorilla*, *great white shark vs saltwater crocodile (shoreline)*.
2. One live battle chosen by the audience from the seed list.
3. Show a source link and an "estimate" tag on screen; show the fair-fight line.
4. Backup: a screen recording of the five showcase battles, in case the course endpoints are down or slow on demo day.

## 10. Source apps and originality

We are not basing the app on screenshots or designs from any existing app. The concept draws on the general "who would win" debate genre; no code, designs, or content are taken from other sources, and the repository starts from scratch.
