"""Run the five showcase battles through the engine (an engine sanity check).

From the repo root:
  uv run --directory backend python scripts/showcase_dry_run.py

Every fighter except the dragon is a real, hand-verified seed sheet (G05, in data/seed/fighters/).
The dragon is still a stand-in with round numbers (G09 builds the real mythical sheets from their
analogs): it is NOT sourced and must never reach the UI. This script checks that the engine gives
sensible, explainable results for the demo, and shows what to tune if not.
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.matchup import Matchup  # noqa: E402
from app.models.simulation import FairFight, SimulationResult  # noqa: E402
from app.models.stats import StatSheet  # noqa: E402
from app.models.terrain import Terrain  # noqa: E402
from app.simulation.engine import run  # noqa: E402
from app.simulation.fair import fair_fight  # noqa: E402
from app.simulation.summary import Summary, summary  # noqa: E402

# Deliberately borrowed from the test helpers (this works because the backend folder is on the
# path); moving `sim_helpers` breaks it. `make_sheet` labels every overridden stat as an unsourced
# stand-in (#86), but the numbers are still invented, so the stand-in sheets built here must never
# be shown, saved, or used as fixtures.
from tests.property.sim_helpers import make_dragon, matchup_of  # noqa: E402

SEED_FIGHTERS = Path(__file__).resolve().parents[2] / "data" / "seed" / "fighters"

BANNER = (
    "ENGINE CHECK ONLY: real seed sheets for every fighter except the dragon, an unsourced "
    "stand-in (G09).\nNot demo results."
)


def seed_sheet(name: str) -> StatSheet:
    """A real, hand-verified seed sheet (G05) by file name, e.g. "gray-wolf"."""
    path = SEED_FIGHTERS / f"{name}.json"
    return StatSheet.model_validate(json.loads(path.read_text("utf-8")))


def dragon() -> StatSheet:
    """The one stand-in left: a dragon with round numbers (see the module docstring)."""
    return make_dragon(["flight", "breath_weapon"], name="dragon")


@dataclass(frozen=True)
class Battle:
    title: str
    matchup: Matchup
    sheets: list[StatSheet]
    references: list[StatSheet | None] | None = None


def battles() -> list[Battle]:
    horse, duck = seed_sheet("horse"), seed_sheet("duck")
    bear, wolf = seed_sheet("grizzly-bear"), seed_sheet("gray-wolf")
    badger, cobra = seed_sheet("honey-badger"), seed_sheet("king-cobra")
    legionary, gorilla = seed_sheet("roman-legionary"), seed_sheet("gorilla")
    tank = seed_sheet("main-battle-tank")
    return [
        Battle(
            "100 duck-sized horses vs 1 horse-sized duck",
            matchup_of(100, 1, ref_0="duck", ref_1="horse", terrain=Terrain.OPEN_FIELD),
            [horse, duck],
            [duck, horse],
        ),
        Battle(
            "Grizzly vs 6 wolves (forest)",
            matchup_of(1, 6, terrain=Terrain.FOREST),
            [bear, wolf],
        ),
        Battle(
            "Honey badger vs king cobra",
            matchup_of(1, 1, terrain=Terrain.OPEN_FIELD),
            [badger, cobra],
        ),
        Battle(
            "Roman legionary vs gorilla",
            matchup_of(1, 1, terrain=Terrain.FOREST),
            [legionary, gorilla],
        ),
        Battle(
            "A dragon vs a main battle tank (open field)",
            matchup_of(1, 1, terrain=Terrain.OPEN_FIELD),
            [dragon(), tank],
        ),
    ]


@dataclass(frozen=True)
class Outcome:
    battle: Battle
    result: SimulationResult
    view: Summary
    fair: FairFight
    seconds: float


def play(battle: Battle, runs: int | None = None) -> Outcome:
    start = time.perf_counter()
    result = run(battle.matchup, battle.sheets, runs=runs, reference_sheets=battle.references)
    fair = fair_fight(battle.matchup, battle.sheets, result, battle.references)
    names = (battle.sheets[0].display_name, battle.sheets[1].display_name)
    return Outcome(battle, result, summary(result, names), fair, time.perf_counter() - start)


def report(outcome: Outcome) -> str:
    r, v = outcome.result, outcome.view
    kinds = ", ".join(sorted({e.type.value for e in r.representative_log}))
    chances = f"{v.win_pct[0]}% / {v.win_pct[1]}% (draw {v.draw_pct}%)"
    lines = [
        f"### {outcome.battle.title}",
        "",
        f"- Verdict: **{r.outcome}**; win chance {chances}; about {v.duration_s} s; "
        f"survivors {v.survivors[0]} / {v.survivors[1]}",
        f"- Why: {r.deciding_factor_explainer}",
        f"- Fair fight: {outcome.fair.message}",
        f"- Replay: {len(r.representative_log)} events ({kinds}); "
        f"computed in {outcome.seconds:.1f} s",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=None, help="runs per battle (default 1,000)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(BANNER + "\n")
    for battle in battles():
        print(report(play(battle, args.runs)) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
