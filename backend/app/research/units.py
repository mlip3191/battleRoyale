"""Convert a number from the unit a source used to the unit a stat is stored in."""

from app.models.stats import StatName


class UnitError(ValueError):
    """The unit is unknown, or doesn't measure what this stat measures."""


STAT_UNITS: dict[StatName, str] = {
    StatName.MASS: "kg",
    StatName.SIZE: "m",
    StatName.SPEED: "m/s",
    StatName.ATTACK_FORCE: "N",
    StatName.ATTACK_RATE: "1/s",
    StatName.REACH: "m",
    StatName.ARMOR: "0-1",
    StatName.ENDURANCE: "s",
    StatName.AGGRESSION: "0-1",
    StatName.GROUP_TACTICS: "0-1",
}

# How many of each stored unit one source unit equals, written in lowercase singular.
FACTORS: dict[str, dict[str, float]] = {
    "kg": {
        "kg": 1.0,
        "kilogram": 1.0,
        "kilogramme": 1.0,
        "g": 0.001,
        "gram": 0.001,
        "mg": 0.000001,
        "milligram": 0.000001,
        "t": 1000.0,
        "tonne": 1000.0,
        "metric ton": 1000.0,
        "lb": 0.45359237,
        "pound": 0.45359237,
        "oz": 0.028349523125,
        "ounce": 0.028349523125,
        "short ton": 907.18474,
        "long ton": 1016.0469088,
    },
    "m": {
        "m": 1.0,
        "metre": 1.0,
        "meter": 1.0,
        "cm": 0.01,
        "centimetre": 0.01,
        "centimeter": 0.01,
        "mm": 0.001,
        "millimetre": 0.001,
        "millimeter": 0.001,
        "km": 1000.0,
        "kilometre": 1000.0,
        "kilometer": 1000.0,
        "ft": 0.3048,
        "foot": 0.3048,
        "feet": 0.3048,
        "in": 0.0254,
        "inch": 0.0254,
        "inche": 0.0254,  # not a typo: what _normalize makes of "inches"
        "yd": 0.9144,
        "yard": 0.9144,
    },
    "m/s": {
        "m/s": 1.0,
        "metre per second": 1.0,
        "meter per second": 1.0,
        "km/h": 1 / 3.6,
        "kph": 1 / 3.6,
        "kilometre per hour": 1 / 3.6,
        "kilometer per hour": 1 / 3.6,
        "mph": 0.44704,
        "mile per hour": 0.44704,
        "ft/s": 0.3048,
        "knot": 0.514444,
        "kn": 0.514444,
    },
    "N": {
        "n": 1.0,
        "newton": 1.0,
        "kn": 1000.0,
        "kilonewton": 1000.0,
        "lbf": 4.4482216152605,
        "kgf": 9.80665,
    },
    "1/s": {
        "1/s": 1.0,
        "per second": 1.0,
        "per minute": 1 / 60,
    },
    "s": {
        "s": 1.0,
        "sec": 1.0,
        "second": 1.0,
        "min": 60.0,
        "minute": 60.0,
        "h": 3600.0,
        "hr": 3600.0,
        "hour": 3600.0,
    },
}


# Lowercase a unit and turn plural words such as "metres per second" into their singular.
def _normalize(unit: str) -> str:
    text = " ".join(unit.strip().rstrip(".").lower().split())
    words = text.split(" ")
    words[0] = words[0][:-1] if len(words[0]) > 2 and words[0].endswith("s") else words[0]
    return " ".join(words)


# Return the value in the unit this stat is stored in.
def to_stat_unit(value: float, unit: str, stat: StatName) -> float:
    target = STAT_UNITS[stat]
    table = FACTORS.get(target)
    if table is None:
        raise UnitError(f"{stat} is not measured in a physical unit")
    written = unit.strip().lower()
    factor = table.get(written, table.get(_normalize(unit)))
    if factor is None:
        raise UnitError(f"{unit!r} can't be converted to {target} for {stat}")
    return value * factor
