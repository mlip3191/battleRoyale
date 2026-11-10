"""Plausible ranges for each value, and sanity limits that reject impossible ones."""

import logging

from app.models.stats import Confidence, StatName

logger = logging.getLogger(__name__)

SPREAD: dict[Confidence, float] = {
    Confidence.HIGH: 0.10,
    Confidence.MEDIUM: 0.25,
    Confidence.LOW: 0.50,
}
ZERO_TO_ONE = {StatName.ARMOR, StatName.AGGRESSION, StatName.GROUP_TACTICS}

# Wide enough for insects and for vehicles; anything outside these is a bad reading.
SANITY_BOUNDS: dict[StatName, tuple[float, float]] = {
    StatName.MASS: (0.000001, 1_000_000_000.0),
    StatName.SIZE: (0.000001, 100_000.0),
    StatName.SPEED: (0.0, 1_000.0),
    StatName.ATTACK_FORCE: (0.0, 1_000_000_000.0),
    StatName.ATTACK_RATE: (0.0, 100.0),
    StatName.REACH: (0.0, 100_000.0),
    StatName.ARMOR: (0.0, 1.0),
    StatName.ENDURANCE: (0.0, 1_000_000.0),
    StatName.AGGRESSION: (0.0, 1.0),
    StatName.GROUP_TACTICS: (0.0, 1.0),
}


# The source's range if it gave one that contains the value, else the spread for its confidence.
def range_for(
    stat: StatName,
    value: float,
    confidence: Confidence,
    source_low: float | None = None,
    source_high: float | None = None,
) -> tuple[float, float]:
    # A source that gives only one end of a range is treated as giving none: the spread applies.
    if source_low is not None and source_high is not None:
        if not source_low <= value <= source_high:
            raise ValueError(f"{stat}: value {value} is outside its range")
        return source_low, source_high
    spread = SPREAD[confidence]
    low, high = round(value * (1 - spread), 10), round(value * (1 + spread), 10)
    return low, min(high, 1.0) if stat in ZERO_TO_ONE else high


# True when the value is possible for this stat; a rejected value is logged.
def within_sanity_bounds(stat: StatName, value: float) -> bool:
    lowest, highest = SANITY_BOUNDS[stat]
    if lowest <= value <= highest:
        return True
    logger.warning("Rejected %s = %s: outside %s to %s.", stat.value, value, lowest, highest)
    return False
