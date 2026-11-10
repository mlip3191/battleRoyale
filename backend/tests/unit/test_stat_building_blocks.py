"""Unit conversion, the evidence check, ranges, sanity limits, and category defaults."""

import logging
import re

import pytest

from app.config import REPO_ROOT
from app.models.stats import Confidence, StatName
from app.research.defaults import (
    CATEGORY_LEVELS,
    PHYSICAL_DEFAULTS,
    PHYSICAL_ORDER,
    RUBRICS,
    behavioral_default,
    category_default,
)
from app.research.evidence_check import (
    evidence_is_valid,
    number_in_quote,
    numbers_in,
    quote_in_passage,
)
from app.research.ranges import range_for, within_sanity_bounds
from app.research.units import UnitError, to_stat_unit

BEHAVIORAL = (StatName.AGGRESSION, StatName.GROUP_TACTICS, StatName.ARMOR)
RESEARCH_DOC = (REPO_ROOT / "docs" / "research.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("value", "unit", "stat", "expected"),
    [
        (100, "lb", StatName.MASS, 45.359237),
        (100, "lbs", StatName.MASS, 45.359237),
        (2, "pounds", StatName.MASS, 0.90718474),
        (6.9, "t", StatName.MASS, 6900),
        (36, "km/h", StatName.SPEED, 10),
        (10, "kilometres per hour", StatName.SPEED, 2.7777777778),
        (30, "mph", StatName.SPEED, 13.4112),
        (10, "ft", StatName.SIZE, 3.048),
        (6, "feet", StatName.REACH, 1.8288),
        (157, "cm", StatName.SIZE, 1.57),
        (3690, "lbf", StatName.ATTACK_FORCE, 16413.94776),
        (2, "kN", StatName.ATTACK_FORCE, 2000),
        (20, "minutes", StatName.ENDURANCE, 1200),
        (2, "hours", StatName.ENDURANCE, 7200),
        (40, "kg", StatName.MASS, 40),
    ],
)
def test_units_convert(value: float, unit: str, stat: StatName, expected: float) -> None:
    assert to_stat_unit(value, unit, stat) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("unit", "stat"),
    [("furlongs", StatName.SIZE), ("kg", StatName.SIZE), ("m", StatName.AGGRESSION)],
)
def test_unknown_or_wrong_units_are_refused(unit: str, stat: StatName) -> None:
    with pytest.raises(UnitError):
        to_stat_unit(1, unit, stat)


def test_numbers_are_read_whole() -> None:
    assert numbers_in("weigh 1,000–1,500 kg and 3.5 m") == [1000, 1500, 3.5]
    assert not number_in_quote(40, "it weighs 140 kg")
    assert not number_in_quote(1, "it weighs 1,500 kg")


def test_number_words_do_not_count() -> None:
    assert not number_in_quote(20, "it can run for twenty minutes")


def test_quotes_match_across_dash_and_spacing_differences() -> None:
    passage = "Males weigh 9\nto 16\xa0kg, and are 55–77 cm long."
    assert quote_in_passage("weigh 9 to 16 kg", passage)
    assert quote_in_passage("55-77 cm long", passage)
    assert not quote_in_passage("weigh 9 to 18 kg", passage)
    assert not quote_in_passage("   ", passage)


def test_evidence_needs_both_the_number_and_the_quote() -> None:
    passage = "The mean body mass of the wolf is 40 kg (88 lb)."
    assert evidence_is_valid(40, "mass of the wolf is 40 kg", passage)
    assert evidence_is_valid(88, "40 kg (88 lb)", passage)
    assert not evidence_is_valid(45, "mass of the wolf is 40 kg", passage)  # number not in quote
    assert not evidence_is_valid(45, "mass of the wolf is 45 kg", passage)  # quote not in passage


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (Confidence.HIGH, (90.0, 110.0)),
        (Confidence.MEDIUM, (75.0, 125.0)),
        (Confidence.LOW, (50.0, 150.0)),
    ],
)
def test_ranges_follow_confidence(confidence: Confidence, expected: tuple[float, float]) -> None:
    assert range_for(StatName.MASS, 100, confidence) == expected


def test_a_source_range_wins_and_must_contain_the_value() -> None:
    assert range_for(StatName.MASS, 40, Confidence.HIGH, 25, 54) == (25, 54)
    with pytest.raises(ValueError):
        range_for(StatName.MASS, 60, Confidence.HIGH, 25, 54)


def test_one_end_of_a_range_alone_falls_back_to_the_spread() -> None:
    assert range_for(StatName.MASS, 100, Confidence.HIGH, source_low=80) == (90.0, 110.0)
    assert range_for(StatName.MASS, 100, Confidence.HIGH, source_high=150) == (90.0, 110.0)


def test_zero_to_one_stats_never_exceed_one() -> None:
    assert range_for(StatName.AGGRESSION, 0.9, Confidence.LOW) == (0.45, 1.0)


def test_sanity_bounds_reject_and_log(caplog: pytest.LogCaptureFixture) -> None:
    assert within_sanity_bounds(StatName.MASS, 6900)
    assert within_sanity_bounds(StatName.SPEED, 0)
    with caplog.at_level(logging.WARNING, logger="app.research.ranges"):
        assert not within_sanity_bounds(StatName.SPEED, 5000)
        assert not within_sanity_bounds(StatName.MASS, -1)
    assert "top_speed_mps" in caplog.text and "mass_kg" in caplog.text


def test_every_category_gets_valid_estimates() -> None:
    for category in PHYSICAL_DEFAULTS:
        for stat in PHYSICAL_ORDER:
            stat_value = category_default(category, stat)
            if stat_value is None:
                assert category in {"vehicle", "machine"}
                continue
            assert stat_value.method == "category_default" and stat_value.is_estimate
            assert stat_value.confidence == Confidence.LOW
            assert stat_value.low is not None and stat_value.high is not None
            assert within_sanity_bounds(stat, stat_value.value)


def test_every_category_gets_rubric_assumptions() -> None:
    for category in CATEGORY_LEVELS:
        for stat in BEHAVIORAL:
            stat_value = behavioral_default(category, stat)
            assert stat_value.method == "assumption" and stat_value.is_estimate
            assert stat_value.note and re.match(
                r"^(aggression|group tactics|armor|durability) level (\d|M): \S", stat_value.note
            )
            assert stat_value.low is not None and stat_value.high is not None
            assert stat_value.high <= 1.0


def test_behavioral_values_use_the_right_scale() -> None:
    assert behavioral_default("vehicle", StatName.ARMOR).note.startswith("durability level 3")
    assert behavioral_default("vehicle", StatName.ARMOR).value == 0.55
    assert behavioral_default("vehicle", StatName.AGGRESSION).value == 1.0
    assert behavioral_default("mammal", StatName.GROUP_TACTICS).value == 0.3


def test_mythical_creatures_and_non_behavioral_stats_are_refused() -> None:
    with pytest.raises(ValueError):
        category_default("mythical", StatName.MASS)
    with pytest.raises(ValueError):
        behavioral_default("mammal", StatName.MASS)


def _expanded(names: str) -> list[str]:
    return [name.strip() for name in names.split(",")]


# Reads the tables in docs/research.md, so update this if those tables change shape.
def test_physical_defaults_match_the_research_doc() -> None:
    section = RESEARCH_DOC.split("## Category defaults")[1].split("## The three")[0]
    rows = re.findall(r"^\| ([a-z_, ]+) \| (.+) \|$", section, re.MULTILINE)
    assert len(rows) == 14
    for names, cells in rows:
        expected = [
            None if cell.strip().startswith("derived") else float(cell) for cell in cells.split("|")
        ]
        for name in _expanded(names):
            assert list(PHYSICAL_DEFAULTS[name]) == expected, name


def test_rubric_levels_match_the_research_doc() -> None:
    section = RESEARCH_DOC.split("### Default level by category")[1].split("## Source policy")[0]
    rows = re.findall(
        r"^\| ([a-z_, ]+) \| (\w) \| (\w) \| (Armor|Durability) (\d) \|$", section, re.M
    )
    assert len(rows) == 13
    for names, aggression, group, scale, level in rows:
        for name in _expanded(names):
            actual = CATEGORY_LEVELS[name]
            assert str(actual[0]) == aggression and str(actual[1]) == group, name
            assert actual[2] == (scale.lower(), int(level)), name


def test_rubric_values_match_the_research_doc() -> None:
    for heading, rubric in [
        ("### Aggression", "aggression"),
        ("### Group tactics", "group tactics"),
        ("### Armor", "armor"),
        ("### Durability", "durability"),
    ]:
        section = RESEARCH_DOC.split(heading)[1].split("###")[0]
        rows = re.findall(r"^\| (\d|M) \| ([\d.]+) \|", section, re.MULTILINE)
        assert rows, rubric
        table = {int(k) if k.isdigit() else k: float(v) for k, v in rows}
        assert {k: v[0] for k, v in RUBRICS[rubric].items()} == table, rubric
