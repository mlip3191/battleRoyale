"""Tests for the live evaluation's research scoring (M09 part 2, #51); no live calls."""

from collections import Counter

from app.models.stats import StatName, StatSheet, StatValue
from scripts import eval_research as er
from scripts.showcase_dry_run import seed_sheet


# A hand-verified value moved to `value`, as research might have found it.
def moved(value: StatValue, to: float) -> StatValue:
    return value.model_copy(update={"value": to, "method": "extracted"})


# The same value, but filled by a category default instead of a source.
def estimated(value: StatValue) -> StatValue:
    return value.model_copy(update={"method": "category_default", "is_estimate": True})


def test_values_land_in_the_right_bucket() -> None:
    mass = seed_sheet("horse").stats[StatName.MASS]
    assert er.classify(moved(mass, mass.value * 1.05), mass.value) == "within 10%"
    assert er.classify(moved(mass, mass.value * 0.8), mass.value) == "within 25%"
    assert er.classify(moved(mass, mass.value * 2), mass.value) == "wrong"
    assert er.classify(estimated(mass), mass.value) == "estimate"


def test_only_hand_verified_stats_are_compared() -> None:
    truth = seed_sheet("horse")
    research = truth.model_copy(
        update={"stats": {**truth.stats, StatName.MASS: moved(truth.stats[StatName.MASS], 9999.0)}}
    )
    result = er.Extraction()
    result.add(truth, research)
    compared = sum(sum(c.values()) for c in result.tally.values())
    assert compared == sum(v.method == "hand_verified" for v in truth.stats.values())
    if truth.stats[StatName.MASS].method == "hand_verified":
        assert result.tally["mass_kg"]["wrong"] == 1
        assert any("mass_kg" in line for line in result.wrong)


def test_the_extraction_table_totals_every_bucket() -> None:
    result = er.Extraction(fighters=2, rejected=3, quote_rejected=1)
    result.tally = {"mass_kg": Counter({"within 10%": 2}), "size_m": Counter({"estimate": 2})}
    text = er.extraction_markdown(result, 10.0)
    assert "| **All** | **2 (50%)** | **0 (0%)** | **0 (0%)** | **2 (50%)** |" in text
    assert "rejected by code: 3, of which 1 failed the quote check" in text


def test_coverage_counts_only_the_seven_physical_stats() -> None:
    sheet: StatSheet = seed_sheet("horse")
    counts = er.coverage_of(sheet)
    assert sum(counts.values()) == len(er.PHYSICAL) == 7
    assert set(counts) <= {"sourced", "derived", "estimate", "assumption"}


def test_the_coverage_table_shows_failures_and_the_app_gap() -> None:
    rows = [
        ("Moose", "animal", Counter({"sourced": 4, "derived": 1, "estimate": 2})),
        ("Forklift", "object or machine", "article not stored"),
    ]
    text = er.coverage_markdown(rows, ["Hippogriff: built on a horse"], 5.0)
    assert "| Moose | animal | 4 | 1 | 2 | 0 |" in text
    assert "| Forklift | object or machine | article not stored |" in text
    assert "#345" in text and "Hippogriff: built on a horse" in text


def test_the_new_fighters_are_on_neither_seed_list() -> None:
    from app.research.mythical import find_creature
    from app.research.seed_fighters import find_seed_fighter

    assert len(er.NEW_FIGHTERS) == 8 and len(er.NEW_LEGENDS) == 2
    for fighter in er.NEW_FIGHTERS:
        assert find_seed_fighter(fighter.display_name) is None
    for name in er.NEW_LEGENDS:
        assert find_creature(name) is None
