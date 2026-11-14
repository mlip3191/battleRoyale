"""Balance check for loadouts (#283): at the same number of points, which kit wins?

From the repo root:
  uv run --directory backend python scripts/loadout_balance.py [--runs 150] [--points 2 4]

Every seed fighter fights every other seed fighter (unequipped) on the arena, with every kit that
spends exactly the same number of points (a kit with more points would win just for having more).
Only contested pairs count (the unequipped win share is between 10% and 90%): a lopsided fight
cannot show anything. For each budget the report says what shape of kit is best (everything in one
loadout, two loadouts, three or four), how often the fighter's own primary attribute is the best
all-in choice, and flags a kit that is best too often (a dominant strategy, which makes the choice
meaningless). It is a report, not a test: the numbers move with the assumptions in `constants.py`.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.stats import StatSheet  # noqa: E402
from app.models.terrain import Terrain  # noqa: E402
from app.simulation import constants as c  # noqa: E402
from app.simulation.loadout_preview import win_share  # noqa: E402
from app.simulation.loadouts import MAX_TIER, archetype_of, primary_of  # noqa: E402

SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "fighters"
DOMINANT = 0.5  # a kit shape or kit that is best in more than half of the contested pairs


def sheets() -> dict[str, StatSheet]:
    return {
        f.stem: StatSheet.model_validate(json.loads(f.read_text("utf-8")))
        for f in sorted(SEED.glob("*.json"))
    }


def kits_with(points: int) -> list[dict[str, int]]:
    """Every kit that spends exactly `points` (each loadout at tier 0 to the top tier)."""
    leans = list(c.LOADOUTS)
    found = []
    for tiers in product(range(MAX_TIER + 1), repeat=len(leans)):
        if sum(tiers) == points:
            found.append({lean: t for lean, t in zip(leans, tiers, strict=True) if t})
    return found


def shape(kit: dict[str, int]) -> str:
    return {1: "all in one loadout", 2: "two loadouts"}.get(len(kit), "three or four loadouts")


def label(kit: dict[str, int]) -> str:
    return " + ".join(f"{lean} {tier}" for lean, tier in kit.items())


def report(points: int, runs: int) -> None:
    fighters = sheets()
    kits = kits_with(points)
    shapes: Counter[str] = Counter()
    winners: Counter[str] = Counter()
    primary_best = 0
    primary_total = 0
    edge: list[float] = []
    by_kind: dict[str, Counter[str]] = defaultdict(Counter)
    contested = 0
    for name, sheet in fighters.items():
        own = {primary_of(sheet): points} if points <= MAX_TIER else None
        for other_name, other in fighters.items():
            if other_name == name:
                continue
            base = win_share(sheet, {}, other, None, Terrain.ARENA, runs)
            if not 0.1 <= base <= 0.9:
                continue
            contested += 1
            shares = {
                label(kit): win_share(sheet, kit, other, None, Terrain.ARENA, runs) for kit in kits
            }
            best_label = max(shares, key=lambda k: shares[k])
            best_kit = next(kit for kit in kits if label(kit) == best_label)
            shapes[shape(best_kit)] += 1
            winners[best_label] += 1
            by_kind[archetype_of(sheet)][shape(best_kit)] += 1
            edge.append(shares[best_label] - base)
            if own and primary_of(sheet) != "balanced":
                primary_total += 1
                if best_kit == own:
                    primary_best += 1
    print(f"## {points} points ({len(kits)} kits, {contested} contested pairs, {runs} runs)\n")
    if not contested:
        print("No contested pairs.\n")
        return
    print("| Best kit is | Pairs | Share |")
    print("|---|---|---|")
    for name, count in shapes.most_common():
        share = count / contested
        flag = " **DOMINANT SHAPE**" if share > DOMINANT else ""
        print(f"| {name} | {count} | {share:.0%}{flag} |")
    top, count = winners.most_common(1)[0]
    flag = " **DOMINANT KIT**" if count / contested > DOMINANT else ""
    print(f"\n- Most common best kit: **{top}** ({count}/{contested}){flag}")
    print(f"- Distinct best kits: {len(winners)} of {len(kits)}")
    print(f"- Mean gain of the best kit over no kit: {sum(edge) / len(edge) * 100:+.1f} points")
    if primary_total:
        print(f"- All points in its primary attribute is best: {primary_best}/{primary_total}")
    for kind, counts in sorted(by_kind.items()):
        total = sum(counts.values())
        print(
            f"- {kind}: "
            + ", ".join(f"{n} {s}" for s, n in counts.most_common())
            + f" (of {total})"
        )
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=150)
    parser.add_argument("--points", type=int, nargs="+", default=[2, 4])
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("# Loadout balance: kits with the same number of points\n")
    for points in args.points:
        report(points, args.runs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
