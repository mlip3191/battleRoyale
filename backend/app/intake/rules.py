"""Code rules for intake: counts, names, size references, and terrain (never the model's call).

Everything here is pure: no providers, no settings, no I/O. The parser (parser.py) feeds it the
user's own words for each side and the model's proposed names, and uses what comes back.
"""

import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class CountReading:
    """How many fighters the user's words ask for, or why that can't be used."""

    count: int | None
    """Whole number of fighters; None when the words hold no quantity at all."""
    problem: Literal["fraction", "zero"] | None = None
    """Set when the quantity is a fraction or zero, which the app can't simulate."""


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


# Read the quantity at the start of one side's words: "a dozen house cats" -> 12.
def read_count(raw: str) -> CountReading:
    pairs = TOKEN.findall(raw.lower())
    tokens, hyphens = [t for t, _ in pairs], [h for _, h in pairs]
    total = current = 0
    saw_number = saw_article = False
    for index, token in enumerate(tokens):
        if _is_description(tokens, hyphens, index):
            break
        if NUMBER_TOKEN.match(token):
            value = _digit_value(token)
            if value == "fraction":
                return CountReading(None, "fraction")
            current, saw_number = current + value, True
        elif token in FRACTION_WORDS and _next(tokens, index) in FRACTION_FOLLOWERS:
            return CountReading(None, "fraction")
        elif token in ZERO_WORDS:
            return CountReading(0, "zero")
        elif token in UNITS:
            current, saw_number = current + UNITS[token], True
        elif token in MULTIPLIERS:
            current, saw_number = max(current, 1) * MULTIPLIERS[token], True
        elif token in SCALES:
            total, current, saw_number = total + max(current, 1) * SCALES[token], 0, True
        elif token in ARTICLES and not saw_number and index == 0:
            saw_article = True
        elif token in {"and", "of"} and saw_number:
            continue
        else:
            break
    if saw_number:
        count = total + current
        return CountReading(count, "zero" if count == 0 else None)
    return CountReading(1 if saw_article else None)


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
}  # fmt: skip
TERRAIN_FILLER = {"in", "on", "at", "a", "an", "the", "of", "inside", "into", "middle"}


# Look up a phrase (or any word in it) in the terrain table; exact words beat approximate ones.
def _lookup_terrain(phrase: str) -> tuple[Terrain, bool] | None:
    if phrase in TERRAIN_WORDS:
        return TERRAIN_WORDS[phrase]
    hits = [TERRAIN_WORDS[w] for w in map(singular_word, phrase.split()) if w in TERRAIN_WORDS]
    exact = [hit for hit in hits if hit[1]]
    return (exact or hits or [None])[0]


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
