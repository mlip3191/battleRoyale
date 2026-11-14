"""The number rule in code: a model's number counts only if the evidence really contains it."""

import re

NUMBER = re.compile(r"(?<![\d.,])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
DASHES = re.compile(r"[‐-―−]")
MATCH_TOLERANCE = 1e-9


# Make text comparable: plain hyphens and single spaces, so line wrapping can't cause a mismatch.
def normalize_text(text: str) -> str:
    return " ".join(DASHES.sub("-", text.replace("\xa0", " ")).split())


# True when the quote appears word for word in the passage, starting and ending on whole words
# and whole numbers, so "5 kg" can't be cut from "15 kg" or "0.5 kg", nor "5 s" from "5 seconds".
def quote_in_passage(quote: str, passage: str) -> bool:
    cleaned = normalize_text(quote)
    if not cleaned:
        return False
    # A "-" may come before the quote, on purpose: it keeps "5 kg" matching inside "4-5 kg".
    # So "5" also matches inside "-5"; that's harmless while negatives fail the sanity bounds.
    pattern = r"(?<![\w.,])" + re.escape(cleaned) + r"(?!\w|[.,]\d)"
    return re.search(pattern, normalize_text(passage)) is not None


# Every number written in digits in the text.
def numbers_in(text: str) -> list[float]:
    return [float(found.replace(",", "")) for found in NUMBER.findall(normalize_text(text))]


# True when the number, in the unit the source used, appears in the quote.
def number_in_quote(value_as_written: float, quote: str) -> bool:
    return any(
        abs(number - value_as_written) <= MATCH_TOLERANCE * max(abs(number), 1.0)
        for number in numbers_in(quote)
    )


# Accept an extracted value only if its number is in the quote and the quote is in the passage.
def evidence_is_valid(value_as_written: float, quote: str, passage: str) -> bool:
    return number_in_quote(value_as_written, quote) and quote_in_passage(quote, passage)


# What may sit between a number and its unit: an optional range end ("4-5 kg", "4 to 5 kg").
RANGE_TAIL = r"(?:\s*(?:-|to)\s*\d[\d,]*(?:\.\d+)?)?\s*"
# Units this short are symbols ("m", "mm", "Mm", "kg", "N"), where case changes the meaning.
SHORT_UNIT_CHARS = 3
# Unit symbols that are also English words.
UNITS_THAT_ARE_WORDS = frozenset({"in"})


# True when the number is written in the quote with this unit right after it (or after the
# range it starts), so "8.8 kg" can't be taken from "4-5 kg (8.8-11.0 lb)".
def number_has_unit_in_quote(value_as_written: float, unit: str, quote: str) -> bool:
    text = normalize_text(quote)
    unit_text = normalize_text(unit)
    if not unit_text:
        return False
    # A unit may not run on into another ("5 m/s" is not metres, "5 in the wild" not inches).
    # Short symbols match case exactly, so "5 Mm" is never millimetres; words like "Newtons"
    # may differ in case.
    flags = re.IGNORECASE if len(unit_text) > SHORT_UNIT_CHARS else 0
    # "in" is also a word, so as inches it can't be followed by another word ("5 in the wild").
    word_after = r"(?!\s+[A-Za-z])" if unit_text.lower() in UNITS_THAT_ARE_WORDS else ""
    # One- and two-letter symbols take no plural, so "5 ms" is not metres nor "5 gs" grams.
    plural = "" if len(unit_text) <= 2 else r"(?:e?s)?"
    tail = re.compile(
        RANGE_TAIL + re.escape(unit_text) + plural + r"(?![A-Za-z/²³])" + word_after, flags
    )
    for found in NUMBER.finditer(text):
        number = float(found.group().replace(",", ""))
        close = abs(number - value_as_written) <= MATCH_TOLERANCE * max(abs(number), 1.0)
        if close and tail.match(text, found.end()):
            return True
    return False
