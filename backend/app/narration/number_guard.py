"""The number guard: find every number in a script line that the inputs do not support.

It reads digits ("1,200", "3,5", "1/2", "1e3", "2 point 5", "3rd"), number words ("four hundred
and twelve", "forty-two", "two point five", "a dozen", "a score", "three quarters"), quantity words
("half", "twice", "thrice", "double", "triple", "tens", "dozens", "hundreds", "thousands",
"millions"), ordinals ("third" to "twentieth"), percentages ("40%", "forty per cent"), and ratios
("8:1", "eight to one", "8-to-1"). ARCHITECTURE "The number rule": a plain number must match an
allowed value (within rounding), a percentage an allowed percentage, and a ratio either two allowed
values or a win-odds ratio. "one", "two", "first", "second", "1st", "2nd" on their own are always
allowed, so "one punch" or "these two" never trips it; digits ("2"), percentages, ratios, decimals
("one point five") and "twice" get no such pass. Known limit: "a third" reads as the ordinal 3.
Pure standard-library code, no I/O, safe to call on every line.
"""

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
)  # fmt: skip
_SCALES = {
    "thousand": 1e3, "million": 1e6, "billion": 1e9, "dozen": 12.0,
    "score": 20.0, "quarter": 0.25, "quarters": 0.25,
}  # fmt: skip
# Scale words that only count after "a" or a number ("a score", "three quarters", not "the score").
_COUNTED = {"score", "quarter", "quarters"}
_STANDALONE = {
    "half": 0.5, "twice": 2.0, "double": 2.0, "thrice": 3.0, "triple": 3.0, "tens": 10.0,
    "dozens": 12.0, "hundreds": 100.0, "thousands": 1e3, "millions": 1e6, "billions": 1e9,
}  # fmt: skip

_TOKEN = re.compile(
    r"(?P<num>\d+(?:\.\d+)?e[+-]?\d+"  # exponent: 1e3, 2.5e-2
    r"|\d+/\d+"  # fraction: 1/2
    r"|\d+ point \d+"  # spoken decimal: 2 point 5
    r"|\d{1,3}(?:,\d{3})+(?!\d)(?:\.\d+)?"  # thousands separators: 1,200
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


@dataclass
class _Tok:
    """A token ("num", "ord", "word", "sym"), or after grouping a whole number ("number")."""

    kind: str
    text: str
    start: int
    end: int
    value: float = 0.0
    ordinary: bool = False


# A whole number spanning start..end of the text.
def _num(value: float, start: int, end: int, ordinary: bool = False) -> _Tok:
    return _Tok("number", "", start, end, value, ordinary)


# The value of a digit token: fractions divide, "point" and a lone comma are decimal points.
def _digits_value(s: str) -> float:
    if "/" in s:
        top, bottom = (float(p) for p in s.split("/"))
        return top / bottom if bottom else top
    s = re.sub(r",(?=\d{3}(?!\d))", "", s.replace(" point ", "."))
    return float(s.replace(",", "."))


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
def _tokenize(text: str) -> list[_Tok]:
    tokens = []
    for m in _TOKEN.finditer(text.lower()):
        if m.group("num"):
            kind = "ord" if m.group("ord") else "num"
            tokens.append(_Tok(kind, m.group(0), m.start(), m.end(), _digits_value(m["num"])))
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


# Turn tokens into a list where each number is one item and other tokens stay as they are.
def _numbers_and_tokens(tokens: list[_Tok]) -> list[_Tok]:
    items: list[_Tok] = []
    i = 0
    while i < len(tokens):
        tok, nums, nxt = tokens[i], [], i + 1
        single = _ORDINALS.get(tok.text) or _STANDALONE.get(tok.text)
        if tok.kind in ("num", "ord"):
            ordinary = tok.kind == "ord" and tok.value in (1.0, 2.0)
            nums = [_num(tok.value, tok.start, tok.end, ordinary)]
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
            found.append(FoundNumber(span, item.value, ordinary=item.ordinary))
            k += 1
    return found


# True when x matches any allowed number within the rounding tolerance.
def _near(x: float, pool: frozenset[float]) -> bool:
    return any(abs(x - a) <= max(ABS_TOL, REL_TOL * abs(a)) for a in pool)


def is_supported(number: FoundNumber, allowed: AllowedNumbers) -> bool:
    """Whether one found number is backed by the allowed set."""
    if number.kind == "percent":
        return _near(number.value, allowed.percents)
    if number.kind == "ratio" and number.right is not None:
        a, b = number.value, number.right
        both = _near(a, allowed.values) and _near(b, allowed.values)
        return both or (b != 0 and any(abs(a / b - o) <= ODDS_REL_TOL * o for o in allowed.odds))
    return number.ordinary or _near(number.value, allowed.values)


def find_unsupported_numbers(text: str, allowed: AllowedNumbers) -> list[FoundNumber]:
    """The numbers in the text that are not in the allowed set (empty list = the line is clean)."""
    return [n for n in extract_numbers(text) if not is_supported(n, allowed)]
