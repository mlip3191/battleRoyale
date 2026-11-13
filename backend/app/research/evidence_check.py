"""The number rule in code: a model's number counts only if the evidence really contains it."""

import re

NUMBER = re.compile(r"(?<![\d.,])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
DASHES = re.compile(r"[‐-―−]")
MATCH_TOLERANCE = 1e-9


# Make text comparable: plain hyphens and single spaces, so line wrapping can't cause a mismatch.
def normalize_text(text: str) -> str:
    return " ".join(DASHES.sub("-", text.replace("\xa0", " ")).split())


# True when the quote appears word for word in the passage.
def quote_in_passage(quote: str, passage: str) -> bool:
    cleaned = normalize_text(quote)
    return bool(cleaned) and cleaned in normalize_text(passage)


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


# True when the number is written in the quote with this unit right after it (or after the
# range it starts), so "8.8 kg" can't be taken from "4-5 kg (8.8-11.0 lb)".
def number_has_unit_in_quote(value_as_written: float, unit: str, quote: str) -> bool:
    text = normalize_text(quote)
    unit_text = normalize_text(unit)
    if not unit_text:
        return False
    tail = re.compile(RANGE_TAIL + re.escape(unit_text) + r"(?:e?s)?(?![A-Za-z])", re.IGNORECASE)
    for found in NUMBER.finditer(text):
        number = float(found.group().replace(",", ""))
        close = abs(number - value_as_written) <= MATCH_TOLERANCE * max(abs(number), 1.0)
        if close and tail.match(text, found.end()):
            return True
    return False
