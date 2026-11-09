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
| `run(..., explain=False)` | `SimulationResult` (placeholder explainer) | Quick probes where you do not need the "why". **Never show** its `deciding_factor` (always `mass_kg`) or explainer ("Deciding factor not computed."): both are placeholders | 0.15 s for a 1 v 1 |
| `fair_fight(matchup, stat_sheets, result=None, reference_sheets=None)` | `FairFight` | "A fair fight needs 37 house cats" | 0.1 s for wolf vs cats; ~4-5 s when there is no answer (15 swarm probes) |
| `test_challengers(winner_sheet, candidates, terrain=Terrain.ARENA)` | `list[ChallengerSuggestion]`, closest to 50/50 first | The "next challenger" step | ~0.3 s for 8 candidates |
| `summary(result, names)` | `Summary` | The numbers the UI and announcer need | instant |

Timings are typical on a dev laptop at `ENGINE_VERSION 5`; expect similar or faster.

All calls are **deterministic**: the same matchup, sheets, and engine version always give the identical result (the seed is built from the matchup, both `sheet_hash` values, and `ENGINE_VERSION`). That is what lets "same battle requested twice" return the cached answer.

## A complete example

Run it from the repo root: the fixture path below is relative (the guide's own test does the same).

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
| **A side flees** | RETREAT then FLEE: the runner escapes, the other side wins, and the runner is counted among the survivors. RETREAT **without** FLEE means the runner is too slow to get away and the fight continues | The log tells the story |
| **A machine runs out of operating time** | a KO event with the hint "out of action: its operating time ran out" | Narrate it as breaking down, not dying |
| **Swarms** (either side over 200) | Group events: `actor`/`target` are `None` and `group_size` is how many acted or fell (it can be 1). In swarm mode every HIT and KO is a group event, for both sides, and there are no MISS events | Animate a crowd, not individuals. Decide "swarm" from the matchup counts (> 200), not from `group_size`; APPROACH, RETREAT and FLEE are group events in every fight |
| **Size reference** ("horse-sized duck") | The first APPROACH event's hint ends with ", scaled to horse size" | See below |

## Size references ("horse-sized duck")

Pass the reference entity's stat sheet at the **same position** as the fighter that has the `size_reference`. For "a horse-sized duck vs a lion", fighter 0 is the duck with `size_reference="horse"`:

```python
result = run(matchup, [duck, lion], reference_sheets=[horse, None])
# fighter 0 (the duck) is scaled up to the horse's mass; fighter 1 is not scaled
```

If a fighter has a `size_reference` and no reference sheet is given, `run` raises `ValueError`. The scale factor is computed in code from the two sheets' masses. (It is not yet a field on the result; see "Known gaps".)

## What the replay log contains

**Switch on `FightEvent.type`; `text_hint` is flavor text for narration, never a code.** Every `text_hint` is neutral and contains no number. Who `side`, `actor` and `target` refer to depends on the type:

| `type` | `side`, `actor`, `target` | `text_hint` |
|---|---|---|
| `approach` | `side` closes in; `group_size` is how many fighters that side has; no `actor` | "closes in" (plus ", scaled to horse size" when scaled) |
| `hit` | `side` is the **attacker's** side, `actor` the attacker, `target` the one hit; `damage` is the hit. **Swarm hits:** `actor` and `target` are `None`, `group_size` is how many hit, and `damage` is the group total | "bite lands" (swarm: "bites land"), "blast lands", "ram lands", and so on (weapon words below) |
| `hit` (spines) | **Swapped:** `side` is the **defender's** side, `actor` the spiny defender, `target` the attacker it hurt | "spines jab back" |
| `miss` | Like `hit`; `damage` is `None`. Swarm fights have no MISS events | "bite misses", "blast misses", and so on |
| `ko` | `side` is the side that **went down** (or the machine that broke), `actor` is the fallen fighter's index, `target` is `None`; swarm: `actor` is `None` and `group_size` is how many fell | "goes down" / "go down"; "out of action: its operating time ran out" |
| `retreat` | `side` is the side that ran; `group_size` is how many were left | "breaks and runs" / "break and run" |
| `flee` | `side` is the side that got away | "escapes" / "escape" |
| `stalemate` | `side` is 0 | "neither side can win" |
| `end` | `side` is the **winner** (0 for a draw or no contest: check `outcome`) | "the fight is over", "fight ends in a draw", "no contest: neither can reach the other", "no contest: nobody can hurt anybody" |

Weapon words: bite, claw swipe, goring thrust, kick, venom strike, squeeze, tusk jab, peck, sting, blow, shot, ram, crush, spine jab, blast, strike (when no weapon fits). A swarm hint uses the plural: "bites land", "crushes land".

### What the replay scene can and cannot rely on

- **Positions:** events carry none. The scene places the fighters itself.
- **Arrival:** there is one APPROACH per side at `t = 0` and no "arrived" event; the first HIT or MISS is the first contact.
- **`damage`** is in hit points (relative, not real units): per hit for single fighters, the group total for swarm hits, `None` on misses and knock-outs.
- **`EventType.ATTACK`** exists in the contract but is never emitted.
- **Time:** events are in time order, `t` in simulated seconds, and all fall within 600 s.
- **Length and cut-off:** the log has at most 300 events. After about 298 events from the fight itself, later hits and knock-outs are dropped, but the closing events are always added. If `len(log) >= 299` the log may be cut off, so never count KOs to work out who survived; use `outcome` and `mean_survivors`, and treat the log as a highlight reel.
- **Who won:** read `outcome` (or `summary(...).favorite`). The END event's `side` is the winner only when there is one (0 for a draw or no contest).

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
