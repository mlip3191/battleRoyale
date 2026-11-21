"""Counts of 3+ digits are spoken in words; everything else is left as written (#502)."""

import pytest

from app.media.spoken_numbers import number_words, speech_text


@pytest.mark.parametrize(
    ("line", "spoken"),
    [
        ("A tiger vs 128 geese!", "A tiger vs one hundred twenty-eight geese!"),
        ("1000 ants", "one thousand ants"),
        ("1,000 ants", "one thousand ants"),
        ("10000 bees", "ten thousand bees"),
        ("Up to 450 pounds.", "Up to four hundred fifty pounds."),
        ("It wins 100% of fights", "It wins one hundred percent of fights"),
        ("2,500,000 krill", "two million five hundred thousand krill"),
        ("101 and 110 and 999", "one hundred one and one hundred ten and nine hundred ninety-nine"),
    ],
)
def test_counts_of_three_or_more_digits_are_spoken_in_words(line: str, spoken: str) -> None:
    assert speech_text(line) == spoken


@pytest.mark.parametrize(
    "line",
    ["7 wolves", "42 geese", "2.5 tonnes", "128.5 kg", "0.125 seconds", "3:1 odds", "1/128", "007"],
)
def test_small_numbers_decimals_and_ratios_are_left_alone(line: str) -> None:
    assert speech_text(line) == line


def test_the_full_count_is_spoken_never_just_the_last_digits() -> None:
    spoken = speech_text("128 geese")
    assert "one hundred twenty-eight" in spoken
    assert "128" not in spoken and not spoken.startswith("twenty-eight")


def test_number_words_reads_round_and_mixed_numbers() -> None:
    assert number_words(100) == "one hundred"
    assert number_words(1001) == "one thousand one"
    assert number_words(20_017) == "twenty thousand seventeen"
