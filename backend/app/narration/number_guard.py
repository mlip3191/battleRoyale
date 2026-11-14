"""The number guard: find every number in a script line that the inputs do not support.

It reads digits ("1,200", "3,5", "1/2", "½", "3½", "1e3", "2 point 5", "3rd"),
number words ("four hundred and twelve", "forty-two", "two point five", "a dozen", "a score",
"three quarters", "two-thirds", "three-fifths", "one hundredth", "a trillion"), quantity words
("half", "twice", "thrice", "double", "triple", "quadruple", "trio", "tens", "dozens", "hundreds",
"thousands", "millions", "trillions", and any number word plus "fold": "twofold", "twentyfold",
"thousandfold"; after "a" or a number: "a couple", "a pair", "a decade", "a century", "a gross",
"a myriad"), ordinals ("third" to "hundredth", including "twenty-first" and "thirty third"),
all-caps Roman numerals of two or more letters ("XIV", "MMXXVI"; not "I", "MIX", or "CIVIL"),
circled digits ("①" to "⑳", "⓪", and similar enclosed digits), percentages ("40%",
"forty per cent"), and ratios ("8:1", "eight to one", "8-to-1"). ARCHITECTURE "The number rule": a
plain number must match an allowed value (within rounding), a percentage an allowed percentage, and
a ratio either two allowed values or a win-odds ratio. "one", "two", "first", "second", "1st",
"2nd" on their own are always allowed, so "one punch" or "these two" never trips it; digits ("2"),
percentages, ratios, decimals ("one point five"), "twice", "a couple", and "a pair" get no such
pass. Known limit: "a third" reads as the ordinal 3.
Pure standard-library code, no I/O, safe to call on every line.
"""

import math
import re
from dataclasses import dataclass
from typing import Literal

# Tolerance for rounding: a number matches an allowed one within 0.01 or 0.5%, whichever is larger.
ABS_TOL = 0.01
REL_TOL = 0.005
# A ratio matches a win-odds ratio within 5% (odds are always said loosely).
ODDS_REL_TOL = 0.05


# Number words in order, mapped to their values: first, first + step, ...
def _numbered(words: str, first: int, step: int = 1) -> dict[str, int]:
    return {w: first + step * i for i, w in enumerate(words.split())}


_UNITS = _numbered("zero one two three four five six seven eight nine", 0)
_TEENS = _numbered(
    "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen", 10
)
_TENS = _numbered("twenty thirty forty fifty sixty seventy eighty ninety", 20, 10)
_ORDINALS = _numbered(
    "third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth "
    "fifteenth sixteenth seventeenth eighteenth nineteenth twentieth", 3
) | _numbered("thirtieth fortieth fiftieth sixtieth seventieth eightieth ninetieth", 30, 10) | {
    "hundredth": 100
}  # fmt: skip
# Ordinals that finish a compound ordinal after a tens word: "twenty-first" through "ninety-ninth".
_UNIT_ORDINALS = {"first": 1, "second": 2} | {w: v for w, v in _ORDINALS.items() if v <= 9}
_SCALES = {
    "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12, "dozen": 12.0,
    "score": 20.0, "quarter": 0.25, "quarters": 0.25, "couple": 2.0, "pair": 2.0, "decade": 10.0,
    "century": 100.0, "gross": 144.0, "myriad": 1e4,
}  # fmt: skip
# Scale words that only count after "a" or a number ("a score", "three quarters", not "the score",
# "that is gross", or "myriad fans").
_COUNTED = {
    "score",
    "quarter",
    "quarters",
    "couple",
    "pair",
    "decade",
    "century",
    "gross",
    "myriad",
}
_STANDALONE = {
    "half": 0.5, "twice": 2.0, "double": 2.0, "thrice": 3.0, "triple": 3.0, "trio": 3.0,
    "quadruple": 4.0, "tens": 10.0,
    "dozens": 12.0, "hundreds": 100.0, "thousands": 1e3, "millions": 1e6, "billions": 1e9,
    "trillions": 1e12,
}  # fmt: skip
# Scale words that multiply a digit right before them: "4 thousand" is 4,000, "7 dozen" is 84.
_DIGIT_SCALES = {
    "hundred": 100.0, "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12,
    "dozen": 12.0, "score": 20.0,
}  # fmt: skip

# Unicode vulgar fractions, alone ("½") or after a whole number ("3½").
_VULGAR = {
    "½": 1 / 2, "⅓": 1 / 3, "⅔": 2 / 3, "¼": 1 / 4, "¾": 3 / 4,
    "⅕": 1 / 5, "⅖": 2 / 5, "⅗": 3 / 5, "⅘": 4 / 5,
    "⅙": 1 / 6, "⅚": 5 / 6, "⅐": 1 / 7,
    "⅛": 1 / 8, "⅜": 3 / 8, "⅝": 5 / 8, "⅞": 7 / 8,
    "⅑": 1 / 9, "⅒": 1 / 10,
}  # fmt: skip

# Fraction words and their bottoms, singular and plural: "half"/"halves" through "tenth"/"tenths",
# and "hundredth"/"hundredths".
_FRACTION_WORDS = {
    word + plural: bottom
    for word, bottom in _ORDINALS.items()
    if bottom <= 10 or bottom == 100
    for plural in ("", "s")
} | {"half": 2, "halves": 2, "quarter": 4, "quarters": 4}
# "one" and "two" alone always pass, so "two-fifths" must be read as one number (2/5):
# "one" to "nine" over any fraction word.
_UNIT_FRACTIONS = {
    f"{top} {word}": _UNITS[top] / bottom
    for top in _UNITS
    if top != "zero"
    for word, bottom in _FRACTION_WORDS.items()
}


# Enclosed digits as (first code point, how many, value of the first): circled 1-20 and 0,
# parenthesized 1-20, negative circled 11-20, double circled 1-10, negative circled 0, dingbat
# circled 1-10 (three styles), and circled 21-35 and 36-50.
_ENCLOSED_RANGES = [
    (0x2460, 20, 1), (0x24EA, 1, 0), (0x2474, 20, 1), (0x24EB, 10, 11), (0x24F5, 10, 1),
    (0x24FF, 1, 0), (0x2776, 10, 1), (0x2780, 10, 1), (0x278A, 10, 1), (0x3251, 15, 21),
    (0x32B1, 15, 36),
]  # fmt: skip
_ENCLOSED = {chr(cp + i): float(first + i) for cp, n, first in _ENCLOSED_RANGES for i in range(n)}

# A canonical Roman numeral (1 to 3999), strictly written: "XIV" but not "IIII" or "DID".
_ROMAN = re.compile(r"M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
# All-caps words and abbreviations that happen to be canonical Roman numerals ("MIX", "CD", "MC").
_ROMAN_WORDS = {"MIX", "DIX", "MC", "MD", "CD", "DC", "CV", "MM", "CC", "MI", "DI", "LI", "MMM"}


# The value of an all-caps Roman numeral of two or more letters ("XIV" -> 14), else None.
def _roman_value(raw: str) -> float | None:
    if len(raw) < 2 or raw in _ROMAN_WORDS or not _ROMAN.fullmatch(raw):
        return None
    vals = [_ROMAN_VALUES[c] for c in raw]
    return float(sum(-v if v < nxt else v for v, nxt in zip(vals, [*vals[1:], 0], strict=True)))


_TOKEN = re.compile(
    r"(?P<num>\d+(?:\.\d+)?e[+-]?\d+"  # exponent: 1e3, 2.5e-2
    r"|\d+/\d+"  # fraction: 1/2
    r"|\d+ point \d+"  # spoken decimal: 2 point 5
    r"|\d{1,3}(?:,\d{3})+(?!\d)(?:\.\d+)?"  # thousands separators: 1,200
    r"|\d*(?:[" + "".join(_VULGAR) + r"])"  # Unicode vulgar: ½, 3½
    r"|\d+(?:[.,]\d+)?)"  # plain or decimal (point or comma): 3.5, 3,5
    r"(?P<ord>st|nd|rd|th)?|(?P<word>[a-z]+)|(?P<sym>[^\sa-z\d])"
)

Kind = Literal["number", "percent", "ratio"]


@dataclass(frozen=True)
class AllowedNumbers:
    """The numbers a script may say: plain values, percentages, and win-odds ratios."""

    values: frozenset[float] = frozenset()
    percents: frozenset[float] = frozenset()
    odds: frozenset[float] = frozenset()


@dataclass(frozen=True)
class FoundNumber:
    """One number found in text, with the exact words it came from."""

    text: str
    value: float
    kind: Kind = "number"
    right: float | None = None
    """Second side of a ratio."""
    ordinary: bool = False
    """True for the always-allowed "one", "two", "first", "second" phrasing."""
    parts: tuple[float, float] | None = None
    """Top and bottom of a digit fraction ("3/4"); value is then their quotient."""


@dataclass
class _Tok:
    """A token ("num", "ord", "word", "sym"), or after grouping a whole number ("number")."""

    kind: str
    text: str
    start: int
    end: int
    value: float = 0.0
    ordinary: bool = False
    parts: tuple[float, float] | None = None


# A whole number spanning start..end of the text.
def _num(
    value: float,
    start: int,
    end: int,
    ordinary: bool = False,
    parts: tuple[float, float] | None = None,
) -> _Tok:
    return _Tok("number", "", start, end, value, ordinary, parts)


# The two sides of a digit fraction ("3/4" -> (3, 4)), or None for any other digit token.
def _fraction_parts(s: str) -> tuple[float, float] | None:
    if "/" not in s:
        return None
    top, bottom = s.split("/")
    return float(top), float(bottom)


# The value of a digit token: fractions divide (a zero bottom has no value, so it is infinite),
# "point" and a lone comma are decimal points.
def _digits_value(s: str) -> float:
    if s and s[-1] in _VULGAR:
        whole = float(s[:-1]) if s[:-1] else 0.0
        return whole + _VULGAR[s[-1]]
    parts = _fraction_parts(s)
    if parts is not None:
        top, bottom = parts
        return top / bottom if bottom else math.inf
    s = re.sub(r",(?=\d{3}(?!\d))", "", s.replace(" point ", "."))
    return float(s.replace(",", "."))


# The value of a number word plus "fold" ("twofold", "twentyfold", "thousandfold"), else None.
def _fold_value(word: str) -> float | None:
    stem = word.removesuffix("fold")
    if stem == word:
        return None
    if stem == "hundred":
        return 100.0
    value = _UNITS.get(stem) or _TEENS.get(stem) or _TENS.get(stem)
    if value is None and stem in _SCALES and stem not in _COUNTED:
        value = _SCALES[stem]
    return None if value is None else float(value)


# Classify a number word for the grammar: unit, teen, tens, hundred, scale, or None.
def _word_class(word: str) -> str | None:
    for cls, table in (("unit", _UNITS), ("teen", _TEENS), ("tens", _TENS), ("scale", _SCALES)):
        if word in table:
            return cls
    return "hundred" if word == "hundred" else None


# Which word classes may follow which, so "one and two" is two numbers but "forty-two" is one.
_FOLLOWS = {
    "unit": {None, "a", "tens", "hundred", "scale"},
    "teen": {None, "a", "hundred", "scale"},
    "tens": {None, "hundred", "scale"},
    "hundred": {None, "a", "unit", "teen"},
    "scale": {None, "a", "unit", "teen", "tens", "hundred"},
}


# Split text into number, word, and symbol tokens (lowercased; offsets match the original text).
# Enclosed digits ("③") and all-caps Roman numerals ("XIV", checked in the original casing) become
# digit tokens.
def _tokenize(text: str) -> list[_Tok]:
    tokens = []
    for m in _TOKEN.finditer(text.lower()):
        roman = _roman_value(text[m.start() : m.end()]) if m.group("word") else None
        enclosed = _ENCLOSED.get(m.group("sym") or "")
        if m.group("num"):
            kind = "ord" if m.group("ord") else "num"
            value, parts = _digits_value(m["num"]), _fraction_parts(m["num"])
            tokens.append(_Tok(kind, m.group(0), m.start(), m.end(), value, parts=parts))
        elif roman is not None:
            tokens.append(_Tok("num", m.group(0), m.start(), m.end(), roman))
        elif enclosed is not None:
            tokens.append(_Tok("num", m.group(0), m.start(), m.end(), enclosed))
        else:
            kind = "word" if m.group("word") else "sym"
            tokens.append(_Tok(kind, m.group(kind), m.start(), m.end()))
    return tokens


# True when token j joins two number words: a hyphen ("forty-two") or "and" ("hundred and six").
def _joins(tokens: list[_Tok], j: int) -> bool:
    if j + 1 >= len(tokens) or _word_class(tokens[j + 1].text) is None:
        return False
    tok = tokens[j]
    return (tok.kind, tok.text) in (("sym", "-"), ("word", "and"))


# Read a run of number words starting at i; return the numbers found and the next token index.
def _read_words(tokens: list[_Tok], i: int) -> tuple[list[_Tok], int]:
    found: list[_Tok] = []
    total = current = 0.0
    last: str | None = None
    start = end = tokens[i].start
    said: list[str] = []

    def flush() -> None:
        nonlocal total, current, last, said
        if last is not None and last != "a":
            ordinary = len(said) == 1 and said[0] in ("one", "two")
            found.append(_num(total + current, start, end, ordinary))
        total, current, last, said = 0.0, 0.0, None, []

    j = i
    while j < len(tokens) and tokens[j].kind == "word":
        tok = tokens[j]
        if tok.text == "a" and last is None:
            if j + 1 >= len(tokens) or _word_class(tokens[j + 1].text) not in ("hundred", "scale"):
                break
            start, last, current = tok.start, "a", 1.0
            j += 1
            continue
        if tok.text == "point" and last not in (None, "a"):
            k = j + 1
            while k < len(tokens) and tokens[k].text in _UNITS:
                k += 1
            if k > j + 1:  # "two point five": the digits after "point" are decimals
                current += float("0." + "".join(str(_UNITS[t.text]) for t in tokens[j + 1 : k]))
                end, j = tokens[k - 1].end, k
                said += ["point", "decimals"]
            break
        cls = _word_class(tok.text)
        if cls is None:
            break
        if last not in _FOLLOWS[cls]:
            flush()
        if last is None and tok.text in _COUNTED:
            break
        if last is None:
            start = tok.start
        if cls == "hundred":
            current = (current or 1.0) * 100
        elif cls == "scale":
            total, current = total + (current or 1.0) * _SCALES[tok.text], 0.0
        else:
            current += _UNITS.get(tok.text) or _TEENS.get(tok.text) or _TENS.get(tok.text) or 0
        last, end = cls, tok.end
        said.append(tok.text)
        j += 2 if _joins(tokens, j + 1) else 1
    flush()
    return found, j


# Read a digit and the scale words right after it as one number ("4 thousand", "3.9 hundred").
def _read_scaled_digit(tokens: list[_Tok], i: int) -> tuple[_Tok, int]:
    value, end, j = tokens[i].value, tokens[i].end, i + 1
    while j < len(tokens) and tokens[j].kind == "word" and tokens[j].text in _DIGIT_SCALES:
        value, end, j = value * _DIGIT_SCALES[tokens[j].text], tokens[j].end, j + 1
    return _num(value, tokens[i].start, end), j


# "one-third" / "two thirds": the unit word, an optional hyphen, and the fraction word.
def _read_unit_fraction(tokens: list[_Tok], i: int) -> tuple[_Tok, int] | None:
    if i >= len(tokens) or tokens[i].kind != "word":
        return None
    a = tokens[i]
    j = i + 1
    if j < len(tokens) and tokens[j].kind == "sym" and tokens[j].text == "-":
        j += 1
    if j >= len(tokens) or tokens[j].kind != "word":
        return None
    value = _UNIT_FRACTIONS.get(f"{a.text} {tokens[j].text}")
    if value is None:
        return None
    return _num(value, a.start, tokens[j].end), j + 1


# "twenty-first" / "thirty third": a tens word, an optional hyphen, and a unit ordinal.
def _read_compound_ordinal(tokens: list[_Tok], i: int) -> tuple[_Tok, int] | None:
    a = tokens[i]
    if a.kind != "word" or a.text not in _TENS:
        return None
    j = i + 1
    if j < len(tokens) and tokens[j].kind == "sym" and tokens[j].text == "-":
        j += 1
    if j >= len(tokens) or tokens[j].kind != "word" or tokens[j].text not in _UNIT_ORDINALS:
        return None
    value = _TENS[a.text] + _UNIT_ORDINALS[tokens[j].text]
    return _num(float(value), a.start, tokens[j].end), j + 1


# Turn tokens into a list where each number is one item and other tokens stay as they are.
def _numbers_and_tokens(tokens: list[_Tok]) -> list[_Tok]:
    items: list[_Tok] = []
    i = 0
    while i < len(tokens):
        tok, nums, nxt = tokens[i], [], i + 1
        single = _ORDINALS.get(tok.text) or _STANDALONE.get(tok.text) or _fold_value(tok.text)
        frac = _read_unit_fraction(tokens, i) or _read_compound_ordinal(tokens, i)
        if frac is not None:
            nums, nxt = [frac[0]], frac[1]
        elif tok.kind == "num" and tok.parts is not None:
            nums = [_num(tok.value, tok.start, tok.end, parts=tok.parts)]
        elif tok.kind == "num":
            scaled, nxt = _read_scaled_digit(tokens, i)
            nums = [scaled]
        elif tok.kind == "ord":
            nums = [_num(tok.value, tok.start, tok.end, tok.value in (1.0, 2.0))]
        elif tok.kind == "word" and single is not None:
            nums = [_num(float(single), tok.start, tok.end)]
        elif tok.kind == "word" and (_word_class(tok.text) or tok.text == "a"):
            nums, nxt = _read_words(tokens, i)
        items.extend(nums or [tok])
        i = nxt if nums else i + 1
    return items


# Text of the item at k, for matching separators like ":", "to", "%", and "percent".
def _text_at(items: list[_Tok], k: int) -> str | None:
    return items[k].text if k < len(items) and items[k].kind != "number" else None


# Length of a ratio separator starting at k (":", "to", "-to-"), or 0 when there is none.
def _ratio_sep(items: list[_Tok], k: int) -> int:
    if _text_at(items, k) in (":", "to"):
        return 1
    return 3 if [_text_at(items, k + n) for n in range(3)] == ["-", "to", "-"] else 0


def extract_numbers(text: str) -> list[FoundNumber]:
    """Every number in the text, with percentages and ratios recognized."""
    items = _numbers_and_tokens(_tokenize(text))
    found: list[FoundNumber] = []
    k = 0
    while k < len(items):
        item = items[k]
        if item.kind != "number":
            k += 1
            continue
        sep = _ratio_sep(items, k + 1)
        right = items[k + 1 + sep] if sep and k + 1 + sep < len(items) else None
        nxt, nxt2 = _text_at(items, k + 1), _text_at(items, k + 2)
        if right is not None and right.kind == "number":
            span = text[item.start : right.end]
            found.append(FoundNumber(span, item.value, "ratio", right=right.value))
            k += 2 + sep
        elif nxt in ("%", "percent") or (nxt == "per" and nxt2 == "cent"):
            width = 3 if nxt == "per" else 2
            span = text[item.start : items[k + width - 1].end]
            found.append(FoundNumber(span, item.value, "percent"))
            k += width
        else:
            span = text[item.start : item.end]
            found.append(FoundNumber(span, item.value, ordinary=item.ordinary, parts=item.parts))
            k += 1
    return found


# True when x matches any allowed number within the rounding tolerance.
def _near(x: float, pool: frozenset[float]) -> bool:
    return any(abs(x - a) <= max(ABS_TOL, REL_TOL * abs(a)) for a in pool)


# A digit fraction is said as its digits, so the value and both written sides must be allowed:
# "50/50" is not 1, and a zero bottom ("5/0") never is.
def _fraction_supported(top: float, bottom: float, values: frozenset[float]) -> bool:
    sides = _near(top, values) and _near(bottom, values)
    return bottom != 0 and sides and _near(top / bottom, values)


def is_supported(number: FoundNumber, allowed: AllowedNumbers) -> bool:
    """Whether one found number is backed by the allowed set."""
    if number.kind == "percent":
        return _near(number.value, allowed.percents)
    if number.kind == "ratio" and number.right is not None:
        a, b = number.value, number.right
        both = _near(a, allowed.values) and _near(b, allowed.values)
        return both or (b != 0 and any(abs(a / b - o) <= ODDS_REL_TOL * o for o in allowed.odds))
    if number.parts is not None:
        return _fraction_supported(*number.parts, allowed.values)
    return number.ordinary or _near(number.value, allowed.values)


def find_unsupported_numbers(text: str, allowed: AllowedNumbers) -> list[FoundNumber]:
    """The numbers in the text that are not in the allowed set (empty list = the line is clean)."""
    return [n for n in extract_numbers(text) if not is_supported(n, allowed)]
