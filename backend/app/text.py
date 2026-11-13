"""Shared English wording helpers: fighter names after a count ("3 African elephants").

One pluralizer for the whole app (#258), used by intake, simulation (fair fight) and narration.
The word tables live here too (#271), so no module imports intake just to get them; intake's
singular_word (app/intake/rules.py) reads the same tables. Pure: no providers, settings or I/O.
"""

# Plural -> singular for words the suffix rules would get wrong. When two plurals share one
# singular ("dwarfs", "dwarves"), the LATER entry is the one pluralize uses: "dwarf" -> "dwarves".
IRREGULAR_PLURALS = {
    "wolves": "wolf", "geese": "goose", "mice": "mouse", "oxen": "ox", "men": "man",
    "women": "woman", "people": "person", "lice": "louse", "calves": "calf", "elves": "elf",
    "dwarfs": "dwarf", "dwarves": "dwarf", "hooves": "hoof", "knives": "knife",
    "leaves": "leaf", "loaves": "loaf", "thieves": "thief", "wives": "wife",
    "halves": "half", "shelves": "shelf", "selves": "self", "wharves": "wharf",
    "scarves": "scarf", "sheaves": "sheaf",
    "octopi": "octopus", "octopuses": "octopus", "cacti": "cactus", "cactuses": "cactus",
    "fungi": "fungus", "larvae": "larva", "walruses": "walrus", "platypuses": "platypus",
    "hippopotamuses": "hippopotamus", "hippopotami": "hippopotamus", "buses": "bus",
    "rhinoceroses": "rhinoceros", "mantises": "mantis", "ibises": "ibis",
    "buffaloes": "buffalo", "mosquitoes": "mosquito", "tomatoes": "tomato",
    "potatoes": "potato", "heroes": "hero", "volcanoes": "volcano", "teeth": "tooth",
    "feet": "foot", "dice": "die", "emus": "emu", "gnus": "gnu", "dingoes": "dingo",
    "flamingoes": "flamingo", "torpedoes": "torpedo", "echoes": "echo", "viruses": "virus",
    "zombies": "zombie", "pixies": "pixie", "genies": "genie", "cookies": "cookie",
    "collies": "collie", "magpies": "magpie", "budgies": "budgie", "yorkies": "yorkie",
    "movies": "movie", "brownies": "brownie", "rookies": "rookie", "goalies": "goalie",
}  # fmt: skip
# Words that are the same in singular and plural, or that only look plural.
UNCHANGED = {
    "moose", "deer", "sheep", "fish", "bison", "salmon", "trout", "shrimp", "squid", "species",
    "series", "aircraft", "swine", "cattle", "rhinoceros", "mercedes", "news", "chaos",
    "mantis", "ibis", "chassis", "atlas", "gas", "lens", "canvas", "triceratops", "cyclops",
}  # fmt: skip

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
