"""#500: when intake keeps a different fighter than the words typed, a code note says so."""

from typing import Any

import pytest

from app.intake.parser import MAX_NOTE_CHARS, misread_notes, parse_matchup, read_matchup
from app.intake.schema import ParsedMatchup
from app.models.matchup import FighterRequest, IntakeResult

KIMONO_NOTE = "We read 'kimono dragon' as dragon. Not what you meant? Edit it and fight again."


# Read a two-sided model reply; each side is (raw, entity) or (raw, entity, variant).
def read(text: str, *sides: tuple[str, ...]) -> IntakeResult:
    fighters: list[dict[str, Any]] = [
        {"raw": s[0], "entity": s[1], "variant": s[2] if len(s) > 2 else None} for s in sides
    ]
    return read_matchup(text, ParsedMatchup.model_validate({"fighters": fighters}))


# The misread notes on an ok result's card.
def misreads(result: IntakeResult) -> list[str]:
    assert result.matchup is not None
    return [n for n in result.matchup.assumptions if n.startswith("We read ")]


def test_a_dropped_word_gets_the_note() -> None:
    result = read(
        "Kimono dragon vs Anaconda", ("Kimono dragon", "dragon"), ("Anaconda", "anaconda")
    )
    assert misreads(result) == [KIMONO_NOTE.replace("kimono", "Kimono")]


def test_the_note_uses_the_users_own_words() -> None:
    result = read(
        "kimono dragon vs anaconda", ("kimono dragon", "dragon"), ("anaconda", "anaconda")
    )
    assert misreads(result) == [KIMONO_NOTE]


@pytest.mark.parametrize("raw", ["US navy seals", "25 US navy seals"])
def test_navy_seals_read_as_the_animal_get_the_note(raw: str) -> None:
    result = read(
        f"{raw} vs 100 spartan warriors", (raw, "seal"), ("100 spartan warriors", "spartan warrior")
    )
    assert misreads(result) == [
        f"We read '{raw}' as seal. Not what you meant? Edit it and fight again."
    ]


@pytest.mark.parametrize(
    ("raw", "entity", "variant"),
    [
        ("a grizzly bear", "grizzly bear", None),
        ("a grizzly bear", "bear", None),  # build_fighter restores "grizzly" as the variant
        ("a grizzly bear", "bear", "grizzly"),
        ("6 gray wolves", "wolf", None),
        ("komodo dragon", "komodo dragon", None),
        ("100 duck-sized horses", "horse", None),
        ("a main-battle tank", "main battle tank", None),
        ("a bear", "bear", None),  # a default-kind pick has its own note, not this one
    ],
)
def test_no_note_when_the_typed_name_was_kept(raw: str, entity: str, variant: str | None) -> None:
    result = read(f"{raw} vs a goose", (raw, entity, variant), ("a goose", "goose"))
    assert misreads(result) == []


def test_each_misread_side_gets_its_own_note() -> None:
    result = read(
        "kimono dragon vs US navy seals", ("kimono dragon", "dragon"), ("US navy seals", "seal")
    )
    assert misreads(result) == [
        KIMONO_NOTE,
        "We read 'US navy seals' as seal. Not what you meant? Edit it and fight again.",
    ]


def test_a_long_raw_is_cut_but_the_guidance_stays() -> None:
    raw = "kimono " * 60 + "dragon"
    [note] = misread_notes([FighterRequest(entity="dragon", raw=raw)])
    assert len(note) <= MAX_NOTE_CHARS
    assert note.endswith("' as dragon. Not what you meant? Edit it and fight again.")


def test_nothing_to_compare_is_skipped() -> None:
    assert misread_notes([FighterRequest(entity="dragon", raw="a")]) == []


async def test_a_blocked_request_still_blocks() -> None:
    result = await parse_matchup("a toddler vs a kimono dragon")
    assert result.status == "blocked" and result.matchup is None
