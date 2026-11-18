"""#415: common names reach their seed fighters; a named variant is not swapped for a default."""

import pytest

from app.intake.parser import default_kind_notes, read_matchup
from app.intake.schema import ParsedMatchup
from app.models.matchup import FighterRequest
from app.research.seed_fighters import (
    default_kind,
    find_seed_fighter,
    find_seed_sheet,
    named_kind_words,
    picked_default,
)


def request(entity: str, raw: str) -> FighterRequest:
    return FighterRequest(entity=entity, raw=raw)


@pytest.mark.parametrize(
    ("entity", "expected"),
    [
        ("hippo", "hippopotamus"),
        ("hippos", "hippopotamus"),
        ("Hippopotamus", "hippopotamus"),
        ("cobra", "king-cobra"),
        ("cobras", "king-cobra"),
        ("king cobra", "king-cobra"),  # the full name still works
        ("t-rex", "tyrannosaurus-rex"),
        ("t rex", "tyrannosaurus-rex"),
        ("T. Rex", "tyrannosaurus-rex"),
        ("trex", "tyrannosaurus-rex"),
        ("tyrannosaurus", "tyrannosaurus-rex"),
        ("Tyrannosaurus rex", "tyrannosaurus-rex"),
    ],
)
def test_common_names_reach_their_seed_fighters(entity: str, expected: str) -> None:
    found = find_seed_fighter(entity, None, f"a {entity}")
    assert found is not None and found.id == expected


def test_a_common_name_finds_the_hand_verified_sheet_when_there_is_one() -> None:
    for name in ("cobra", "king cobra"):
        sheet = find_seed_sheet(name, None, f"a {name}")
        assert sheet is not None and sheet.fighter_id == "king-cobra"


def test_a_cobra_is_not_a_bare_kind_so_it_gets_no_default_note() -> None:
    assert default_kind_notes([request("cobra", "a cobra")]) == []


@pytest.mark.parametrize(
    "raw", ["a polar bear", "the polar bear", "2 polar bears", "a kodiak bear"]
)
def test_a_named_kind_in_the_raw_text_is_not_swapped_for_the_default(raw: str) -> None:
    assert default_kind("bear", None, raw) is None
    assert picked_default("bear", None, raw) is None
    assert find_seed_fighter("bear", None, raw) is None
    assert find_seed_sheet("bear", None, raw) is None
    assert default_kind_notes([request("bear", raw)]) == []  # no "Not sure which bear"


@pytest.mark.parametrize(
    "raw",
    [
        "a bear",
        "the bear",
        "6 bears",
        "three bears",
        "a big bear",
        "some small bears",
        "a fierce bear",
        "an adult bear",
        "my bear",
    ],
)
def test_a_bare_kind_with_only_articles_numbers_or_size_words_still_gets_the_default(
    raw: str,
) -> None:
    assert default_kind("bear", None, raw) == "grizzly-bear"
    assert default_kind_notes([request("bear", raw)]) == [
        "Not sure which bear, so we used the grizzly bear."
    ]


def test_a_phrase_that_does_not_mention_the_entity_changes_nothing() -> None:
    assert default_kind("wolves", None, "../fighters") == "gray-wolf"  # path-like raw, still safe
    assert default_kind("bear", None, "something else entirely") == "grizzly-bear"


def test_the_raw_text_rule_keeps_the_earlier_cases_working() -> None:
    assert default_kind("wolves") == "gray-wolf"  # no raw text given
    assert picked_default("wolf", None, "6 gray wolves") is None  # already named
    found = find_seed_fighter("wolf", None, "6 gray wolves")
    assert found is not None and found.id == "gray-wolf"


@pytest.mark.parametrize(
    ("entity", "raw", "expected"),
    [
        ("bear", "a polar bear", "polar"),
        ("bear", "2 polar bears", "polar"),
        ("bear", "a Kodiak bear", "kodiak"),
        ("bear", "a bear", None),
        ("bear", "6 bears", None),
        ("bear", "a fierce bear", None),
        ("bear", "../fighters", None),
    ],
)
def test_the_named_kind_around_a_bare_entity_is_kept_in_the_users_words(
    entity: str, raw: str, expected: str | None
) -> None:
    assert named_kind_words(entity, raw) == expected


def test_intake_keeps_the_polar_in_a_polar_bear_so_the_fighter_reads_polar_bear() -> None:
    parsed = ParsedMatchup.model_validate(
        {
            "fighters": [
                {"entity": "bear", "raw": "a polar bear"},
                {"entity": "gray wolf", "raw": "a gray wolf"},
            ]
        }
    )
    result = read_matchup("a polar bear vs a gray wolf", parsed)
    assert result.matchup is not None
    bear = result.matchup.fighters[0]
    assert (bear.entity, bear.variant) == ("bear", "polar")
    assert not any("Not sure which bear" in n for n in result.matchup.assumptions)


def test_intake_leaves_a_plain_bear_and_a_given_variant_alone() -> None:
    parsed = ParsedMatchup.model_validate(
        {
            "fighters": [
                {"entity": "bear", "raw": "a bear"},
                {"entity": "bear", "variant": "grizzly", "raw": "a grizzly bear"},
            ]
        }
    )
    result = read_matchup("a bear vs a grizzly bear", parsed)
    assert result.matchup is not None
    plain, given = result.matchup.fighters
    assert plain.variant is None and given.variant == "grizzly"
