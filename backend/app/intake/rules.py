"""Code rules for intake: counts, names, size references, and terrain (never the model's call).

Everything here is pure: no providers, no settings, no I/O. The parser (parser.py) feeds it the
user's own words for each side and the model's proposed names, and uses what comes back.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.models.terrain import Terrain
from app.text import IRREGULAR_PLURALS, UNCHANGED

# --- Counts -------------------------------------------------------------------------------

ARTICLES = {"a", "an", "the"}
UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}  # fmt: skip
SCALES = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
MULTIPLIERS = {"hundred": 100, "dozen": 12, "pair": 2, "couple": 2}
ZERO_WORDS = {"zero", "no", "none"}
FRACTION_WORDS = {"half", "halves", "quarter", "quarters", "third", "thirds", "fraction"}
# A fraction word only means a fraction before these ("half a horse", not "a quarter horse").
FRACTION_FOLLOWERS = {"a", "an", "of", "the"}
# Words that may sit before a name as part of its quantity; stripped from model-given names.
QUANTITY_WORDS = ARTICLES | set(UNITS) | set(SCALES) | set(MULTIPLIERS) | {"and", "of"}
# Digits with optional thousands commas, a decimal part, or a "/" fraction ("1,000", "1.5", "1/2").
NUMBER_TOKEN = re.compile(r"^\d[\d,]*(?:\.\d+)?(?:/\d+)?$")
# A token plus a trailing hyphen, if any ("three-" in "three-headed"), to spot descriptions.
TOKEN = re.compile(r"(\d[\d,]*(?:\.\d+)?(?:/\d+)?|[a-z]+)(-?)")
# Group words with no number ("a swarm of bees") and the count code assumes for one group (#561).
# Rough, typical sizes, not sourced figures: the card says the count was assumed, and the user can
# type a number instead. "army" is left out on purpose: it names a military unit (D-69).
GROUP_WORDS = {
    "pack": 6, "pride": 6, "pod": 10, "gaggle": 10, "herd": 20, "troop": 20, "flock": 30,
    "school": 100, "swarm": 1_000, "colony": 1_000,
}  # fmt: skip
# Small words that may sit between a group word's "of" and a typed count, which still wins over
# the group's default: "a pack of the 12 wolves", "a pack of maybe a dozen wolves" (#573).
COUNT_FILLERS = {"the", "a", "an", "about", "some", "around", "roughly", "maybe"}
MAX_COUNT_FILLERS = 2  # past this many, the words after "of" are not read as a count
# Scientific notation as typed, "1e3" or "2.5E2", up to e99 (#561).
SCIENTIFIC = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)[eE]\+?(\d{1,2})(?![\w.])")
SCIENTIFIC_MAX = 1_000_000  # past this, the note says "more than" instead of every digit
# A minus sign stuck to a number at the start of a word, "-3" (not "T-1000" or "1-3") (#561).
MINUS = re.compile(r"(?<![\w.])[-−](\d[\d,]*(?:\.\d+)?)")


@dataclass(frozen=True)
class CountReading:
    """How many fighters the user's words ask for, or why that can't be used."""

    count: int | None
    """Whole number of fighters; None when the words hold no quantity at all."""
    problem: Literal["fraction", "zero"] | None = None
    """Set when the quantity is a fraction or zero, which the app can't simulate."""
    group: str | None = None
    """The group word the count was assumed from ("swarm"), when no number was typed for it."""
    multiplied: str | None = None
    """The typed words a count of groups was multiplied from ("2 packs of 5"), for the card."""


# The group word at index when "of" follows it ("swarm" in "a swarm of bees"), else None.
def _group_word(tokens: list[str], index: int) -> str | None:
    word = singular_word(tokens[index])
    return word if word in GROUP_WORDS and _next(tokens, index) == "of" else None


# True for a token that states a count: digits or a number word.
def _is_count_word(token: str) -> bool:
    return (
        bool(NUMBER_TOKEN.match(token)) or token in UNITS or token in SCALES or token in MULTIPLIERS
    )


# Tokens back into the words as typed, for a note: "twenty", "five" -> "twenty-five".
def _typed_words(tokens: list[str], hyphens: list[str]) -> str:
    return "".join(t + (h or " ") for t, h in zip(tokens, hyphens, strict=True)).strip(" -")


# The count typed after the group phrase at index, and where its words end; None when no number
# follows. Up to MAX_COUNT_FILLERS small words may sit in between: "pack of the 12" (#573).
def _count_after_group(
    tokens: list[str], hyphens: list[str], index: int
) -> tuple[CountReading, int] | None:
    start, limit = index + 2, min(len(tokens), index + 2 + MAX_COUNT_FILLERS)
    while start < limit and tokens[start] in COUNT_FILLERS and not hyphens[start]:
        start += 1  # a hyphenated "a" starts a name ("A-10"), so it is not a filler
    if start >= len(tokens) or not _is_count_word(tokens[start]):
        return None
    reading, used = _read_tokens(tokens[start:], hyphens[start:])
    return (reading, start + used) if used else None  # "12-foot" describes, so it isn't a count


# A count typed after a group phrase, times the number of groups when that was typed too: the
# user typed both numbers, so code multiplies them. "2 packs of 5" -> 10, with the typed words
# kept for the card's note (#573). groups is None for "a pack of 12": the 12 is used as typed.
def _times_groups(
    after: tuple[CountReading, int], groups: int | None, tokens: list[str], hyphens: list[str]
) -> tuple[CountReading, int]:
    each, end = after
    if groups is None or each.count is None:
        return each, end
    count = groups * each.count
    if count == 0:
        return CountReading(0, "zero"), end
    typed = _typed_words(tokens[:end], hyphens[:end]) if groups > 1 else None
    return CountReading(count, multiplied=typed), end


# Numbers written in ways the count reader can't use, rewritten with a note for the card (#561):
# "1e3 ants" -> "1000 ants", "-3 lions" -> "3 lions".
def tidy_numbers(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []

    def expand(match: re.Match[str]) -> str:
        value = Decimal(match.group(1)) * 10 ** int(match.group(2))
        if value > SCIENTIFIC_MAX:  # "1e99": a short note; the side is capped later anyway
            notes.append(f"We read '{match.group(0)}' as more than {SCIENTIFIC_MAX:,}.")
            return str(SCIENTIFIC_MAX)
        plain = f"{value.normalize():f}"
        notes.append(f"We read '{match.group(0)}' as {Decimal(plain):,}.")
        return plain

    def unsign(match: re.Match[str]) -> str:
        notes.append(
            f"We read '{match.group(0)}' as {match.group(1)}, since a side can't have "
            "fewer than zero fighters."
        )
        return match.group(1)

    text = SCIENTIFIC.sub(expand, text)
    return MINUS.sub(unsign, text), notes


# Value of a digit token, or "fraction" for "1/2" and "1.5" (but "2.0" is just 2).
def _digit_value(token: str) -> int | Literal["fraction"]:
    if "/" in token:
        return "fraction"
    whole, _, decimals = token.replace(",", "").partition(".")
    if decimals.strip("0"):
        return "fraction"
    return int(whole)


# The token after index, or "" at the end.
def _next(tokens: list[str], index: int) -> str:
    return tokens[index + 1] if index + 1 < len(tokens) else ""


# True when a number is hyphenated to a non-number word: "three-headed", "6-foot", "500-pound".
def _is_description(tokens: list[str], hyphens: list[str], index: int) -> bool:
    token, following = tokens[index], _next(tokens, index)
    is_number = bool(NUMBER_TOKEN.match(token)) or token in UNITS
    joins_number = following in UNITS or bool(NUMBER_TOKEN.match(following))
    return is_number and bool(hyphens[index]) and bool(following) and not joins_number


# Read the quantity at the start of tokens; the second value is where the quantity's words end
# (0 when no number was typed), so a note can quote them.
def _read_tokens(tokens: list[str], hyphens: list[str]) -> tuple[CountReading, int]:
    total = current = end = 0
    for index, token in enumerate(tokens):
        if _is_description(tokens, hyphens, index):
            break
        if NUMBER_TOKEN.match(token):
            value = _digit_value(token)
            if value == "fraction":
                return CountReading(None, "fraction"), index + 1
            current += value
        elif token in FRACTION_WORDS and _next(tokens, index) in FRACTION_FOLLOWERS:
            return CountReading(None, "fraction"), index + 1
        elif token in ZERO_WORDS:
            return CountReading(0, "zero"), index + 1
        elif token in UNITS:
            current += UNITS[token]
        elif token in MULTIPLIERS:
            current = max(current, 1) * MULTIPLIERS[token]
        elif token in SCALES:
            total, current = total + max(current, 1) * SCALES[token], 0
        elif group := _group_word(tokens, index):
            if after := _count_after_group(tokens, hyphens, index):  # a typed count wins (#573)
                return _times_groups(after, total + current if end else None, tokens, hyphens)
            if end:  # "2 packs of wolves": the typed count, as typed (#561 review)
                break
            return CountReading(GROUP_WORDS[group], None, group), 0  # "a swarm of bees" -> 1,000
        elif (token in ARTICLES and index == 0) or (token in {"and", "of"} and end):
            continue
        else:
            break
        end = index + 1
    if end:
        count = total + current
        return CountReading(count, "zero" if count == 0 else None), end
    return CountReading(1 if tokens[:1] and tokens[0] in ARTICLES else None), 0


# Read the quantity at the start of one side's words: "a dozen house cats" -> 12.
def read_count(raw: str) -> CountReading:
    pairs = TOKEN.findall(raw.lower())
    return _read_tokens([t for t, _ in pairs], [h for _, h in pairs])[0]


# Keep a count within the per-side limit; the second value is the assumption to show, if any.
def clamp_count(count: int, entity: str, max_count: int) -> tuple[int, str | None]:
    if count <= max_count:
        return count, None
    note = (
        f"Capped the {entity} side at {max_count:,} (the most per side); you asked for {count:,}."
    )
    return max_count, note


# --- Names --------------------------------------------------------------------------------

# IRREGULAR_PLURALS (plural -> singular) and UNCHANGED live in app/text.py, shared with the
# pluralizer (#271); they are imported at the top of this module.
# Singular endings that end in "s" and must keep it ("albatross", "walrus", "stegosaurus").
KEEP_S_ENDINGS = ("ss", "us")


# One word to its singular form: "wolves" -> "wolf", "army" stays "army".
def singular_word(word: str) -> str:
    if word in IRREGULAR_PLURALS:
        return IRREGULAR_PLURALS[word]
    if word in UNCHANGED or word.endswith(KEEP_S_ENDINGS):
        return word
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("sses", "ches", "shes", "xes")):
        return word[:-2]
    if len(word) > 2 and word.endswith("s"):
        return word[:-1]
    return word


# A name to lowercase singular with no quantity or size words: "3 Duck-Sized Horses" -> "horse".
def normalize_entity(name: str) -> str:
    text = strip_size_phrase(name)
    words = re.sub(r"[^a-z0-9' -]+", " ", text).split()
    while words and (words[0] in QUANTITY_WORDS or NUMBER_TOKEN.match(words[0])):
        words = words[1:]
    if not words:
        return ""
    words[-1] = singular_word(words[-1])
    return " ".join(words)


# True for a word before a name that is only part of its quantity: "a", "12", "dozen", "about".
def _is_quantity_word(word: str) -> bool:
    return word in QUANTITY_WORDS or word in COUNT_FILLERS or bool(NUMBER_TOKEN.match(word))


# A normalized name without a leading group phrase, for the fighter intake keeps: "swarm of bee"
# -> "bee" (#561). The safety lookups keep the whole name, so they search exactly as before.
def without_group(name: str) -> str:
    words = name.split()
    if len(words) > 2 and singular_word(words[0]) in GROUP_WORDS and words[1] == "of":
        words = words[2:]
        while len(words) > 1 and _is_quantity_word(words[0]):
            words = words[1:]  # "pack of about 12 wolf" -> "wolf" (#573)
        return " ".join(words)
    return name


# --- Size references ----------------------------------------------------------------------

# "duck-sized", "school-bus-sized", "horse sized" -> the words before "sized".
SIZED = re.compile(r"\b([a-z]+(?:-[a-z]+)*)[- ]sized\b")
# "the size of a school bus" -> "school bus": up to three words, stopping at a joining word.
_SIZE_WORD = r"(?!(?:in|vs|versus|with|and|on|at|or)\b)[a-z]+(?:-[a-z]+)*"
SIZE_OF = re.compile(rf"\b(?:the )?size of (?:an? |the )?({_SIZE_WORD}(?: {_SIZE_WORD}){{0,2}})\b")


# "medium-sized dog" describes a size, not another entity, so these never become references.
SIZE_ADJECTIVES = {
    "small", "medium", "large", "big", "full", "average", "normal", "regular", "mid", "life",
    "bite", "fun", "king", "queen", "pint", "good", "decent", "over", "under", "oddly", "odd",
}  # fmt: skip


# The entity a side is sized like, from the user's own words; never a number.
def find_size_reference(raw: str) -> str | None:
    text = raw.lower()
    match = SIZED.search(text) or SIZE_OF.search(text)
    if match is None or match.group(1).split("-")[0] in SIZE_ADJECTIVES:
        return None
    name = normalize_entity(match.group(1).replace("-", " "))
    return name or None


# Remove a size phrase from a name: "duck-sized horse" -> "horse".
def strip_size_phrase(name: str) -> str:
    text = SIZED.sub(" ", name.lower())
    text = SIZE_OF.sub(" ", text)
    return " ".join(text.split())


# --- Terrain ------------------------------------------------------------------------------

# Words users say -> (terrain, exact). Inexact matches add an assumption so the user sees it.
TERRAIN_WORDS: dict[str, tuple[Terrain, bool]] = {
    "arena": (Terrain.ARENA, True), "ring": (Terrain.ARENA, True),
    "colosseum": (Terrain.ARENA, True), "stadium": (Terrain.ARENA, True),
    "cage": (Terrain.ARENA, True), "octagon": (Terrain.ARENA, True),
    "open field": (Terrain.OPEN_FIELD, True), "field": (Terrain.OPEN_FIELD, True),
    "plain": (Terrain.OPEN_FIELD, True), "grassland": (Terrain.OPEN_FIELD, True),
    "savanna": (Terrain.OPEN_FIELD, True), "savannah": (Terrain.OPEN_FIELD, True),
    "prairie": (Terrain.OPEN_FIELD, True), "meadow": (Terrain.OPEN_FIELD, True),
    "desert": (Terrain.OPEN_FIELD, False), "snow": (Terrain.OPEN_FIELD, False),
    "tundra": (Terrain.OPEN_FIELD, False), "ice": (Terrain.OPEN_FIELD, False),
    "forest": (Terrain.FOREST, True), "wood": (Terrain.FOREST, True),
    "woodland": (Terrain.FOREST, True), "jungle": (Terrain.FOREST, True),
    "rainforest": (Terrain.FOREST, True),
    "water": (Terrain.WATER, True), "ocean": (Terrain.WATER, True),
    "sea": (Terrain.WATER, True), "lake": (Terrain.WATER, True),
    "river": (Terrain.WATER, True), "pond": (Terrain.WATER, True),
    "underwater": (Terrain.WATER, True),
    "shoreline": (Terrain.SHORELINE, True), "shore": (Terrain.SHORELINE, True),
    "beach": (Terrain.SHORELINE, True), "coast": (Terrain.SHORELINE, True),
    "riverbank": (Terrain.SHORELINE, True), "swamp": (Terrain.SHORELINE, False),
    "marsh": (Terrain.SHORELINE, False),
    "urban": (Terrain.URBAN, True), "city": (Terrain.URBAN, True),
    "town": (Terrain.URBAN, True), "street": (Terrain.URBAN, True),
    "downtown": (Terrain.URBAN, True), "alley": (Terrain.URBAN, True),
    "parking lot": (Terrain.URBAN, True),
    "mountain": (Terrain.MOUNTAIN, True), "mountainside": (Terrain.MOUNTAIN, True),
    "cliff": (Terrain.MOUNTAIN, True), "hill": (Terrain.MOUNTAIN, False),
    "canyon": (Terrain.MOUNTAIN, False),
    "sky": (Terrain.SKY, True), "air": (Terrain.SKY, True),
    "midair": (Terrain.SKY, True), "cloud": (Terrain.SKY, False),  # a cloud forest is a forest
}  # fmt: skip
TERRAIN_FILLER = {"in", "on", "at", "a", "an", "the", "of", "inside", "into", "middle"}


# Look up a phrase (or any word in it) in the terrain table; exact words beat approximate ones.
def _lookup_terrain(phrase: str) -> tuple[Terrain, bool] | None:
    if phrase in TERRAIN_WORDS:
        return TERRAIN_WORDS[phrase]
    hits = [TERRAIN_WORDS[w] for w in map(singular_word, phrase.split()) if w in TERRAIN_WORDS]
    exact = [hit for hit in hits if hit[1]]
    return (exact or hits or [None])[0]


# The text's trailing place phrase, "... in a forest" -> "in a forest", but only when it names a
# battlefield we know (#456). The model sometimes drops the place; this keeps "in a forest" from
# silently becoming the arena. Only the very end of the text counts, up to three words, so a place
# word inside a fighter's name ("a sea turtle vs a wolf") or "in a minute" is never the battlefield.
# Up to five words ("in the middle of the forest"), a hyphenated word ("rain-forest"), and any
# trailing marks or a closing bracket ("in a forest!!", "in a forest :)", "(in a forest)").
_TRAILING_PLACE = re.compile(
    r"\s+\(?((?:in|on|at|inside|into)(?:\s+[A-Za-z]+(?:-[A-Za-z]+)?){1,5})[\s.!?,:;)\"'~]*$", re.I
)


def terrain_in_text(text: str) -> str | None:
    found = _TRAILING_PLACE.search(text)
    if found is None:
        return None
    words = [w for w in re.findall(r"[a-z]+", found.group(1).lower()) if w not in TERRAIN_FILLER]
    return found.group(1) if words and _lookup_terrain(" ".join(words)) else None


# The user's terrain words -> a Terrain, plus an assumption when it isn't an exact match.
def map_terrain(phrase: str | None) -> tuple[Terrain, str | None]:
    found = re.findall(r"[a-z]+", (phrase or "").lower().replace("_", " "))
    words = [w for w in found if w not in TERRAIN_FILLER]
    if not words:
        return Terrain.ARENA, None
    cleaned = " ".join(words)
    if cleaned in {t.value.replace("_", " ") for t in Terrain}:
        return Terrain(cleaned.replace(" ", "_")), None
    hit = _lookup_terrain(cleaned)
    if hit is None:
        note = f'We don\'t have a "{cleaned}" battlefield yet, so they fight in the arena.'
        return Terrain.ARENA, note
    terrain, exact = hit
    if exact:
        return terrain, None
    label = terrain.value.replace("_", " ")
    return terrain, f'Treated "{cleaned}" as {label} terrain.'
