# Simulation API: how to call the fight engine

For Adam (the orchestrator, A05; scripts, A06) and Dillon (results and battle scene, D04, D05, D07). Everything lives in `backend/app/simulation/` and runs **in-process with no network, no providers, and no language model**. Every number in a result is set by code. The model behind it is explained in [simulation-model.md](simulation-model.md); this page is just *how to call it*.

## The five calls

```python
from app.simulation.engine import run
from app.simulation.fair import fair_fight, test_challengers
from app.simulation.summary import summary
```

| Call | Returns | Use it for | Typical time |
|---|---|---|---|
| `run(matchup, stat_sheets, runs=None, reference_sheets=None, explain=True)` | `SimulationResult` | The verdict, the replay log, the deciding factor | 0.4 s for a 1 v 1; ~1 s for 6 v 1; ~1.5 s for 10,000 ants v 1 lion |
| `run(..., explain=False)` | `SimulationResult` (placeholder explainer) | Quick probes where you do not need the "why" | 0.15 s for a 1 v 1 |
| `fair_fight(matchup, stat_sheets, result=None, reference_sheets=None)` | `FairFight` | "A fair fight needs 37 house cats" | 0.1 s for wolf vs cats; ~4-5 s when there is no answer (15 swarm probes) |
| `test_challengers(winner_sheet, candidates, terrain=Terrain.ARENA)` | `list[ChallengerSuggestion]`, closest to 50/50 first | The "next challenger" step | ~0.3 s for 8 candidates |
| `summary(result, names)` | `Summary` | The numbers the UI and announcer need | instant |

All calls are **deterministic**: the same matchup, sheets, and engine version always give the identical result (the seed is built from the matchup, both `sheet_hash` values, and `ENGINE_VERSION`). That is what lets "same battle requested twice" return the cached answer.

## A complete example

```python
import json
from pathlib import Path

from app.models.matchup import FighterRequest, Matchup
from app.models.stats import StatSheet
from app.models.terrain import Terrain
from app.simulation.engine import run
from app.simulation.fair import fair_fight
from app.simulation.summary import summary

fixtures = Path("backend/tests/fixtures/contracts")
bear = StatSheet.model_validate(json.loads((fixtures / "stat-sheet.json").read_text("utf-8")))
wolf = StatSheet.model_validate(json.loads((fixtures / "stat-sheet-gray-wolf.json").read_text("utf-8")))

matchup = Matchup(
    fighters=[
        FighterRequest(entity="grizzly bear", variant="adult male", raw="a grizzly bear"),
        FighterRequest(entity="gray wolf", count=6, raw="6 gray wolves"),
    ],
    terrain=Terrain.FOREST,
    raw_text="a grizzly bear vs 6 gray wolves in a forest",
)
stat_sheets = [bear, wolf]  # in the same order as matchup.fighters

result = run(matchup, stat_sheets)  # SimulationResult
view = summary(result, (bear.display_name, wolf.display_name))
print(view.favorite_name, view.win_pct, view.deciding_factor_text)

fair = fair_fight(matchup, stat_sheets, result)  # reuse the result you already have
print(fair.message)
```

`stat_sheets[i]` must belong to `matchup.fighters[i]`. Counts come from the matchup (`FighterRequest.count`), never from the sheet.

## What you get back

**`SimulationResult`** (a shared contract, unchanged):

| Field | Meaning |
|---|---|
| `outcome` | `win_0`, `win_1`, `draw`, or `no_contest`: the most likely result |
| `win_prob`, `draw_prob`, `win_prob_ci95` | Shares over `runs` fights (default 1,000) and their 95% ranges. Label them "range" in the UI |
| `mean_survivors`, `mean_duration_s` | Averages over all runs |
| `deciding_factor`, `deciding_factor_explainer` | A stat name or `numbers` / `terrain` / `habitat` / `abilities`, plus a plain sentence made by a code template |
| `representative_log` | Up to 300 `FightEvent`s of one typical fight: the replay for Phaser and the script |
| `seed`, `runs` | Reproducibility |

**`summary(result, names)`** returns a `Summary` (not a contract): `win_pct` (per side, percent to 1 decimal), `draw_pct`, `survivors`, `duration_s`, `outcome`, `favorite` (`0`, `1`, or `None`), `favorite_name`, `deciding_factor`, `deciding_factor_text`. Use it for the results card and for the script generator's inputs.

**`FairFight`**: `count` is the number of the *losing* side (`varied_side`) that makes the fight about 50/50, or `None` with a plain `message` ("No fair fight within 10,000 house cats."). If the count is only approximate, the message says "about" and `win_prob_at_count` shows the real value.

**`ChallengerSuggestion`**: `entity` (the candidate's display name), `tested_win_prob` (the candidate's chance against the winner), and a `reason`. Candidates that cannot even meet the winner (`no_contest`) are left out.

## Cases your code must handle

| Case | What you see | What to do |
|---|---|---|
| **No contest** (flier vs swimmer in open water; two objects that can't hurt anyone) | `outcome == "no_contest"`, probabilities 0, one END event with a joke-able hint | Skip the sports commentary; show the explainer. `fair_fight` returns `count=None` with an explanation |
| **Draw / stalemate** | `outcome == "draw"` | There is no favorite (`summary.favorite is None`); the explainer says it was a stalemate |
| **A side flees** | RETREAT then FLEE events; the other side wins; the runner is counted among the survivors | The log tells the story |
| **A machine runs out of operating time** | a KO event with the hint "out of action: its operating time ran out" | Narrate it as breaking down, not dying |
| **Swarms** (a side over 200) | Group events with `group_size > 1` and `actor`/`target` of `None` | Animate a crowd, not individuals |
| **Size reference** ("horse-sized duck") | The first APPROACH event's hint ends with ", scaled to horse size" | See below |

## Size references ("horse-sized duck")

Pass the reference entity's stat sheet at the **same position** as the fighter that has the `size_reference`. For "a horse-sized duck vs a lion", fighter 0 is the duck with `size_reference="horse"`:

```python
result = run(matchup, [duck, lion], reference_sheets=[horse, None])
# fighter 0 (the duck) is scaled up to the horse's mass; fighter 1 is not scaled
```

If a fighter has a `size_reference` and no reference sheet is given, `run` raises `ValueError`. The scale factor is computed in code from the two sheets' masses. (It is not yet a field on the result; see "Known gaps".)

## What the replay log contains

`FightEvent.type` values used, with the `text_hint` words you can rely on (all neutral, and none contains a number):

| Type | Typical `text_hint` |
|---|---|
| `approach` | "closes in" (plus ", scaled to X size" when scaled) |
| `hit` / `miss` | "bite lands", "claw swipe misses", "blast lands", "spines jab back" (swarms: plural, "bites land") |
| `ko` | "goes down" / "go down"; "out of action: its operating time ran out" |
| `retreat` / `flee` | "breaks and runs" / "escapes" |
| `stalemate` / `end` | "neither side can win", "fight ends in a draw", "the fight is over", "no contest: ..." |

`actor` and `target` are fighter indexes within a side; `side` is 0 or 1 (the matchup order); `damage` is in hit points (relative, not real units). Events are in time order, `t` in simulated seconds. The log holds at most 298 events from the fight itself plus the closing events (300 in all), so a long fight's log may stop before the fight does; the END event is always last.

## Speed and good habits

- Call `run` once per battle with the default 1,000 runs. Pass `explain=False` for anything you do in a loop.
- Pass the `result` you already have to `fair_fight` so it does not re-simulate.
- Fair-fight and challenger probes use 200 runs each by design.
- One-by-one fights cost roughly the number of attacks made, so groups just under 200 per side are slow (200 v 200 takes ~17 s at 1,000 runs). If you let users type big numbers, cap the run count there, or ask me to lower the swarm threshold.
- Run the engine off the event loop (a thread or task): it is CPU-bound Python.

## Known gaps

- `SimulationResult` has no field for the scale factor; it rides in the first approach event's `text_hint` and `engine.scale_factors(...)` returns it. A proper field needs a `contract-change` approved by Mike.
- Fatigue for living fighters is not modeled; only machines stop when their operating time runs out.
- The constants are assumptions where no source exists ([simulation-model.md](simulation-model.md) labels each one). The benchmark (F07) is how we check them.

## Test fixtures to build against

`backend/tests/fixtures/contracts/` has `simulation-result.json`, `fair-fight.json`, `challenger-suggestion.json`, `fight-event.json`, and stat sheets for a grizzly, a gray wolf, a toaster, and a dragon. `backend/tests/property/sim_helpers.py` has `make_sheet(...)` for building stand-in fighters in tests.
