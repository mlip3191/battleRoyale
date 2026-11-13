"""Shared English wording helpers: fighter names after a count ("3 African elephants").

One pluralizer for the whole app (#258), used by intake, simulation (fair fight) and narration.
The word tables stay in app/intake/rules.py (their single source of truth; that module is pure).
"""

from app.intake.rules import IRREGULAR_PLURALS, UNCHANGED

# Singular -> plural for words the suffix rules would get wrong: "mouse" -> "mice".
SINGULAR_TO_PLURAL = {singular: plural for plural, singular in IRREGULAR_PLURALS.items()}

# First words that are proper adjectives or place names, so they keep their capital after a count:
# "3 African elephants", not "3 african elephants" (#250).
PROPER_FIRST_WORDS = frozenset(
    {
        "African", "American", "Antarctic", "Arabian", "Arctic", "Asian", "Atlantic",
        "Australian", "Aztec", "Bengal", "Bornean", "Burmese", "Canada", "Chinese", "Egyptian",
        "European", "Galapagos", "German", "Gila", "Greek", "Greenland", "Highland", "Himalayan",
        "Indian", "Japanese", "Kodiak", "Komodo", "Labrador", "Maasai", "Mongol", "Nile",
        "Norse", "Pacific", "Persian", "Roman", "Shetland", "Siberian", "Spartan", "Sumatran",
        "Tasmanian", "Viking", "Zulu",
    }
)  # fmt: skip


# Plural of a name's last word, always (no count, casing untouched): "gray wolf" -> "gray wolves".
def pluralize(entity: str) -> str:
    *head, last = entity.split(" ")
    if last in SINGULAR_TO_PLURAL:
        last = SINGULAR_TO_PLURAL[last]
    elif last in UNCHANGED:
        pass
    elif last.endswith(("s", "x", "ch", "sh")):
        last += "es"
    elif len(last) > 1 and last.endswith("y") and last[-2] not in "aeiou":
        last = last[:-1] + "ies"
    else:
        last += "s"
    return " ".join([*head, last])


# A fighter's name said after a count: "Gray wolf" -> "gray wolves", or "gray wolf" for one.
def counted_name(name: str, count: int) -> str:
    """Lower-case the first letter of an ordinary name ("Gorilla"), keep "T. rex" or "TV" as is,
    keep a proper first word such as "African" or "Roman" (PROPER_FIRST_WORDS) capitalized,
    and pluralize (see `pluralize`) only when the count is not 1."""
    proper = name.split(" ", 1)[0] in PROPER_FIRST_WORDS
    noun = name[:1].lower() + name[1:] if name[1:2].islower() and not proper else name
    return noun if count == 1 else pluralize(noun)
