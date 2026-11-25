"""#562: an unlisted object or machine is sized by its class, not a 1 kg placeholder."""

import pytest

from app.models.matchup import FighterRequest, Matchup
from app.models.stats import Body, StatName
from app.pipeline import stages
from app.research import lore
from app.research.estimate_sheet import SIZE_MASSES, STAND_IN_NOTE, estimate_sheet
from app.simulation.engine import run

BUS_IN_WATER = "a school bus vs a great white shark in the water"


# The bug bash's matchup, with the bus sized by `size_class` and a shark of `shark_class`.
def bus_vs_shark(size_class: str | None, shark_class: str = "huge") -> str:
    fight = Matchup.model_validate(
        {
            "fighters": [
                {"entity": "school bus", "raw": "a school bus"},
                {"entity": "great white shark", "raw": "a great white shark"},
            ],
            "terrain": "water",
            "raw_text": BUS_IN_WATER,
        }
    )
    bus = estimate_sheet("school bus", "object_or_machine", size_class=size_class)
    shark = estimate_sheet(
        "great white shark", "real_animal", category="fish", size_class=shark_class
    )
    return run(fight, [bus, shark], runs=200).deciding_factor_explainer or ""


def test_an_unsized_bus_is_the_1_kg_placeholder_the_bug_bash_found() -> None:
    bus = estimate_sheet("school bus", "object_or_machine")
    assert bus.stats[StatName.MASS].value == pytest.approx(1.0)


def test_a_huge_school_bus_weighs_thousands_of_kg_and_is_metres_long() -> None:
    bus = estimate_sheet("school bus", "object_or_machine", size_class="huge")
    mass, size = bus.stats[StatName.MASS], bus.stats[StatName.SIZE]
    assert mass.value == pytest.approx(SIZE_MASSES["huge"])  # 5,000 kg, from the code table
    assert size.value > 3.0
    assert all(value.is_estimate for value in bus.stats.values())
    assert "Sized as a huge fighter" in (mass.note or "")
    assert bus.body == Body.INERT  # still an object: no attack, no movement (D-38)


@pytest.mark.parametrize(("size_class", "kg"), [("small", 1.0), ("large", 500.0)])
def test_each_size_class_comes_from_the_fixed_table(size_class: str, kg: float) -> None:
    # A small object (a toaster) already fits its band at the 1 kg default, so it stays 1 kg.
    sheet = estimate_sheet("thing", "object_or_machine", size_class=size_class)
    assert sheet.stats[StatName.MASS].value == pytest.approx(kg)


def test_the_lookup_keeps_only_a_size_word_for_an_object_never_a_number() -> None:
    assert lore.outcome_for_not_found("object_or_machine", None, "HUGE").size_class == "huge"
    assert lore.outcome_for_not_found("object_or_machine", None, 11000).size_class is None
    assert lore.outcome_for_not_found("object_or_machine", None, "bus-sized").size_class is None
    assert lore.outcome_for_not_found("object_or_machine", "mammal", "huge").category is None


def test_an_object_of_unknown_size_says_it_is_a_stand_in() -> None:
    bus = estimate_sheet("school bus", "object_or_machine")
    for stat in (StatName.MASS, StatName.SIZE):
        note = bus.stats[stat].note or ""
        assert note.startswith("Estimate: ") and STAND_IN_NOTE in note


def test_a_sized_object_or_a_living_fighter_is_never_called_a_stand_in() -> None:
    sheets = [
        estimate_sheet("school bus", "object_or_machine", size_class="huge"),
        estimate_sheet("toaster", "object_or_machine", size_class="small"),
        estimate_sheet("moose", "real_animal"),
    ]
    for sheet in sheets:
        assert not any(STAND_IN_NOTE in (v.note or "") for v in sheet.stats.values())


@pytest.mark.parametrize("shark_class", ["large", "huge"])
def test_a_sized_bus_never_decides_a_fight_as_1_kg(shark_class: str) -> None:
    assert "1 kg" not in bus_vs_shark("huge", shark_class)


async def test_a_school_bus_from_the_live_lookup_is_sized(monkeypatch) -> None:
    from tests.unit.test_legend_cache import ScriptedChat
    from tests.unit.test_mythical_battles import go_live

    reply = {"found": False, "reason": "object_or_machine", "size_class": "huge"}
    go_live(monkeypatch, ScriptedChat(reply))
    sheet, estimated = await stages.lookup_fighter_or_estimate(
        FighterRequest(entity="school bus", raw="a school bus")
    )
    assert estimated and sheet.body == Body.INERT
    assert sheet.stats[StatName.MASS].value == pytest.approx(SIZE_MASSES["huge"])
