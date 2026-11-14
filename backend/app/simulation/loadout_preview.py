"""What would each choice do? A pre-fight preview of the odds for every loadout choice (#283).

Before a round the user adds a loadout or upgrades one. `preview_choices` runs a short simulation
for each possible choice and says how the win share would move, so a hidden multiplier becomes a
decision the user can read ("with the shield: 41%, with the axe: 55%"). Every number is a
simulator result for the two sheets as they stand (the loadout multipliers are assumptions, but
the percentages are real simulation output), and the preview is deterministic: the same inputs
give the same previews.
"""

import math
from dataclasses import dataclass

from app.models.matchup import FighterRequest, Matchup
from app.models.stats import StatSheet
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import run
from app.simulation.loadouts import (
    Kit,
    add_or_upgrade,
    apply_kit,
    archetype_of,
    available_choices,
    item_name,
)

PREVIEW_RUNS = 200  # quick: the answer is a nudge, not a verdict


@dataclass(frozen=True)
class ChoicePreview:
    """What one choice would do: the loadout, its new tier, the item and the odds."""

    lean: str
    tier_after: int
    adds: bool  # True when it adds a new loadout, False when it upgrades one already carried
    item: str  # the item name for this fighter, e.g. "razor claws"
    win_share: float  # the fighter's chance of winning after the choice (0 to 1)
    change: float  # win_share minus the current win share, in points of probability
    noise: float  # 95% noise of that change at this many runs (about 0.07 at 200 runs)
    clear: bool  # True when the change is bigger than the noise, so it is a real effect


def win_share(
    sheet: StatSheet,
    kit: Kit,
    opponent: StatSheet,
    opponent_kit: Kit | None = None,
    terrain: Terrain = Terrain.ARENA,
    runs: int = PREVIEW_RUNS,
) -> float:
    """The fighter's chance of beating the opponent, with each side's kit applied (1 v 1)."""
    fighters = [apply_kit(sheet, kit), apply_kit(opponent, opponent_kit or {})]
    matchup = Matchup(
        fighters=[FighterRequest(entity=s.fighter_id, raw=s.display_name) for s in fighters],
        terrain=terrain,
        raw_text=f"{fighters[0].display_name} vs {fighters[1].display_name}",
    )
    return run(matchup, fighters, runs=runs, explain=False).win_prob[0]


def preview_choices(
    sheet: StatSheet,
    kit: Kit,
    opponent: StatSheet,
    opponent_kit: Kit | None = None,
    terrain: Terrain = Terrain.ARENA,
    runs: int = PREVIEW_RUNS,
) -> list[ChoicePreview]:
    """Every choice open to the fighter, best first, with how it would move the odds.

    A choice is one point: add a loadout it does not carry, or upgrade one it does, up to the
    top tier. The opponent's kit (what the user can see before choosing) is part of the fight, so
    the best choice depends on who is across the ring.
    """
    now = win_share(sheet, kit, opponent, opponent_kit, terrain, runs)
    archetype = archetype_of(sheet)
    previews = []
    for lean in available_choices(kit):
        grown = add_or_upgrade(kit, lean)
        after = win_share(sheet, grown, opponent, opponent_kit, terrain, runs)
        spread = (now * (1 - now) + after * (1 - after)) / runs
        noise = 1.96 * math.sqrt(max(spread, 1.0 / runs / runs))
        previews.append(
            ChoicePreview(
                lean=lean,
                tier_after=grown[lean],
                adds=lean not in kit,
                item=item_name(archetype, lean, grown[lean]),
                win_share=after,
                change=after - now,
                noise=noise,
                clear=abs(after - now) > noise,
            )
        )
    return sorted(previews, key=lambda p: (-p.change, list(c.LOADOUTS).index(p.lean)))
