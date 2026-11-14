"""Keyword stand-in for the safety classifier, for mock mode only (#240).

This list is only the mock, for CI and offline demos (CLAUDE.md section 6). It is not the live
classifier: in live mode the chat model reads prompts/safety_classify.md and this file is never
used. It is not meant to be complete either, just enough obvious names that an offline demo
stays family-friendly and "Taylor Swift vs a goose" does not come back ok.

To add a word, put it under its reason in MOCK_BLOCKED_WORDS, lowercase and spelled as people
type it. Hyphens and spaces are treated the same ("ak-47" also matches "ak 47"), and a plain
"s" or "es" plural matches too. Matches are whole words only, so "thor" never fires on "a
thorny devil". Only add names that are never an animal, an object, or a machine: "tank",
"cannon", "sword", or a dog breed would block fighters the live classifier allows.
"""

import re

# Reason -> words, in the prompt's order of reasons (BlockedReason), so the first reason that
# applies wins when a request has several problems. Only the classifier's reasons appear here;
# minors, groups of people, and "me" / "my friend" are the code rules' job (app/safety/rules.py).
MOCK_BLOCKED_WORDS: dict[str, tuple[str, ...]] = {
    "real_person": (
        "napoleon",
        "taylor swift",
        "abraham lincoln",
        "george washington",
        "julius caesar",
        "genghis khan",
        "cleopatra",
        "albert einstein",
        "mike tyson",
        "elon musk",
    ),
    "copyrighted_character": (
        "batman",
        "superman",
        "spider-man",
        "spiderman",
        "the hulk",
        "godzilla",
        "king kong",
        "pikachu",
        "darth vader",
        "harry potter",
        "mickey mouse",
        "shrek",
    ),
    "deity": (
        "zeus",
        "odin",
        "thor",
        "poseidon",
        "hades",
        "anubis",
    ),
    "weapon": (
        "gun",
        "handgun",
        "pistol",
        "revolver",
        "rifle",
        "shotgun",
        "machine gun",
        "ak-47",
        "ak47",
        "ar-15",
        "ar15",
        "uzi",
        "glock",
        "grenade",
        "bomb",
        "dynamite",
        "bazooka",
        "rocket launcher",
    ),
}


# Lowercase words joined by single spaces: "an AK-47!" -> "an ak 47".
def _plain(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


# One whole-word pattern per reason, with an optional "s" / "es" plural on each word.
_PATTERNS: dict[str, re.Pattern[str]] = {
    reason: re.compile(
        r"\b(?:" + "|".join(re.escape(_plain(word)) for word in words) + r")(?:e?s)?\b"
    )
    for reason, words in MOCK_BLOCKED_WORDS.items()
}


# The first reason whose words appear in the text, or None when nothing on the list does.
def mock_block_reason(text: str) -> str | None:
    plain = _plain(text)
    for reason, pattern in _PATTERNS.items():
        if pattern.search(plain):
            return reason
    return None
