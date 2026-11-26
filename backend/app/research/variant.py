"""Respect the fighter's variant (#522): code reads the sex and age words a figure was given with.

Research used to ignore "Adult male" and the like, so a figure could describe another animal:
the lion's mass came from Wikidata's female figure. A figure for a young animal never stands in
for an adult. A figure for the other sex is used only when nothing for the fighter's own sex is
left, since the same animal's other sex is still closer than a category default (the
hand-verified lion uses a lioness's bite force for the same reason).
"""

import re
from collections.abc import Callable

from app.research.evidence_check import normalize_text

MALE = frozenset({"male", "males", "bull", "bulls", "stallion", "stallions", "boar", "boars"})
FEMALE = frozenset(
    {"female", "females", "lioness", "lionesses", "cow", "cows", "mare", "mares", "sow", "sows"}
)
YOUNG = frozenset(
    {"birth", "newborn", "newborns", "hatchling", "hatchlings", "juvenile", "juveniles", "cub"}
    | {"cubs", "calf", "calves", "foal", "foals", "pup", "pups", "chick", "chicks"}
)
ADULT = frozenset({"adult", "adults"})
OTHER_SEX = {"male": "female", "female": "male"}
# Species names that hold a sex word name an animal, not its sex ("bull shark", "wild boar",
# "sea cow"), so they are taken out before the words are read.
SPECIES_NAMES = re.compile(
    r"\b(?:bull (?:shark|terrier|ant|snake)|pit bull|wild boar|sea cow|cow shark)s?\b",
    re.IGNORECASE,
)
WORD = re.compile(r"[a-z]+")
SENTENCE_END = (". ", "? ", "! ")


# The sex and age marks among some words: "male", "female", "young", "adult".
def marks(words: list[str]) -> set[str]:
    found = set()
    for word in words:
        for mark, group in (("male", MALE), ("female", FEMALE), ("young", YOUNG), ("adult", ADULT)):
            if word in group:
                found.add(mark)
    return found


# The lowercase words of a text, without species names that hold a sex word.
def words_of(text: str) -> list[str]:
    return WORD.findall(SPECIES_NAMES.sub(" ", text).lower())


# What a figure is about: the quote's own sex and age words, or, when it has none, the nearest
# such word before it in its sentence ("Males weigh 190 kg and females 126 kg": "126 kg" is the
# females' figure).
def described(quote: str, passage: str = "") -> set[str]:
    own = marks(words_of(quote))
    if own or not passage:
        return own
    text, cleaned = normalize_text(passage), normalize_text(quote)
    at = text.find(cleaned)
    if at < 0:
        return set()
    start = max(text.rfind(end, 0, at) for end in SENTENCE_END) + 1
    lead = [word for word in words_of(text[start:at]) if marks([word])]
    return marks(lead[-1:])


# The items whose figure fits the variant: no young animal's for an adult, and another sex's
# only when none is left for the fighter's own. `context` gives an item's quote and passage.
def prefer_variant[T](
    variant: str | None, items: list[T], context: Callable[[T], tuple[str, str]]
) -> list[T]:
    wanted = marks(words_of(variant or ""))
    sex = "male" if "male" in wanted else "female" if "female" in wanted else None
    said = [(item, described(*context(item))) for item in items]
    if "adult" in wanted:
        said = [(item, m) for item, m in said if not ("young" in m and "adult" not in m)]
    other = OTHER_SEX.get(sex or "")
    own = [(item, m) for item, m in said if not (other in m and sex not in m)]
    return [item for item, _ in (own or said)]
