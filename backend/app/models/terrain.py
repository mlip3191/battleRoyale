"""Where the fight happens."""

from enum import StrEnum


class Terrain(StrEnum):
    """The battlefield; it changes who can reach whom and how fast they move."""

    ARENA = "arena"
    OPEN_FIELD = "open_field"
    FOREST = "forest"
    WATER = "water"
    SHORELINE = "shoreline"
    URBAN = "urban"
    MOUNTAIN = "mountain"
    SKY = "sky"  # D-70: only fliers, and ranged attacks from the ground, reach a flier
