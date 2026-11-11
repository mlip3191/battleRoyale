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
