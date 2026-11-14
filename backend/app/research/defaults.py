"""Category defaults and rubric levels from docs/research.md, used when there is no evidence."""

from typing import Literal

from app.models.stats import Confidence, StatName, StatValue
from app.research.ranges import range_for
from app.research.units import STAT_UNITS

PHYSICAL_ORDER = (
    StatName.MASS,
    StatName.SIZE,
    StatName.SPEED,
    StatName.ATTACK_FORCE,
    StatName.ATTACK_RATE,
    StatName.REACH,
    StatName.ENDURANCE,
)

# Mass, size, speed, force, attack rate, reach, endurance. None means code derives it (G09).
PHYSICAL_DEFAULTS: dict[str, tuple[float | None, ...]] = {
    "mammal": (50, 1.2, 12, 500, 1.5, 0.4, 300),
    "bird": (2, 0.5, 18, 30, 2, 0.15, 300),
    "reptile": (20, 1.5, 4, 300, 1, 0.3, 120),
    "amphibian": (0.2, 0.12, 1, 2, 1, 0.03, 60),
    "fish": (10, 0.8, 6, 150, 1, 0.2, 300),
    "insect": (0.0001, 0.01, 0.5, 0.01, 3, 0.003, 600),
    "arachnid": (0.002, 0.02, 0.5, 0.05, 2, 0.005, 300),
    "mollusk": (0.2, 0.2, 0.2, 2, 0.5, 0.05, 600),
    "dinosaur": (1000, 5, 8, 5000, 0.8, 1.2, 180),
    "human_archetype": (70, 1.75, 8, 400, 1, 1, 600),
    "vehicle": (3000, 5, 25, None, None, 1, 3600),
    "machine": (1000, 3, 5, None, None, 1, 3600),
    "plant": (50, 3, 0, 0, 0, 0, 600),
    "object": (1, 0.3, 0, 0, 0, 0, 600),
    "other": (1, 0.3, 0, 0, 0, 0, 600),
}

Level = int | Literal["M"]
Rubric = Literal["aggression", "group tactics", "armor", "durability"]

# Each rubric level's value and description.
RUBRICS: dict[Rubric, dict[Level, tuple[float, str]]] = {
    "aggression": {
        0: (0.0, "inanimate, an object or plant"),
        1: (0.1, "flees from almost everything"),
        2: (0.3, "flees first, fights when cornered"),
        3: (0.5, "hunts or defends itself, avoids risky fights"),
        4: (0.7, "territorial, confident against most animals"),
        5: (0.9, "attacks animals larger than itself"),
        "M": (1.0, "operated to win, a machine with a driver"),
    },
    "group tactics": {
        0: (0.0, "inanimate, an object or plant"),
        1: (0.1, "solitary, fights alone"),
        2: (0.3, "gathers in groups, but each acts alone"),
        3: (0.5, "family or herd that defends together"),
        4: (0.8, "pack that hunts in coordination"),
        5: (1.0, "colony or drilled unit acting as one"),
    },
    "armor": {
        1: (0.15, "fur, feathers, or bare skin"),
        2: (0.3, "thick fur, fat, or loose tough skin"),
        3: (0.45, "very thick hide"),
        4: (0.6, "bony plates in the skin, or metal body armor"),
        5: (0.8, "a full hard shell, or full plate"),
    },
    "durability": {
        1: (0.1, "brittle, shatters easily"),
        2: (0.4, "thin sheet metal, or a tough plant"),
        3: (0.55, "ordinary vehicle body"),
        4: (0.7, "heavy steel construction"),
        5: (0.8, "tank armor"),
    },
}

# Aggression level, group tactics level, and the armor or durability scale with its level.
CATEGORY_LEVELS: dict[str, tuple[Level, Level, tuple[Rubric, Level]]] = {
    "mammal": (3, 2, ("armor", 1)),
    "bird": (2, 2, ("armor", 1)),
    "reptile": (3, 1, ("armor", 3)),
    "amphibian": (1, 1, ("armor", 1)),
    "fish": (3, 2, ("armor", 2)),
    "insect": (3, 3, ("armor", 2)),
    "arachnid": (3, 1, ("armor", 2)),
    "mollusk": (2, 1, ("armor", 3)),
    "dinosaur": (4, 2, ("armor", 3)),
    "human_archetype": (4, 4, ("armor", 4)),
    "vehicle": ("M", 2, ("durability", 3)),
    "machine": ("M", 2, ("durability", 3)),
    "plant": (0, 0, ("durability", 2)),
    "object": (0, 0, ("durability", 2)),
    "other": (0, 0, ("durability", 2)),
}


# The labeled estimate for a physical stat, or None if code must derive it instead.
def category_default(category: str, stat: StatName) -> StatValue | None:
    value = PHYSICAL_DEFAULTS[_known(category)][PHYSICAL_ORDER.index(stat)]
    if value is None:
        return None
    low, high = range_for(stat, float(value), Confidence.LOW)
    return StatValue(
        value=float(value),
        unit=STAT_UNITS[stat],
        confidence=Confidence.LOW,
        is_estimate=True,
        method="category_default",
        low=low,
        high=high,
        note=f"Category default for {category}: no evidence found.",
    )


# The rubric-based assumption for a behavioral stat, at the category's default level.
def behavioral_default(category: str, stat: StatName) -> StatValue:
    aggression, group, (armor_scale, armor_level) = CATEGORY_LEVELS[_known(category)]
    rubric: Rubric
    level: Level
    if stat == StatName.AGGRESSION:
        rubric, level = "aggression", aggression
    elif stat == StatName.GROUP_TACTICS:
        rubric, level = "group tactics", group
    elif stat == StatName.ARMOR:
        rubric, level = armor_scale, armor_level
    else:
        raise ValueError(f"{stat} is not a behavioral stat")
    value, reason = RUBRICS[rubric][level]
    low, high = range_for(stat, value, Confidence.LOW)
    return StatValue(
        value=value,
        unit=STAT_UNITS[stat],
        confidence=Confidence.LOW,
        is_estimate=True,
        method="assumption",
        low=low,
        high=high,
        note=f"{rubric} level {level}: {reason}.",
    )


# Mythical creatures are built from their analogs (G09), so they have no defaults here.
def _known(category: str) -> str:
    if category not in PHYSICAL_DEFAULTS:
        raise ValueError(f"no defaults for category {category!r}")
    return category
