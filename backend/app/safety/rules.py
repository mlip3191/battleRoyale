"""Safety code rules (A04 layer 1): block clear human cases before any model is called.

Pure: no providers, no settings. The word lists live in blocklist.yaml. These rules only catch
clear cases (toddlers, "the French", "my brother"); everything else goes to the classifier, so a
rule here must never block an animal or an archetype ("German shepherd", "baby elephant").
"""

import re
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


# Read blocklist.yaml once.
@cache
def load_blocklist() -> Blocklist:
    data = yaml.safe_load(BLOCKLIST_PATH.read_text(encoding="utf-8"))

    def words(section: str, key: str) -> frozenset[str]:
        return frozenset(str(w).lower() for w in data[section][key])

    return Blocklist(
        minor_anywhere=words("minor", "anywhere"),
        minor_head=words("minor", "head"),
        max_age=int(data["minor"]["max_age"]),
        group_head=words("group_of_people", "head"),
        people_words=words("group_of_people", "people_words"),
        self_words=words("real_person", "self_words"),
        owners=words("real_person", "owners"),
        relations=words("real_person", "relations"),
    )


# Lowercase words with hyphens as spaces: "Six-Year-Old" -> "six year old".
def _clean(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", text.lower().replace("-", " ")).split())


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


# Layer 1 on any text (the whole request, or one side's raw or entity): clear human cases only.
def check_text_rules(text: str) -> SafetyVerdict:
    lists = load_blocklist()
    if _has_phrase(text, lists.minor_anywhere):
        return blocked("minor", "rules")
    if _names_someone_known(text, lists):
        return blocked("real_person", "rules")
    for words in sides(text):
        verdict = _check_side(words, lists)
        if not verdict.allowed:
            return verdict
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
