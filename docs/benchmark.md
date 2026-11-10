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

**Held-out set.** `data/benchmark/heldout.yaml` holds 10 entries: 5 obvious, 3 documented, and 2 count. They were drawn at random with Python's `random.Random(30)`, so nobody chose the easy ones. The other 20 are in `data/benchmark/matchups.yaml`. **Held-out results are never used to change constants.** Only the tuning set may guide tuning.

## Entry format

| Field | Meaning |
|---|---|
| `id` | Unique name: `obv-`, `doc-`, or `cnt-` and a number |
| `group` | `obvious`, `documented`, or `count` |
| `fighters` | Two sides, each with `entity`, `count`, and `variant` |
| `terrain` | One of the app's terrains |
| `expected_winner` | `"0"` (first side), `"1"` (second side), or `"draw"` |
| `confidence` | `high` or `medium` |
| `expected_fair_count` | Count cases only: `[low, high]` for the losing side's count |
| `source` | A link, or `obvious: <one-line reason>` |
| `quote` | Documented cases only: the sentence the answer rests on |

## Pass rules

These were written before the first run.

1. **Favorite correct:** the simulator's favorite matches `expected_winner`.
2. **High-confidence cases:** the favorite's win probability is at least 0.7.
3. **Count cases:** the fair-fight count falls inside `expected_fair_count`.

The product target is at least 80% favorite-correct on the obvious cases in the held-out set. Everything else is reported as it comes out.

## Known weaknesses

- **Predation is not a duel.** Most documented cases say one animal preys on another, usually under conditions that favor the hunter. The benchmark treats that as evidence for a one-on-one fight, which is weaker than a direct statement, so most are `medium` confidence.
- **Some quotes are indirect or about a broader group.** `doc-01` is about brown bears against wolf packs, `doc-03` lists lions among several predators of the honey badger, `doc-04` is about cobras in general rather than the king cobra, `doc-05` is about wolves preying on wild horses, `doc-06` is about shepherd dogs rather than golden retrievers, `doc-09` lists horses among livestock eaten "if given the opportunity", and `doc-10` says lion prides rarely kill adult hippos, which is thin support for a one-on-one result.
- **The random draw left two gaps in the held-out set.** `obv-01` and `cnt-01` are both house cat vs gray wolf, so they test nearly the same thing, and none of the 5 held-out obvious cases involves an object or machine. Replacing entries by hand would undo the point of the draw, so they stay.
- **Count ranges are judgment calls.** No source measures how many house cats equal a wolf, so the ranges are deliberately wide.
- **Fighters without hand-verified sheets.** Only 15 fighters get hand-verified sheets (G05). Matchups using the others can only be scored with research sheets or skipped.
- **The set is small.** With 5 obvious cases held out, one miss moves that score by 20 points.
