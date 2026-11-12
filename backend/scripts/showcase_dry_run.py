"""Run the five showcase battles through the engine with stand-in sheets (an engine sanity check).

From the repo root:
  uv run --directory backend python scripts/showcase_dry_run.py

The real sheets come from tasks G05 and G09. So far only the grizzly and the gray wolf are real
(the hand-verified seed sheets in data/seed/fighters/); every other fighter is a stand-in with
round numbers from common reference values. They are NOT sourced and must never reach the UI:
this script only checks that the engine gives sensible, explainable results for the demo, and
shows what to tune if not.
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
from tests.property.sim_helpers import make_dragon, make_sheet, matchup_of  # noqa: E402

SEED_FIGHTERS = Path(__file__).resolve().parents[2] / "data" / "seed" / "fighters"

BANNER = (
    "STAND-IN SHEETS: only the grizzly and the gray wolf are real (G05 seed sheets); every other "
    "fighter is an unsourced stand-in.\nEngine check only, not demo results."
)


def seed_sheet(name: str) -> StatSheet:
    """A real, hand-verified seed sheet (G05) by file name, e.g. "gray-wolf"."""
    path = SEED_FIGHTERS / f"{name}.json"
    return StatSheet.model_validate(json.loads(path.read_text("utf-8")))


def stand_ins() -> dict[str, StatSheet]:
    """Round-number stand-ins (see the module docstring)."""
    return {
        "horse": make_sheet(
            "horse", mass_kg=500, size_m=2.4, top_speed_mps=20, attack_force_n=6000,
            attacks_per_s=0.5, reach_m=1.5, armor_0_1=0.05, aggression_0_1=0.3,
            group_tactics_0_1=0.4,
        ),
        "duck": make_sheet(
            "duck",
            category="bird", mass_kg=1.2, size_m=0.55, top_speed_mps=5, attack_force_n=20,
            attacks_per_s=2.0, reach_m=0.2, armor_0_1=0.05, aggression_0_1=0.3,
            group_tactics_0_1=0.3,
        ),
        "honey badger": make_sheet(
            "honey badger",
            fighter_id="honey-badger", category="mammal", mass_kg=10, size_m=0.75,
            top_speed_mps=8, attack_force_n=300, attacks_per_s=2.0, reach_m=0.3, armor_0_1=0.5,
            aggression_0_1=1.0, group_tactics_0_1=0.0,
        ),
        "king cobra": make_sheet(
            "king cobra",
            weapons=["venom", "teeth"], category="reptile", mass_kg=6, size_m=3.5,
            top_speed_mps=5, attack_force_n=100, attacks_per_s=1.5, reach_m=1.2, armor_0_1=0.1,
            aggression_0_1=0.5, group_tactics_0_1=0.0,
        ),
        "legionary": make_sheet(
            "legionary",
            category="human_archetype", mass_kg=75, size_m=1.75, top_speed_mps=6,
            attack_force_n=1500, attacks_per_s=1.0, reach_m=0.9, armor_0_1=0.5, aggression_0_1=0.7,
            group_tactics_0_1=0.9, weapons=["weapon_melee"],
        ),
        "gorilla": make_sheet(
            "gorilla",
            category="mammal", mass_kg=160, size_m=1.7, top_speed_mps=7, attack_force_n=6000,
            attacks_per_s=1.0, reach_m=1.0, armor_0_1=0.15, aggression_0_1=0.5,
            group_tactics_0_1=0.2,
        ),
        "dragon": make_dragon(["flight", "breath_weapon"], name="dragon"),
        "tank": make_sheet(
            "tank",
            category="vehicle", body="machine", weapons=["ramming"], mass_kg=60000, size_m=10.0,
            top_speed_mps=18, attack_force_n=0, attacks_per_s=0.1, reach_m=1.0,
            armor_0_1=0.9, endurance_s=7200, aggression_0_1=0.0, group_tactics_0_1=0.0,
        ),
    }  # fmt: skip


@dataclass(frozen=True)
class Battle:
    title: str
    matchup: Matchup
    sheets: list[StatSheet]
    references: list[StatSheet | None] | None = None


def battles() -> list[Battle]:
    s = stand_ins()
    bear, wolf = seed_sheet("grizzly-bear"), seed_sheet("gray-wolf")
    return [
        Battle(
            "100 duck-sized horses vs 1 horse-sized duck",
            matchup_of(100, 1, ref_0="duck", ref_1="horse", terrain=Terrain.OPEN_FIELD),
            [s["horse"], s["duck"]],
            [s["duck"], s["horse"]],
        ),
        Battle(
            "Grizzly vs 6 wolves (forest)",
            matchup_of(1, 6, terrain=Terrain.FOREST),
            [bear, wolf],
        ),
        Battle(
            "Honey badger vs king cobra",
            matchup_of(1, 1, terrain=Terrain.OPEN_FIELD),
            [s["honey badger"], s["king cobra"]],
        ),
        Battle(
            "Roman legionary vs gorilla",
            matchup_of(1, 1, terrain=Terrain.FOREST),
            [s["legionary"], s["gorilla"]],
        ),
        Battle(
            "A dragon vs a main battle tank (open field)",
            matchup_of(1, 1, terrain=Terrain.OPEN_FIELD),
            [s["dragon"], s["tank"]],
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
