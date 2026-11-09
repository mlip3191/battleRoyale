"""Simulation output: probabilities, the fight log that gets replayed, and follow-up suggestions."""

from enum import StrEnum
from typing import Literal

from pydantic import Field

from app.models.base import Contract
from app.models.stats import StatName


class EventType(StrEnum):
    """What happened at one moment of the fight."""

    APPROACH = "approach"
    ATTACK = "attack"
    HIT = "hit"
    MISS = "miss"
    KO = "ko"
    RETREAT = "retreat"
    FLEE = "flee"
    STALEMATE = "stalemate"
    END = "end"


class FightEvent(Contract):
    """One moment in a simulated fight, replayed by the game and narrated."""

    t: float
    """Seconds since the start of the fight."""
    type: EventType
    """What happened."""
    side: Literal[0, 1]
    """Which side acted (0 = first fighter, 1 = second)."""
    actor: int | None = None
    """Index of the acting fighter within its side, or None for a group event."""
    target: int | None = None
    """Index of the fighter on the other side that was targeted, if any."""
    group_size: int = 1
    """How many fighters acted together (more than 1 for swarm events)."""
    damage: float | None = None
    """Damage dealt, when the event is a hit."""
    text_hint: str
    """Short neutral description for narration, e.g. "bite lands"."""


class SimulationResult(Contract):
    """The Monte Carlo verdict: who wins how often, and one representative fight."""

    seed: int
    """Seed of the random generator, so the result can be reproduced."""
    runs: int
    """How many fights were simulated."""
    win_prob: tuple[float, float]
    """Share of fights won by side 0 and by side 1."""
    draw_prob: float
    """Share of fights that ended in a draw."""
    win_prob_ci95: tuple[tuple[float, float], tuple[float, float]]
    """95% interval (low, high) for each side's win probability."""
    mean_survivors: tuple[float, float]
    """Average number of fighters left standing on each side."""
    mean_duration_s: float
    """Average fight length in seconds."""
    outcome: Literal["win_0", "win_1", "draw", "no_contest"]
    """Most likely result; no_contest means the two sides cannot engage."""
    deciding_factor: StatName | Literal["numbers", "terrain", "habitat", "abilities"]
    """The stat or circumstance that mattered most."""
    deciding_factor_explainer: str
    """Plain-language explanation of the deciding factor, written by a code template."""
    representative_log: list[FightEvent] = Field(max_length=300)
    """Events of one typical fight, capped at 300."""


class FairFight(Contract):
    """How many of one fighter would make the battle a coin flip."""

    varied_side: Literal[0, 1]
    """The side whose count was changed."""
    count: int | None
    """The count that gives about 50/50, or None when no fair fight exists within the limits."""
    win_prob_at_count: float | None
    """That side's win probability at the count."""
    message: str
    """Plain-language summary for the results page."""


class ChallengerSuggestion(Contract):
    """The next challenger to try against the winner."""

    entity: str
    """Name of the suggested fighter."""
    tested_win_prob: float
    """Its simulated win probability against the winner."""
    reason: str
    """Why it makes a good next fight."""
