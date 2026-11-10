"""Every hand-verified seed sheet must follow the number rule and the G05 limits."""

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.stats import ASSUMABLE_STATS, StatName, StatSheet, StatValue
from app.research.bite_force import average_carnivore_bite_n
from app.research.sheet_hash import compute_sheet_hash

FIGHTERS_DIR = Path(__file__).parents[3] / "data" / "seed" / "fighters"
SHEET_PATHS = sorted(FIGHTERS_DIR.glob("*.json"))
PHYSICAL_STATS = [name for name in StatName if name not in ASSUMABLE_STATS]
RUBRIC_NOTE = re.compile(r"^(aggression|group tactics|armor|durability) level (\d|M): \S")
MAX_ESTIMATES = 2
EXCEPTIONS = {"duck": 3, "honey-badger": 3}  # PM decision D-47 (2): these two may have 3

# Units a quote may use: as stored, km/h for m/s, cm for m, minutes for s, tonnes for kg, and
# kilograms of force for newtons.
CONVERSIONS = {
    "m/s": (1.0, 3.6),
    "m": (1.0, 100.0),
    "s": (1.0, 1 / 60),
    "kg": (1.0, 0.001),
    "N": (1.0, 1 / 9.80665),
}


# Load one sheet file through the shared contract.
def load_sheet(path: Path) -> StatSheet:
    return StatSheet.model_validate(json.loads(path.read_text(encoding="utf-8")))


# True when the quote contains the stored value, directly or in a unit the source used.
def quote_has_number(stat: StatValue) -> bool:
    assert stat.source is not None
    found = re.findall(r"\d[\d,]*(?:\.\d+)?", stat.source.quote)
    numbers = [float(n.replace(",", "")) for n in found]
    factors = CONVERSIONS.get(stat.unit, (1.0,))
    return any(abs(number - stat.value * f) < 0.05 for number in numbers for f in factors)


def test_sheets_exist() -> None:
    assert SHEET_PATHS, f"no seed sheets found in {FIGHTERS_DIR}"


@pytest.mark.parametrize("path", SHEET_PATHS, ids=lambda p: p.stem)
class TestSeedSheet:
    def test_file_name_matches_fighter_id(self, path: Path) -> None:
        assert load_sheet(path).fighter_id == path.stem

    def test_stored_hash_is_correct(self, path: Path) -> None:
        sheet = load_sheet(path)
        assert sheet.sheet_hash == compute_sheet_hash(sheet.stats)

    def test_hand_verified_values_have_a_source_and_quote(self, path: Path) -> None:
        for name, stat in load_sheet(path).stats.items():
            if stat.method == "hand_verified":
                assert stat.source is not None and stat.source.quote.strip(), name

    def test_hand_verified_quote_contains_the_number(self, path: Path) -> None:
        for name, stat in load_sheet(path).stats.items():
            if stat.method == "hand_verified":
                assert quote_has_number(stat), f"{name}: {stat.value} not in the quote"

    def test_behavioral_stats_are_rubric_assumptions(self, path: Path) -> None:
        sheet = load_sheet(path)
        for name in ASSUMABLE_STATS:
            stat = sheet.stats[name]
            assert stat.method == "assumption", name
            assert stat.note and RUBRIC_NOTE.match(stat.note), f"{name}: {stat.note}"

    def test_every_value_has_a_range(self, path: Path) -> None:
        for name, stat in load_sheet(path).stats.items():
            assert stat.low is not None and stat.high is not None, name

    def test_derived_reach_follows_the_formula(self, path: Path) -> None:
        sheet = load_sheet(path)
        reach, size = sheet.stats[StatName.REACH], sheet.stats[StatName.SIZE]
        if reach.method == "derived":
            formula = 0.25 * size.value  # stored values are rounded to the centimetre
            assert reach.value == pytest.approx(formula, abs=0.006)
            assert reach.low == pytest.approx(0.75 * formula, abs=0.006)
            assert reach.high == pytest.approx(1.25 * formula, abs=0.006)

    def test_derived_attack_force_comes_from_the_code_fit(self, path: Path) -> None:
        sheet = load_sheet(path)
        force = sheet.stats[StatName.ATTACK_FORCE]
        if force.method == "derived" and "bite_force" in (force.note or ""):
            expected = average_carnivore_bite_n(sheet.stats[StatName.MASS].value)
            assert force.value == pytest.approx(expected, abs=0.5)

    def test_at_most_two_physical_estimates(self, path: Path) -> None:
        sheet = load_sheet(path)
        estimates = [str(n) for n in PHYSICAL_STATS if sheet.stats[n].is_estimate]
        allowed = EXCEPTIONS.get(path.stem, MAX_ESTIMATES)
        assert len(estimates) <= allowed, f"{path.stem} estimates: {estimates}"


def test_the_estimate_exception_covers_only_duck_and_honey_badger() -> None:
    assert set(EXCEPTIONS) == {"duck", "honey-badger"}
    assert all(limit == MAX_ESTIMATES + 1 for limit in EXCEPTIONS.values())


def test_hand_verified_without_a_source_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StatValue(
            value=1.0, unit="kg", confidence="high", is_estimate=False, method="hand_verified"
        )


def test_hash_changes_when_a_value_changes() -> None:
    sheet = load_sheet(SHEET_PATHS[0])
    changed = dict(sheet.stats)
    mass = changed[StatName.MASS]
    changed[StatName.MASS] = mass.model_copy(update={"value": mass.value + 1})
    assert compute_sheet_hash(sheet.stats) != compute_sheet_hash(changed)
