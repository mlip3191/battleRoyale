"""Compare swarm mode (fights simulated in groups) with the one-by-one engine.

From the repo root:
  uv run --directory backend python scripts/validate_swarm.py
  uv run --directory backend python scripts/validate_swarm.py --scenario cats --runs 300

Each matchup is simulated twice with the same sheets: once forced through the one-by-one engine
and once forced through swarm mode (by moving `SWARM_THRESHOLD`). The one-by-one engine is the
reference. The report is a markdown table of win share, mean duration, and survivors for both.
Fighters are the contract wolf and bear plus stand-ins (cat, archer) from the test helpers.
Nothing here uses the network.
"""

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.simulation import SimulationResult  # noqa: E402
from app.models.stats import StatSheet  # noqa: E402
from app.simulation import constants as c  # noqa: E402
from app.simulation.engine import run  # noqa: E402
from tests.property.sim_helpers import FIXTURES, make_sheet, matchup_of  # noqa: E402

ALWAYS_INDIVIDUAL = 10**9  # a threshold no fight reaches
ALWAYS_SWARM = 0


def sheet(name: str) -> StatSheet:
    return StatSheet.model_validate(json.loads((FIXTURES / name).read_text("utf-8")))


def scenarios() -> dict[str, list[tuple[str, StatSheet, int, StatSheet, int]]]:
    wolf, bear = sheet("stat-sheet-gray-wolf.json"), sheet("stat-sheet.json")
    cat = make_sheet(
        "cat", mass_kg=4.5, size_m=0.46, top_speed_mps=13, attack_force_n=200,
        attacks_per_s=2.0, reach_m=0.2, armor_0_1=0.05, aggression_0_1=1.0,
    )  # fmt: skip
    archer = make_sheet("archer", weapons=["weapon_ranged"], reach_m=8)

    def fights(a, b, sizes, label):
        """`sizes` is a list of (count of a, count of b); `label` names the two fighters."""
        return [(f"{na} v {nb} {label}", a, na, b, nb) for na, nb in sizes]

    even = [(n, n) for n in (5, 10, 25, 50, 100)]
    uneven = [(n * 5 // 4, n) for n in (10, 25, 50, 100)]
    one_big = [(n, 1) for n in (3, 6, 12, 25, 50)]
    many_weak = [(n, max(n // 5, 1)) for n in (10, 25, 50, 100)]
    ranged = [(n, n // 2) for n in (10, 25, 50)]
    # Sizes where swarm mode really runs (above 200 per side). Opt-in because it is the slowest
    # group (about 8 s at 300 runs): `--scenario large --runs 300`.
    large = [(250, 250, wolf, wolf, "wolves"), (300, 60, cat, wolf, "(cats v wolves)")]
    large += [
        (600, 120, cat, wolf, "(cats v wolves)"),
        (400, 200, archer, wolf, "(archers v wolves)"),
    ]
    return {
        "mirror": fights(wolf, wolf, even, "wolves"),
        "uneven": fights(wolf, wolf, uneven, "wolves"),
        "pack": fights(wolf, bear, one_big, "(wolves v bear)"),
        "cats": fights(cat, wolf, many_weak, "(cats v wolves)"),
        "ranged": fights(archer, wolf, ranged, "(archers v wolves)"),
        "large": [(f"{na} v {nb} {label}", a, na, b, nb) for na, nb, a, b, label in large],
    }


@dataclass(frozen=True)
class Row:
    label: str
    individual: SimulationResult
    swarm: SimulationResult
    seconds: tuple[float, float]


def compare(label: str, a: StatSheet, na: int, b: StatSheet, nb: int, runs: int) -> Row:
    """Run one matchup through both engines."""
    matchup = matchup_of(na, nb)
    results, seconds = [], []
    # Changes a module-level constant and restores it in `finally`; not safe to run in threads.
    saved = c.SWARM_THRESHOLD
    try:
        for threshold in (ALWAYS_INDIVIDUAL, ALWAYS_SWARM):
            c.SWARM_THRESHOLD = threshold
            start = time.perf_counter()
            results.append(run(matchup, [a, b], runs=runs, explain=False))
            seconds.append(time.perf_counter() - start)
    finally:
        c.SWARM_THRESHOLD = saved
    return Row(label, results[0], results[1], (seconds[0], seconds[1]))


def table(rows: list[Row]) -> str:
    lines = [
        "| Fight | Win share side 0 (one-by-one / swarm) | Gap | Noise (95%) "
        "| Duration s (one-by-one / swarm) "
        "| Survivors side 0 | Survivors side 1 | Time s (one-by-one / swarm) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        i, s = r.individual, r.swarm
        gap = s.win_prob[0] - i.win_prob[0]
        p = i.win_prob[0]
        noise = 1.96 * math.sqrt(2 * p * (1 - p) / max(i.runs, 1))
        lines.append(
            f"| {r.label} | {i.win_prob[0]:.3f} / {s.win_prob[0]:.3f} | {gap:+.3f} "
            f"| {noise:.3f}{' (within noise)' if abs(gap) <= noise else ''} "
            f"| {i.mean_duration_s:.1f} / {s.mean_duration_s:.1f} "
            f"| {i.mean_survivors[0]:.1f} / {s.mean_survivors[0]:.1f} "
            f"| {i.mean_survivors[1]:.1f} / {s.mean_survivors[1]:.1f} "
            f"| {r.seconds[0]:.1f} / {r.seconds[1]:.2f} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    groups = scenarios()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--scenario", choices=["all", *groups], default="all")
    parser.add_argument("--runs", type=int, default=600, help="simulation runs per engine")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for name, fights in groups.items():
        if args.scenario not in ("all", name) or (args.scenario == "all" and name == "large"):
            continue  # "large" runs only when asked for: it is the slowest group (about 8 s at 300 runs)
        rows = [compare(label, a, na, b, nb, args.runs) for label, a, na, b, nb in fights]
        print(f"### {name}\n\n{table(rows)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
