"""Safety code rules (A04 layer 1): block clear cases before any model is called.

Pure: no providers, no settings. The word lists live in blocklist.yaml. These rules only catch
clear cases (toddlers, "the French", "my brother", "end my life", "plans to attack a shopping
mall"); everything else goes to the classifier, so a rule here must never block an animal or an
archetype ("German shepherd", "baby elephant") or ordinary fight wording ("the bear attacks").
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from app.intake.rules import UNITS, singular_word
from app.safety.verdict import ALLOWED, SafetyVerdict, blocked

BLOCKLIST_PATH = Path(__file__).with_name("blocklist.yaml")
# Words that separate sides, or fighters within a side, for these rules.
SIDE_BREAK = re.compile(r"\s+(?:vs\.?|versus|v\.|against|and|&|plus)\s+|\s*[,;/+]\s*")
# A side ends at a place or company phrase: "a baby in the snow" -> "a baby".
TAIL = re.compile(r"\s+(?:in|on|at|inside|near|under|atop|during|with|from|riding)\s+.*$")
# "6 year old", "twenty five years old" (hyphens already turned into spaces) at a side's end;
# group 1 is an optional tens word, group 2 the number.
AGE = re.compile(r"(?:\b([a-z]+)\s+)?\b(\d{1,3}|[a-z]+)\s+(?:year|yr)s?\s+olds?$")
# Curly and modifier apostrophes as a plain one, so "don’t" is not read as "don t".
APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'"})


@dataclass(frozen=True)
class Blocklist:
    """blocklist.yaml as sets, one per kind of rule."""

    minor_anywhere: frozenset[str]
    minor_head: frozenset[str]
    max_age: int
    group_head: frozenset[str]
    people_words: frozenset[str]
    self_words: frozenset[str]
    owners: frozenset[str]
    relations: frozenset[str]
    self_harm: frozenset[str] = frozenset()
    religious_figures: frozenset[str] = frozenset()
    hate_groups: frozenset[str] = frozenset()
    attack_ask: frozenset[str] = frozenset()
    attack: re.Pattern[str] = re.compile(r"(?!)")
    """A harm word, then within four words a target not followed by "of" (on _clean text)."""
    attack_person: re.Pattern[str] = re.compile(r"(?!)")
    """A direct ask, a harm word, then within two words a person target (on _clean text)."""
    subject_starts: frozenset[str] = frozenset()
    subject_modals: frozenset[str] = frozenset()
    subject_after: frozenset[str] = frozenset()
    not_fighters: frozenset[str] = frozenset()
    ask_opener: re.Pattern[str] = re.compile(r"(?!)")
    """An ask phrase and its comma at the start of the text, see strip_ask_opener (#344)."""


# Phrases as one regex alternative, longest first, each as whole words.
def _alternatives(phrases: frozenset[str]) -> str:
    return "|".join(re.escape(p) for p in sorted(phrases, key=len, reverse=True))


# The attack-planning pattern from its harm and target lists.
def _attack_pattern(harm: frozenset[str], targets: frozenset[str]) -> re.Pattern[str]:
    return re.compile(
        rf"\b(?:{_alternatives(harm)})\b(?:\s+[a-z0-9']+){{0,4}}?\s+"
        rf"(?:{_alternatives(targets)})\b(?!\s+of\b)"
    )


# The person-target pattern: "how to poison someone", "help me hurt somebody".
def _attack_person_pattern(
    asks: frozenset[str], harm: frozenset[str], targets: frozenset[str]
) -> re.Pattern[str]:
    return re.compile(
        rf"\b(?:{_alternatives(asks)})\s+(?:{_alternatives(harm)})"
        rf"(?:\s+[a-z0-9']+){{0,2}}?\s+(?:{_alternatives(targets)})\b"
    )


# Read blocklist.yaml once.
@cache
def load_blocklist() -> Blocklist:
    data = yaml.safe_load(BLOCKLIST_PATH.read_text(encoding="utf-8"))

    def words(section: str, key: str) -> frozenset[str]:
        return frozenset(_clean(str(w)) for w in data[section][key])

    return Blocklist(
        minor_anywhere=words("minor", "anywhere"),
        minor_head=words("minor", "head"),
        max_age=int(data["minor"]["max_age"]),
        group_head=words("group_of_people", "head"),
        people_words=words("group_of_people", "people_words"),
        self_words=words("real_person", "self_words"),
        owners=words("real_person", "owners"),
        relations=words("real_person", "relations"),
        self_harm=words("self_harm", "anywhere"),
        religious_figures=words("religious_figure", "anywhere"),
        hate_groups=words("hate_group", "anywhere"),
        attack_ask=words("attack_planning", "ask"),
        attack=_attack_pattern(
            words("attack_planning", "harm"), words("attack_planning", "targets")
        ),
        attack_person=_attack_person_pattern(
            words("attack_planning", "direct_ask"),
            words("attack_planning", "harm"),
            words("attack_planning", "person_targets"),
        ),
        subject_starts=words("attack_planning", "subject_starts"),
        subject_modals=words("attack_planning", "subject_modals"),
        subject_after=words("attack_planning", "subject_after"),
        not_fighters=_not_fighters(words),
        ask_opener=re.compile(
            rf"^\s*(?:please\s+)?(?:{_alternatives(words('real_person', 'ask_openers'))})\s*,\s*",
            re.IGNORECASE,
        ),
    )


# Subject words that are never a fighter: the not_fighters list plus every people list above.
def _not_fighters(words: Callable[[str, str], frozenset[str]]) -> frozenset[str]:
    return (
        words("attack_planning", "not_fighters")
        | words("minor", "head")
        | words("minor", "anywhere")
        | words("group_of_people", "head")
        | words("group_of_people", "people_words")
        | words("real_person", "relations")
    )


# Lowercase words with hyphens as spaces and straight apostrophes: "Six-Year-Old" -> "six year
# old", "don’t" -> "don't", "my self" -> "myself".
def _clean(text: str) -> str:
    text = text.lower().replace("-", " ").translate(APOSTROPHES)
    words = " ".join(re.sub(r"[^a-z0-9' ]+", " ", text).split())
    return re.sub(r"\bmy self\b", "myself", words)


# The text without an ask phrase and its comma at the start: "help me, a lion vs a goose" -> "a
# lion vs a goose" (#344). Without the comma it is left alone, so "help me vs a goose" still
# reads "me" as a fighter, and "help me, me vs a goose" still has its "me" side.
def strip_ask_opener(text: str, lists: Blocklist) -> str:
    return lists.ask_opener.sub("", text, count=1)


# The text's sides, each cut before its place phrase: "a toddler vs a goose in a pond" -> 2.
def sides(text: str) -> list[list[str]]:
    lowered = text.lower().replace("-", " ")
    found = []
    for part in SIDE_BREAK.split(lowered):
        words = _clean(TAIL.sub("", part.strip())).split()
        if words:
            found.append(words)
    return found


# True if a word, or its singular, is in the set.
def _in(word: str, vocabulary: frozenset[str]) -> bool:
    return word in vocabulary or singular_word(word) in vocabulary


# An age phrase at the end of a side, as a number: "a six year old" -> 6, "twenty five" -> 25.
def _head_age(words: list[str]) -> int | None:
    match = AGE.search(" ".join(words))
    if match is None:
        return None
    tens, token = match.group(1), match.group(2)
    if token.isdigit():
        return int(token)
    if token not in UNITS:
        return None
    return UNITS[token] + (UNITS[tens] if UNITS.get(tens or "", 0) >= 20 else 0)


# Phrases from a list found anywhere in the text, as whole words.
def _has_phrase(text: str, phrases: frozenset[str]) -> bool:
    padded = f" {_clean(text)} "
    return any(f" {phrase} " in padded for phrase in phrases)


# The verdict for one side's words (head-noun rules).
def _check_side(words: list[str], lists: Blocklist) -> SafetyVerdict:
    head = words[-1]
    age = _head_age(words)
    if _in(head, lists.minor_head) or (age is not None and age <= lists.max_age):
        return blocked("minor", "rules")
    if len(words) <= 2 and head in lists.self_words:
        return blocked("real_person", "rules")
    if _in(head, lists.group_head):
        return blocked("hate", "rules")
    if _in(head, lists.people_words) and any(_in(w, lists.group_head) for w in words[:-1]):
        return blocked("hate", "rules")
    return ALLOWED


# "my brother", "your little sister": someone the user knows.
def _names_someone_known(text: str, lists: Blocklist) -> bool:
    words = _clean(text).split()
    for index, word in enumerate(words):
        if word in lists.owners:
            following = words[index + 1 : index + 3]  # allow one describing word in between
            if any(_in(w, lists.relations) for w in following):
                return True
    return False


# True when the text asks for real-world attack planning: an ask word ("step by step", "how to")
# and a harm word followed by a real-world target ("attack a shopping mall"), both needed; or a
# direct ask right before harm to a person ("how to poison someone").
def _asks_for_attack_plans(text: str, lists: Blocklist) -> bool:
    cleaned = _clean(text)
    if lists.attack_person.search(cleaned):
        return True
    return _has_phrase(text, lists.attack_ask) and _harms_a_target(cleaned, lists)


# True when some harm word before a real-world target is not a fighter's action: "plans to attack
# a mall" counts, "how a lion would attack a restaurant" doesn't (#317). Tries every harm word.
def _harms_a_target(cleaned: str, lists: Blocklist) -> bool:
    position = 0
    while match := lists.attack.search(cleaned, position):
        if not _fighter_is_subject(cleaned[: match.start()].split(), lists):
            return True
        position = match.start() + 1
    return False


# True when the words end in an ask phrase from the attack_planning ask list ("step by step").
def _ends_with_ask(words: list[str], lists: Blocklist) -> bool:
    return any(
        words[-len(phrase.split()) :] == phrase.split() for phrase in lists.attack_ask if words
    )


# True when the words before a harm word end in "<modal> <fighter>" or "<lead> <fighter> <modal>",
# where the lead is "how", the start of the request, or an ask phrase: "how a lion would", "step
# by step: a wolf would", "a wolf would", "would 6 wolves"; not if a subject word is a person or
# pronoun ("how a terrorist would", "would i"), or the subject is part of a longer phrase ("with a
# gun would"). A subject of four or more words ("a very angry unemployed pilot") is not read as a
# fighter, so it fails safe and still blocks; the limit stays at three words on purpose.
def _fighter_is_subject(before: list[str], lists: Blocklist) -> bool:
    modal_last = bool(before) and before[-1] in lists.subject_modals
    words = before[:-1] if modal_last else before
    for size in (1, 2, 3):
        if len(words) < size + 1:
            break
        opener, nouns, lead_words = words[-size - 1], words[-size:], words[: -size - 1]
        lead = lead_words[-1] if lead_words else ""
        led = lead in lists.subject_modals or (
            modal_last
            and (not lead_words or lead in lists.subject_after or _ends_with_ask(lead_words, lists))
        )
        is_start = opener in lists.subject_starts or opener.isdigit()
        if led and is_start and not any(_in(w, lists.not_fighters) for w in nouns):
            return True
    return False


# Layer 1 on any text (the whole request, or one side's raw or entity): clear cases only.
# Self-harm comes first, so its message (with the crisis line) wins over any other reason.
def check_text_rules(text: str) -> SafetyVerdict:
    lists = load_blocklist()
    if _has_phrase(text, lists.self_harm):
        return blocked("self_harm", "rules")
    if _has_phrase(text, lists.minor_anywhere):
        return blocked("minor", "rules")
    if _names_someone_known(text, lists):
        return blocked("real_person", "rules")
    if _has_phrase(text, lists.religious_figures):  # a living religion's figure (D-69)
        return blocked("deity", "rules")
    if _has_phrase(text, lists.hate_groups):  # never a "military unit" (D-69, #523 review)
        return blocked("hate", "rules")
    for words in sides(strip_ask_opener(text, lists)):
        verdict = _check_side(words, lists)
        if not verdict.allowed:
            return verdict
    if _asks_for_attack_plans(text, lists):
        return blocked("other", "rules")
    return ALLOWED


# Layer 1 on a model-written variant ("adult male", "baby"): only words that block anywhere, since
# a variant describes its entity ("baby" elephant, "French" bulldog) rather than naming a side.
def check_variant_rules(variant: str | None) -> SafetyVerdict:
    lists = load_blocklist()
    if variant and _has_phrase(variant, lists.minor_anywhere):
        return blocked("minor", "rules")
    if variant and _names_someone_known(variant, lists):
        return blocked("real_person", "rules")
    return ALLOWED
