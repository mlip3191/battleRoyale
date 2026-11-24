"""The 30 seed fighters, read from data/seed/fighters.yaml, and their hand-verified sheets."""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import REPO_ROOT
from app.models.stats import StatSheet

SEED_LIST_PATH = REPO_ROOT / "data" / "seed" / "fighters.yaml"
SEED_SHEETS_DIR = REPO_ROOT / "data" / "seed" / "fighters"


@dataclass(frozen=True)
class SeedFighter:
    """One row of the seed list in docs/research.md."""

    id: str
    display_name: str
    variant: str
    category: str
    body: str
    habitat: str
    article: str
    # Pinned so a vandalized or changed Wikidata name can't break the trait match (#290).
    scientific_name: str | None = None


# Read the seed list.
def load_seed_fighters(path: Path = SEED_LIST_PATH) -> list[SeedFighter]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [SeedFighter(**row) for row in data["fighters"]]


# Turn a fighter name into its id: "Grizzly Bear" -> "grizzly-bear".
def fighter_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# Other spellings and word forms the seed lookup should treat as the sheet's word.
# Add a word here when a new seed sheet needs another spelling or plural.
_ALIASES = {
    "grey": "gray",
    "wolves": "wolf",
    "ducks": "duck",
    "mice": "mouse",  # irregular plurals of default kinds (#168 review)
    "cacti": "cactus",
}


# Common names that are a seed fighter's id, not one of its words (#415). They are matched as the
# whole name: a word-by-word alias would turn "king cobra" into "king-king-cobra".
_NAME_ALIASES = {
    "hippo": "hippopotamus",
    "hippos": "hippopotamus",
    "cobra": "king-cobra",
    "cobras": "king-cobra",
    "t-rex": "tyrannosaurus-rex",
    "t-rexes": "tyrannosaurus-rex",
    "trex": "tyrannosaurus-rex",
    "trexes": "tyrannosaurus-rex",
    "tyrannosaurus": "tyrannosaurus-rex",
}


# Words that may stand around a bare kind in the user's own phrase without naming a kind: articles,
# numbers, group words, size words, possessives and plain adjectives. "a big bear" or "my fierce
# bear" is still just a bear; "a polar bear" is not. The list is closed: a word that is not on it
# counts as naming a kind (add a word here when a plain one turns up).
_FILLER_WORDS = {
    *("a", "an", "the", "some", "many", "few", "several", "of", "pack", "herd", "flock"),
    *("swarm", "school", "group", "pair", "couple", "dozen", "hundred", "thousand", "million"),
    *("big", "small", "large", "little", "huge", "giant", "tiny", "angry", "young", "old"),
    *("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"),
    *("eleven", "twelve", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty"),
    *("thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"),
    *("bunch", "troop", "trio", "pride", "dozens", "hundreds", "thousands", "lots", "both", "all"),
    *("ninety", "my", "your", "his", "her", "our", "their", "lone", "wild", "adult", "mature"),
    *("fierce", "hungry", "mean", "strong", "fast", "scary", "tough", "mighty", "grumpy", "deadly"),
    *("venomous", "poisonous", "dangerous", "hairy", "fat", "tall", "short", "ordinary", "normal"),
}


# When a user names a kind without saying which one, code picks the most familiar seed fighter
# of that kind (#168). This copies the "Default variants" table in docs/research.md, and a test
# keeps the two identical, so the choice is a written rule, never a model's guess.
DEFAULT_KINDS: dict[str, str] = {
    "bear": "grizzly-bear",
    "shark": "great-white-shark",
    "wolf": "gray-wolf",
    "eagle": "bald-eagle",
    "cat": "house-cat",
    "dog": "golden-retriever",
    "elephant": "african-elephant",
    "crocodile": "saltwater-crocodile",
    "snake": "king-cobra",
    "bee": "honey-bee",
    "ant": "army-ant",
    "mouse": "house-mouse",
    "tank": "main-battle-tank",
    "truck": "pickup-truck",
    "cactus": "saguaro-cactus",
    # The last word of a seed name is a bare kind too (#455): "a lion" is the African lion.
    "lion": "african-lion",
    "badger": "honey-badger",
    "knight": "medieval-knight",
    "legionary": "roman-legionary",
    "retriever": "golden-retriever",
}


# The default fighter's id for a bare kind ("bear", "bears", "wolves"), or None. Only when no
# kind was given: "polar bear", "bear" with a variant, or "bear" with "a polar bear" in the user's
# own words (`raw`), is never replaced by a default (#415).
def default_kind(entity: str, variant: str | None = None, raw: str | None = None) -> str | None:
    if (variant or "").strip() or _raw_names_a_kind(entity, raw):
        return None
    slug = _canonical_slug(entity)
    if slug in DEFAULT_KINDS:
        return DEFAULT_KINDS[slug]
    singular = slug[:-1] if slug.endswith("s") else None  # "bears", "sharks"
    if singular and singular in DEFAULT_KINDS:
        return DEFAULT_KINDS[singular]
    ies = slug[:-3] + "y" if slug.endswith("ies") else None  # "legionaries"
    return DEFAULT_KINDS.get(ies) if ies else None


# A trailing place phrase ("in a forest", "on the ice") that rides along in a side's exact words
# when the battlefield comes last. It is not a kind of fighter.
_PLACE_TAIL = re.compile(r"\s+(?:in|on|at|inside|into)\s+.*$", re.IGNORECASE)
_POSSESSIVE = re.compile(r"['’]s\b", re.IGNORECASE)


# The words of a side that can name a kind: without a trailing place phrase or a possessive "'s".
def _side_words(raw: str | None) -> str:
    return _POSSESSIVE.sub("", _PLACE_TAIL.sub("", (raw or "").strip()))


# True when the user's phrase has a word besides the entity, an article, a number or a size word,
# so a kind was named ("a polar bear" for the entity "bear"). A phrase that does not contain the
# entity at all describes something else and names no kind of it.
def _raw_names_a_kind(entity: str, raw: str | None) -> bool:
    raw = _side_words(raw)
    if not raw:
        return False
    entity_words = {w for part in _canonical_slug(entity).split("-") for w in (part, part + "s")}
    words = _canonical_slug(raw).split("-")
    if not entity_words & set(words):
        return False  # the phrase does not describe this entity, so it names no kind of it
    for word in words:
        if not word or word.isdigit() or word in _FILLER_WORDS or word in entity_words:
            continue
        if not (word.endswith("s") and word[:-1] in entity_words):
            return True
    return False


# The kind the user named around a bare entity, in their own spelling: "polar" for the entity
# "bear" and the phrase "2 polar bears", or None when the phrase names no kind (#415). Intake
# keeps it as the variant, so the fighter reads "polar bear" instead of a bare "bear".
def named_kind_words(entity: str, raw: str | None) -> str | None:
    if not _raw_names_a_kind(entity, raw):
        return None
    entity_words = {w for part in _canonical_slug(entity).split("-") for w in (part, part + "s")}
    kept = []
    # Words start with a letter and may hold digits, so "m1" stays "m1", not "m" (#561).
    for word in re.findall(r"[A-Za-z][A-Za-z0-9]*", _side_words(raw)):
        low = _canonical_slug(word)
        plural_of_entity = low.endswith("s") and low[:-1] in entity_words
        if low and low not in _FILLER_WORDS and low not in entity_words and not plural_of_entity:
            kept.append(word.lower())
    return " ".join(kept) or None


def _canonical_slug(name: str) -> str:
    """Slug a name, then map known alternate spellings to the sheet's word."""
    whole = fighter_slug(name)
    if whole in _NAME_ALIASES:
        return _NAME_ALIASES[whole]
    parts = [_ALIASES.get(part, part) for part in fighter_slug(name).split("-") if part]
    return "-".join(parts)


# The hand-verified sheet for a fighter, or None when there is no seed sheet for it.
# Live intake may put a descriptive word in variant ("grizzly" + "bear"), or drop it
# from both fields and leave it only in raw ("a grizzly bear" + entity "bear").
# Mock intake keeps the full name as entity and a label like "adult male" as variant.
# Try variant plus entity first, then the entity alone, then a unique seed sheet
# whose last slug part is the entity and whose other parts all appear in raw, so a
# variant-specific sheet wins when one exists and raw-only descriptors still match.
# Gunnar's G04 get_stat_sheet will wrap or replace this lookup.
# Only slugs of [a-z0-9-] are used, so this can only read files in sheets_dir.
def find_seed_sheet(
    entity: str,
    variant: str | None = None,
    raw: str | None = None,
    *,
    sheets_dir: Path = SEED_SHEETS_DIR,
) -> StatSheet | None:
    names: list[str] = []
    kind = (variant or "").strip()
    if kind:
        names.append(f"{kind} {entity}")
    names.append(entity)
    for name in names:
        sheet = _sheet_at(_canonical_slug(name), sheets_dir)
        if sheet is not None:
            return sheet
    sheet = _sheet_from_raw(entity, raw, sheets_dir)
    if sheet is not None:
        return sheet
    default = default_kind(entity, variant, raw)
    return None if default is None else _sheet_at(default, sheets_dir)


def _sheet_at(slug: str, sheets_dir: Path) -> StatSheet | None:
    if not slug or re.search(r"[^a-z0-9-]", slug):
        return None
    path = sheets_dir / f"{slug}.json"
    if not path.is_file():
        return None
    return StatSheet.model_validate_json(path.read_text(encoding="utf-8"))


# Unique seed sheet for a live-style raw phrase: "6 gray wolves" + entity "wolf"
# finds gray-wolf; the aliases map "wolves" to "wolf". A vague phrase
# like "a bear" matches no unique sheet (the prefix is not in the phrase).
def _sheet_from_raw(entity: str, raw: str | None, sheets_dir: Path) -> StatSheet | None:
    try:
        entries = list(sheets_dir.iterdir())
    except OSError:
        return None
    slugs = [p.stem for p in entries if p.suffix == ".json" and p.is_file()]
    slug = _unique_raw_match(entity, raw, slugs)
    return None if slug is None else _sheet_at(slug, sheets_dir)


# The one slug whose last word is the entity and whose other words all appear in raw, or None.
def _unique_raw_match(entity: str, raw: str | None, slugs: list[str]) -> str | None:
    if not raw or not raw.strip():
        return None
    entity_slug = _canonical_slug(entity)
    if not entity_slug:
        return None
    raw_tokens = {part for part in _canonical_slug(raw).split("-") if part and not part.isdigit()}
    matches: list[str] = []
    for slug in slugs:
        if not slug or re.search(r"[^a-z0-9-]", slug):
            continue
        parts = slug.split("-")
        if len(parts) < 2 or parts[-1] != entity_slug:
            continue
        if all(part in raw_tokens for part in parts[:-1]):
            matches.append(slug)
            if len(matches) > 1:
                return None
    return matches[0] if len(matches) == 1 else None


# The seed-list fighter a request names, tried like find_seed_sheet: "variant entity", then
# entity, then a unique match in raw. None for names not on the seed list.
def find_seed_fighter(
    entity: str, variant: str | None = None, raw: str | None = None
) -> SeedFighter | None:
    fighters = {f.id: f for f in load_seed_fighters()}
    by_name = {**{_canonical_slug(f.display_name): f for f in fighters.values()}, **fighters}
    kind = (variant or "").strip()
    for name in ([f"{kind} {entity}"] if kind else []) + [entity]:
        found = by_name.get(_canonical_slug(name))
        if found is not None:
            return found
    slug = _unique_raw_match(entity, raw, list(fighters)) or default_kind(entity, variant, raw)
    return None if slug is None else fighters.get(slug)


# Names that keep their capital in the middle of a sentence ("the African elephant").
_PROPER_WORDS = {"African", "Roman"}


# The default fighter research will use for a bare kind, or None when the request names a
# fighter more exactly (an exact name, a variant, or raw text such as "6 gray wolves").
def picked_default(
    entity: str, variant: str | None = None, raw: str | None = None
) -> SeedFighter | None:
    slug = default_kind(entity, variant, raw)
    if slug is None:
        return None
    fighters = {f.id: f for f in load_seed_fighters()}
    if _canonical_slug(entity) in fighters or _unique_raw_match(entity, raw, list(fighters)):
        return None
    return fighters.get(slug)


# A display name as it reads mid-sentence: "Grizzly bear" -> "grizzly bear".
def spoken_name(display_name: str) -> str:
    first = display_name.split(" ", 1)[0]
    return display_name if first in _PROPER_WORDS else display_name[:1].lower() + display_name[1:]
