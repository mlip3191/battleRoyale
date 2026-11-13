"""The number guard catches invented numbers in any form and lets real ones through.

These tests use hand-built allowed sets, so the guard is tested on its own. The tests that use the
real fixture battle's allowed set live in test_narration_facts.py.
"""

import pytest

from app.narration.number_guard import (
    AllowedNumbers,
    extract_numbers,
    find_unsupported_numbers,
)

# The four canonical cases from the A06 acceptance criteria, against a narrow allowed set.
NARROW = AllowedNumbers(values=frozenset({1.0, 389.0}), percents=frozenset({55.0}))

# A bear-vs-wolves style set: stats, conversions, counts, run count, and win percentages.
BATTLE = AllowedNumbers(
    values=frozenset({389.0, 13.33, 13.3, 858.0, 48.0, 4.0, 6.0, 1000.0}),
    percents=frozenset({38.0, 55.0}),
)


@pytest.mark.parametrize(
    "text",
    [
        "The bear lands 7 punches!",  # invented digit
        "The bear lands 7,777 punches tonight!",  # invented digit with a separator
        "It packs 3.14 meters of reach.",  # invented decimal
        "Four hundred wolves could not stop it!",  # number word
        "That is four hundred and twelve reasons to worry.",  # compound number word
        "The wolves win 40% of the time.",  # percentage (digits)
        "The wolves win forty-three percent of the time.",  # percentage (words)
        "The wolves win 43 per cent of the time.",  # percentage ("per cent")
        "The bear is an eight to one favorite!",  # ratio (words)
        "The bear is a 9:1 favorite!",  # ratio (colon)
        "The bear is a 9-to-1 favorite!",  # ratio (hyphens)
        "Two to one, the bear is going down!",  # "two" is not exempt inside a ratio
        "Only two percent of fans saw that coming.",  # "two" is not exempt inside a percentage
        "A dozen wolves would do it.",  # dozen
        "Two dozen wolves would do it.",  # dozen with a count
        "That is the nineteenth bite!",  # ordinal
        "Twice the bear it used to be!",  # twice
        "Half the pack is tired.",  # half
    ],
)
def test_guard_catches_canonical_cases(text: str) -> None:
    assert find_unsupported_numbers(text, NARROW), text


@pytest.mark.parametrize(
    "text",
    [
        "Hundreds of fans are on their feet!",
        "Thousands of fans are on their feet!",
        "Millions watching at home!",
        "Tens of wolves pour in!",
        "A score of wolves pour in!",
        "A quarter of the pack is tired.",
        "Three quarters of the pack is tired.",
        "Hit him thrice!",
        "That is triple the speed!",
        "That is double the speed!",
    ],
)
def test_guard_catches_quantity_words(text: str) -> None:
    assert find_unsupported_numbers(text, NARROW), text


def test_quantity_words_pass_when_their_value_is_allowed() -> None:
    allowed = AllowedNumbers(values=frozenset({100.0, 20.0, 0.25, 2.0}))
    for text in ("Hundreds of fans!", "A score of wolves!", "A quarter of the pack.", "Double!"):
        assert find_unsupported_numbers(text, allowed) == [], text


@pytest.mark.parametrize(
    "text",
    [
        "The bear weighs two point five tonnes.",  # spoken decimal (words)
        "The bear weighs 2 point 5 tonnes.",  # spoken decimal (digits)
        "It covers 1/2 the ring.",  # fraction
        "It covers 3/4 of the ring.",  # fraction
        "It hits with 1e3 newtons.",  # exponent
        "It weighs 3,5 tonnes.",  # decimal comma
    ],
)
def test_guard_reads_decimals_fractions_and_exponents_as_one_value(text: str) -> None:
    # Every part (2, 5, 1, 3, 4) is allowed, so only the whole value can trip the guard.
    allowed = AllowedNumbers(values=frozenset({1.0, 2.0, 3.0, 4.0, 5.0}))
    assert find_unsupported_numbers(text, allowed), text


def test_narrow_set_still_passes_real_numbers() -> None:
    text = "One punch from 389 kilograms, and these two know it: 55% for the wolves."
    assert find_unsupported_numbers(text, NARROW) == []


@pytest.mark.parametrize(
    "text",
    [
        "The bear weighs in at 389 kilograms!",  # stat value
        "The bear weighs 389.0 kilograms.",  # stat value with a trailing decimal
        "The bear tops out at 13.3 meters per second.",  # rounded value
        "The bear tops out at thirteen point three meters per second.",  # spoken decimal
        "That's 858 pounds of bear!",  # converted unit
        "The wolves won 55% of the fights.",  # win percentage
        "The wolves won fifty-five percent of the fights.",  # win percentage in words
        "About 4 wolves make it a coin flip.",  # count
        "Across 1,000 simulated fights.",  # run count
        "Across 1e3 simulated fights.",  # run count as an exponent
        "The bear landed one punch.",  # ordinary "one"
        "These two do not like each other.",  # ordinary "two"
        "For the first time tonight, the second wolf steps up.",  # first/second not extracted
        "What is the score? It is round one.",  # "score" alone is not a number
        "Good evening and welcome to Battle Royale!",  # no numbers at all
    ],
)
def test_guard_passes_supported_numbers(text: str) -> None:
    assert find_unsupported_numbers(text, BATTLE) == [], text


@pytest.mark.parametrize(
    ("text", "value", "kind"),
    [
        ("about 1,200 of them", 1200.0, "number"),
        ("3.5 seconds", 3.5, "number"),
        ("3,5 seconds", 3.5, "number"),
        ("1,234,567.5 grams", 1234567.5, "number"),
        ("two point five", 2.5, "number"),
        ("forty-two point zero five", 42.05, "number"),
        ("2 point 5", 2.5, "number"),
        ("3/4", 0.75, "number"),
        ("1e3", 1000.0, "number"),
        ("four hundred and twelve", 412.0, "number"),
        ("forty-two", 42.0, "number"),
        ("two thousand four hundred", 2400.0, "number"),
        ("a dozen", 12.0, "number"),
        ("a hundred", 100.0, "number"),
        ("a score", 20.0, "number"),
        ("four score and seven", 87.0, "number"),
        ("three quarters", 0.75, "number"),
        ("hundreds of them", 100.0, "number"),
        ("thrice", 3.0, "number"),
        ("half the pack", 0.5, "number"),
        ("the 3rd round", 3.0, "number"),
        ("40%", 40.0, "percent"),
        ("eight to one", 8.0, "ratio"),
        ("8-to-1", 8.0, "ratio"),
        ("8:1", 8.0, "ratio"),
    ],
)
def test_extract_reads_each_form(text: str, value: float, kind: str) -> None:
    found = extract_numbers(text)
    assert len(found) == 1, found
    assert found[0].value == pytest.approx(value)
    assert found[0].kind == kind


def test_separate_number_words_stay_separate() -> None:
    assert [n.value for n in extract_numbers("one and two and three")] == [1.0, 2.0, 3.0]


def test_hyphen_only_joins_number_words() -> None:
    assert [n.value for n in extract_numbers("forty-two well-fed wolves")] == [42.0]


def test_spoken_decimal_is_never_ordinary() -> None:
    [found] = extract_numbers("one point five")
    assert not found.ordinary
    assert find_unsupported_numbers("one point five", NARROW)


def test_found_text_quotes_the_original_words() -> None:
    [found] = extract_numbers("An Eight-To-One favorite")
    assert found.text == "Eight-To-One"
    assert found.right == 1.0


def test_ratio_passes_when_it_matches_win_odds() -> None:
    odds_only = AllowedNumbers(odds=frozenset({1.5}))
    assert find_unsupported_numbers("They are three to two favorites.", odds_only) == []
    assert find_unsupported_numbers("They are nine to one favorites.", odds_only)


def test_ratio_passes_when_both_sides_are_allowed() -> None:
    allowed = AllowedNumbers(values=frozenset({8.0, 1.0}))
    assert find_unsupported_numbers("an 8-to-1 favorite", allowed) == []


# Every part of the QA cases is allowed on its own, so only the combined value can trip the guard.
QA_SET = AllowedNumbers(
    values=frozenset({1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 12.0, 100.0, 389.0, 1000.0})
)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("4 thousand wolves", 4000.0),
        ("7 dozen wolves", 84.0),
        ("3.9 hundred wolves", 390.0),
        ("3 hundred wolves", 300.0),
        ("2 score wolves", 40.0),
    ],
)
def test_digit_and_scale_word_are_one_number(text: str, value: float) -> None:
    # Each digit and scale is allowed on its own; 389 is left out because 390 rounds to it.
    parts = AllowedNumbers(values=frozenset({2.0, 3.0, 3.9, 4.0, 7.0, 12.0, 20.0, 100.0, 1000.0}))
    [found] = extract_numbers(text)
    assert found.value == pytest.approx(value)
    assert find_unsupported_numbers(text, parts), text


def test_digit_and_scale_word_pass_when_combined_value_is_allowed() -> None:
    allowed = AllowedNumbers(values=frozenset({4000.0, 84.0}))
    assert find_unsupported_numbers("4 thousand wolves and 7 dozen bees", allowed) == []


def test_spelled_scale_still_caught() -> None:
    assert find_unsupported_numbers("four thousand wolves", QA_SET)


@pytest.mark.parametrize("text", ["50/50 odds", "5/0 odds"])
def test_fraction_needs_both_sides_and_value(text: str) -> None:
    # "50/50" divides to the allowed 1, and "5/0" has no value at all; both must be flagged.
    assert find_unsupported_numbers(text, QA_SET), text


def test_zero_bottom_fraction_is_flagged_even_when_sides_are_allowed() -> None:
    allowed = AllowedNumbers(values=frozenset({0.0, 5.0}))
    assert find_unsupported_numbers("5/0 odds", allowed)


def test_fraction_passes_when_value_and_sides_are_allowed() -> None:
    allowed = AllowedNumbers(values=frozenset({1.0, 2.0, 0.5}))
    assert find_unsupported_numbers("It covers 1/2 the ring.", allowed) == []


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("3½ tall", 3.5),
        ("½ the ring", 0.5),
        ("⅔ of the pack", 2 / 3),
        ("a tenfold increase", 10.0),
        ("a hundredfold increase", 100.0),
        ("a thousandfold increase", 1000.0),
        ("two-thirds of the pack", 2 / 3),
        ("one-third of the pack", 1 / 3),
        ("two thirds of the pack", 2 / 3),
        ("one third of the pack", 1 / 3),
        ("a trillion bees", 1e12),
        ("trillions of bees", 1e12),
        ("4 trillion bees", 4e12),
    ],
)
def test_unicode_fractions_and_leftover_words_are_read(text: str, value: float) -> None:
    # 1, 2, 3, and 4 are allowed on their own, and "two" always passes, so only the
    # combined value (3.5, 2/3, 4 trillion) can trip the guard.
    parts = AllowedNumbers(values=frozenset({1.0, 2.0, 3.0, 4.0}))
    [found] = extract_numbers(text)
    assert found.value == pytest.approx(value)
    assert find_unsupported_numbers(text, parts), text


def test_unicode_fractions_and_leftover_words_pass_when_allowed() -> None:
    allowed = AllowedNumbers(
        values=frozenset({3.5, 0.5, 2 / 3, 1 / 3, 10.0, 100.0, 1000.0, 1e12, 4e12})
    )
    for text in (
        "3½ tall",
        "½ the ring",
        "two-thirds of the pack",
        "one-third of the pack",
        "a tenfold increase",
        "a hundredfold increase",
        "a thousandfold increase",
        "a trillion bees",
        "4 trillion bees",
    ):
        assert find_unsupported_numbers(text, allowed) == [], text


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("a twofold increase", 2.0),
        ("a threefold increase", 3.0),
        ("a fivefold increase", 5.0),
        ("a twentyfold increase", 20.0),
        ("a twelvefold increase", 12.0),
        ("a millionfold increase", 1e6),
    ],
)
def test_any_number_word_fold_is_read(text: str, value: float) -> None:
    # "twofold" is a multiplier, not the free-pass "two", so it must match an allowed value.
    [found] = extract_numbers(text)
    assert found.value == pytest.approx(value)
    assert not found.ordinary
    assert find_unsupported_numbers(text, NARROW), text
    assert find_unsupported_numbers(text, AllowedNumbers(values=frozenset({value}))) == [], text


def test_fold_needs_a_number_word_stem() -> None:
    assert extract_numbers("the manifold scaffold") == []


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("two-fifths of the pack", 2 / 5),
        ("one-fifth of the pack", 1 / 5),
        ("three-fifths of the pack", 3 / 5),
        ("one half of the pack", 1 / 2),
        ("three fourths of the pack", 3 / 4),
        ("five-sixths of the pack", 5 / 6),
        ("seven eighths of the pack", 7 / 8),
        ("nine-tenths of the pack", 9 / 10),
    ],
)
def test_unit_fractions_beyond_thirds_are_read(text: str, value: float) -> None:
    # The top and bottom are allowed on their own and "one"/"two" always pass, so only the
    # fraction's value can trip the guard.
    parts = AllowedNumbers(values=frozenset({1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0}))
    [found] = extract_numbers(text)
    assert found.value == pytest.approx(value)
    assert not found.ordinary
    assert find_unsupported_numbers(text, parts), text
    assert find_unsupported_numbers(text, AllowedNumbers(values=frozenset({value}))) == [], text


# Issue #249: Roman numerals, ordinals past "twentieth", more quantity words, "one hundredth",
# and circled digits are numbers too. Each is flagged when nothing is allowed and passes when
# its own value is allowed.
@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("It's round XIV and he looks fresh", 14.0),  # Roman numeral
        ("Round II goes to the bear.", 2.0),  # Roman numeral, no "two" pass
        ("Round IV goes to the bear.", 4.0),  # Roman numeral
        ("Welcome to Battle Royale MMXXVI!", 2026.0),  # Roman numeral
        ("That is the twenty-first swing!", 21.0),  # compound ordinal
        ("That is the thirty-third swing!", 33.0),  # compound ordinal
        ("That is the forty-fifth swing!", 45.0),  # compound ordinal
        ("That is the thirty third swing!", 33.0),  # compound ordinal with a space
        ("That is the ninety-ninth swing!", 99.0),  # compound ordinal
        ("That is the twenty-second swing!", 22.0),  # compound ordinal ending in "second"
        ("That is the thirtieth swing!", 30.0),  # tens ordinal
        ("That is the fortieth swing!", 40.0),  # tens ordinal
        ("That is the hundredth swing!", 100.0),  # hundredth
        ("A couple of punches land.", 2.0),  # couple, no "two" pass
        ("A pair of claws swing.", 2.0),  # pair, no "two" pass
        ("A trio of punches land.", 3.0),  # trio
        ("A century of evolution!", 100.0),  # century
        ("A decade of training!", 10.0),  # decade
        ("A gross of bees pour in!", 144.0),  # gross
        ("A myriad of bees pour in!", 10000.0),  # myriad
        ("That is quadruple the speed!", 4.0),  # quadruple
        ("It lasts one hundredth of a second.", 0.01),  # fraction
        ("Bout ① goes to the bear.", 1.0),  # circled 1
        ("Bout ③ goes to the bear.", 3.0),  # circled 3
        ("Bout ⑳ goes to the bear.", 20.0),  # circled 20
        ("Bout ⓪ goes to the bear.", 0.0),  # circled 0
    ],
)
def test_roman_late_ordinal_quantity_and_circled_forms_are_read(text: str, value: float) -> None:
    [found] = extract_numbers(text)
    assert found.value == pytest.approx(value)
    assert not found.ordinary
    assert find_unsupported_numbers(text, AllowedNumbers()), text
    assert find_unsupported_numbers(text, AllowedNumbers(values=frozenset({value}))) == [], text


@pytest.mark.parametrize(
    "text",
    [
        "I MIX it up, DID you see that CIVIL display?",  # caps words that only look Roman
        "I think I can.",  # the pronoun "I"
        "Round xiv in lower case is just letters.",  # Roman numerals must be all caps
        "One punch, and these two know it.",  # ordinary "one" and "two"
        "That is gross!",  # "gross" without a count is not 144
        "The pair circle each other.",  # "pair" without a count is not read
    ],
)
def test_words_that_look_like_new_forms_are_not_numbers(text: str) -> None:
    assert find_unsupported_numbers(text, AllowedNumbers()) == [], text


def test_roman_numeral_reads_original_casing() -> None:
    assert extract_numbers("I MIX DID CIVIL") == []
    assert [n.value for n in extract_numbers("XIV and xiv")] == [14.0]
