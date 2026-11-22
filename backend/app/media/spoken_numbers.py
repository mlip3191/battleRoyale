"""Counts written out in words for the speech service only (#502).

The speech service misread the digit string "128" as "28", so a line sent to TTS has its whole
numbers of three or more digits ("128", "1000", "1,000") written out in words ("one hundred
twenty-eight", "one thousand"). Numbers under 100, decimals ("2.5"), ratios and fractions
("3:1", "1/128") and numbers with a leading zero are left as they are. A "%" right after a
converted number becomes " percent". Captions, saved scripts and results never pass through here:
they keep the digits.
"""

import re

_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen \
fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_SCALES = [(10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (1000, "thousand")]
_LARGEST = 10**15  # from here on the digits are left alone

# A whole number of 3+ digits, plain or comma-grouped, not part of a decimal, ratio or fraction.
_COUNT = re.compile(r"(?<![\d.,:/])([1-9]\d{0,2}(?:,\d{3})+|[1-9]\d{2,})(?![\d:/]|[.,]\d)(%?)")


# 0-999 in words: "one hundred twenty-eight".
def _under_thousand(n: int) -> str:
    words: list[str] = []
    if n >= 100:
        words.append(f"{_ONES[n // 100]} hundred")
        n %= 100
    if n >= 20:
        tens, ones = divmod(n, 10)
        words.append(_TENS[tens] + (f"-{_ONES[ones]}" if ones else ""))
    elif n or not words:
        words.append(_ONES[n])
    return " ".join(words)


# A whole number in words: 1000 -> "one thousand", 10500 -> "ten thousand five hundred".
def number_words(n: int) -> str:
    words: list[str] = []
    for size, name in _SCALES:
        if n >= size:
            words.append(f"{_under_thousand(n // size)} {name}")
            n %= size
    if n or not words:
        words.append(_under_thousand(n))
    return " ".join(words)


# One matched count in words, with "%" read as " percent".
def _say(match: re.Match[str]) -> str:
    n = int(match.group(1).replace(",", ""))
    if n >= _LARGEST:
        return match.group(0)
    return number_words(n) + (" percent" if match.group(2) else "")


# The line as it should be spoken: counts of 3+ digits in words, everything else unchanged.
def speech_text(line: str) -> str:
    return _COUNT.sub(_say, line)
