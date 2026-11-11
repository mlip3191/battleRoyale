"""The numbers the results page and the announcer need, in one place."""

from dataclasses import dataclass
from typing import Literal

from app.models.simulation import SimulationResult


@dataclass(frozen=True)
class Summary:
    """A plain view of a SimulationResult (not a shared contract)."""

    win_pct: tuple[float, float]
    """Win chance of each side, in percent, to one decimal."""
    draw_pct: float
    survivors: tuple[float, float]
    """Average fighters left on each side."""
    duration_s: float
    outcome: Literal["win_0", "win_1", "draw", "no_contest"]
    favorite: Literal[0, 1] | None
    """The side more likely to win, or None for a draw, no contest, or an exact tie."""
    favorite_name: str | None
    deciding_factor: str
    deciding_factor_text: str


def summary(result: SimulationResult, names: tuple[str, str]) -> Summary:
    """Summarize a result. `names` are the two display names, in side order."""
    p0, p1 = result.win_prob
    favorite: Literal[0, 1] | None = None
    if result.outcome in ("win_0", "win_1") and p0 != p1:
        favorite = 0 if p0 > p1 else 1
    return Summary(
        win_pct=(round(p0 * 100, 1), round(p1 * 100, 1)),
        draw_pct=round(result.draw_prob * 100, 1),
        survivors=(round(result.mean_survivors[0], 1), round(result.mean_survivors[1], 1)),
        duration_s=round(result.mean_duration_s, 1),
        outcome=result.outcome,
        favorite=favorite,
        favorite_name=None if favorite is None else names[favorite],
        deciding_factor=str(result.deciding_factor),
        deciding_factor_text=result.deciding_factor_explainer,
    )
