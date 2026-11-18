# Benchmark matchup set

The benchmark asks whether the simulator's verdicts are sensible. It holds 30 matchups with an expected answer, written before anyone ran them through the engine (DECISIONS D-10). `run_benchmark.py` (task F07) scores them.

## How the set was built

| Group | Entries | Where the expected answer comes from |
|---|---|---|
| Obvious | 15 (5 with an object or machine) | The outcome follows from size or biology. Each has a one-line reason. |
| Documented | 10 | A published source records the outcome or who preys on whom. Each has a link to the exact page revision and the quote. |
| Count | 5 | A rough range for how many of the weaker fighter make the fight even. Each range is a judgment from relative size, with a one-line reason. |

All fighters come from the seed list in `docs/research.md`. Fighters and terrain are given as plain slugs, and `variant: null` means the default variant.

**Mythical creatures are excluded,** because legends have no right answer.

**Held-out set.** `data/benchmark/heldout.yaml` holds 10 entries: 5 obvious, 3 documented, and 2 count. They were drawn at random so nobody chose the easy ones. The draw was a one-off run with a single Python `random.Random(30)` generator: `sample` took 5 from the obvious entries, then 3 from the documented, then 2 from the count entries, each list in id order. The other 20 are in `data/benchmark/matchups.yaml`. **Held-out results are never used to change constants.** Only the tuning set may guide tuning. F07 reports held-out results separately from tuning results, and the held-out set is run only after tuning is frozen. A held-out miss may be investigated as a possible bug, but no constant may be tuned to move it. The file is committed in the open, so this is a team promise, not a technical lock.

## Entry format

| Field | Meaning |
|---|---|
| `id` | Unique name: `obv-`, `doc-`, or `cnt-` and a number |
| `group` | `obvious`, `documented`, or `count` |
| `fighters` | Two sides, each with `entity`, `count`, and `variant` |
| `terrain` | One of the app's terrains |
| `expected_winner` | `"0"` (first side), `"1"` (second side), or `"draw"` |
| `confidence` | `high` or `medium` |
| `expected_fair_count` | Count cases only: `[low, high]` for the weaker side's count, with the stronger side fixed at its listed count (1 in all five cases) |
| `source` | A link, or `obvious: <one-line reason>` |
| `quote` | Documented cases only: the sentence the answer rests on |

## Pass rules

These were written before the first run.

1. **Favorite correct:** the simulator's favorite matches `expected_winner`. For `draw`, the simulated outcome must be a draw (no entry uses `draw` yet).
2. **High-confidence cases:** the favorite's win probability is at least 0.7. Medium-confidence cases need only the right favorite.
3. **Count cases:** these are judged only on the fair-fight search, which varies the count of the side expected to lose until the fight is closest to even. That count must land inside `expected_fair_count`. Rules 1 and 2 don't apply to them.

The product target is at least 80% favorite-correct on the obvious cases in the held-out set. Everything else is reported as it comes out.

## Traceability

The run's traceability column comes from G06's checker (`scripts/trace_report.py`, #40): the share of stored battles with no broken link between a number and its source. The note under it says how many quotes (extracted and, since #369, hand-verified) were checked against stored articles, and how many couldn't be checked because their article isn't stored on the machine running the benchmark.

**Strict mode** (`--require-quotes`, #370), on both `trace_report.py` and `run_benchmark.py`: a battle counts as traceable only if it has no issues and every quote was checked, so 100% means every quote was really verified. Since #369 this includes the seed sheets' hand-verified quotes, so strict mode fails on a machine whose knowledge base doesn't store their articles; run `npm run ingest` (or `--refresh`) first. `trace_report.py --require-quotes` also exits 1 when any quote couldn't be checked. It's off by default.

## Known weaknesses

- **Predation is not a duel.** Most documented cases say one animal preys on another, usually under conditions that favor the hunter. The benchmark treats that as evidence for a one-on-one fight, which is weaker than a direct statement, so most are `medium` confidence.
- **Some quotes are indirect or about a broader group.** `doc-01` is about brown bears against wolf packs, `doc-03` lists lions among several predators of the honey badger, `doc-04` is about cobras in general rather than the king cobra, `doc-05` is about wolves preying on wild horses, `doc-06` is about shepherd dogs rather than golden retrievers, `doc-09` lists horses among livestock eaten "if given the opportunity", and `doc-10` says lion prides rarely kill adult hippos, which is thin support for a one-on-one result.
- **The random draw left gaps in the held-out set.** Two pairings appear twice in it, cat vs wolf (`obv-01` and `cnt-01`) and horse vs duck (`obv-09` and `cnt-04`), so it holds 8 distinct matchups, not 10. None of the 5 held-out obvious cases involves an object or machine. (The tuning set also repeats wolf vs grizzly as `cnt-02` and `doc-01`.) Replacing entries by hand would undo the point of the draw, so they stay.
- **Count ranges are assumptions, not measurements.** No source measures how many house cats equal a wolf. The ranges come from rough size ratios and are deliberately wide (for example `cnt-04` spans 20 to 300), so they catch gross errors in the engine, not small ones. A pass here is weak evidence.
- **Fighters without hand-verified sheets.** Only 15 fighters get hand-verified sheets (G05). Matchups using the others can only be scored with research sheets or skipped.
- **The set is small.** With 5 obvious cases held out, one miss moves that score by 20 points.
- **No swarm or edge-case coverage.** No matchup puts more than 4 fighters on a side apart from the count-case ranges, so the set cannot judge swarm mode or `SWARM_THRESHOLD`. It also has no mirror matches, no draws, no ranged fighters, and never uses the water, urban or mountain terrain. Ten seed fighters (chimpanzee, great white shark, army ant, honey bee, T. rex, triceratops, medieval knight, samurai, pickup truck, saguaro cactus) are not used. The edge-case set below covers these.

## Edge-case set

`data/benchmark/edge.yaml` (#136) holds 15 cases the main set can't judge. It uses the same entry format, with three differences:

- `group` is `swarm`, `showcase`, `mirror`, `draw` or `terrain`, and `id` starts with `edge-`.
- `source` is always `assumption: <one-line reason>`. These answers are judgment calls, never sourced facts.
- A fighter may carry `size_reference` (the showcase's duck-sized horses), and the showcase dragon comes from `data/seed/mythical.yaml`. Legends have no right answer, so the main set leaves them out; this one checks only that the showcase battle behaves as planned.

| Group | Cases | What it checks |
|---|---|---|
| `swarm` | army ants (150, 300) vs a house cat; honey bees (150, 300) vs a chimpanzee | the same matchup on both sides of 200 per side |
| `showcase` | the five PRODUCT_SPEC §9 battles | the demo still behaves as planned |
| `mirror` | samurai vs samurai; gray wolf vs gray wolf | no side bias |
| `draw` | saguaro cactus vs toaster | a fight nobody can win |
| `terrain` | water, mountain, urban | the terrains the main set never uses |

Together they use all ten seed fighters the main set leaves out.

**Pass rules, written before the first run:**

1. **Swarm, showcase, terrain:** the same favorite rule as the main set (rule 1). All are `medium`, so rule 2's 0.7 floor doesn't apply.
2. **Mirror:** the first side's win probability is within 0.1 of 0.5 (|p − 0.5| ≤ 0.1). `expected_winner` is `draw` only to mark it; the outcome itself doesn't have to be a draw.
3. **Draw:** a draw is the most likely outcome, with a draw probability of at least 0.5. A fight where neither side can hurt the other ends as `no_contest` (win and draw shares both 0), which counts as the same "nobody wins" (#376; the runner reads it this way because the engine never reports a harmless fight as a counted draw).
4. **Swarm pairs** (`a` is about 150 per side, `b` about 300): both pick the expected favorite, and the bigger swarm never does worse. The swarm side's win probability in `b` is at least its value in `a` minus 0.03 (more fighters never hurt, #108).
5. **Swarm against one-by-one (D-45):** the runner runs each swarm case in both modes and the two win probabilities agree within ±0.03. `run_benchmark.py` does this for the four swarm entries (#376), forcing swarm through the work rule and one-by-one through a head-count threshold nobody reaches, the same way `scripts/validate_swarm.py` does. A venomous side under 200 per side stays one by one whatever the budget (D-44), so such a case is reported with no mode check instead of a false 0.000. It adds a minute or two to a live run; `--no-edge` leaves the whole edge set out.

The edge-case results are reported in their own table, never mixed into the main set's scores or its 80% target.

**Known weaknesses of this set:**

- Every answer is an assumption, so a miss means "look at this", not "the engine is wrong".
- Since D-50, swarm mode is chosen by a fight's estimated work, not by head count. So 150 against 300 crosses the old 200 line but may not switch the engine's mode on its own. Rule 5 is the direct check.
- The draw case depends on the toaster and the cactus both being unable to hurt each other. If either gets a real attack, it stops being a draw case.

## Engine version 12 (#341) and 11 (#301)

The benchmark scores the favorite and the fair count, never the deciding factor. The #301 change (every deciding-factor variant runs in the baseline's swarm mode) moved 1 deciding factor in 261 seed fights and no win share. The seed baseline re-run at version 11 (`--live --sheets seed`, run of 2026-11-15) has the same tuning result as the version before (15/16, cnt-05 is the known limit in D-58) and no verdict changed because of it.

Version 12 (#341) only skips a deciding-factor variant that is far over the work budget, so it changes no win share. The seed baseline re-run at version 12 (`--live --sheets seed`, run of 2026-11-16) has the same headline as version 11: tuning 15/16 (cnt-05 is the known limit in D-58) and held-out 8/9.
