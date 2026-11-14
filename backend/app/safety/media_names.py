"""Is a stat sheet's media_name safe to put in an image or music prompt? (ARCHITECTURE §11)

Pure: no providers, no settings. A safe name is short, uses only lowercase letters, digits,
single spaces, and hyphens (after lowercasing), and names no brand or franchise from
media_brands.yaml.
"""

import re
from functools import cache
from pathlib import Path

import yaml

BRANDS_PATH = Path(__file__).with_name("media_brands.yaml")
MAX_MEDIA_NAME = 48
MEDIA_NAME = re.compile(r"[a-z0-9]+(?:[ -][a-z0-9]+)*")


# The brand words and phrases, read once.
@cache
def _brands() -> tuple[frozenset[str], tuple[str, ...]]:
    data = yaml.safe_load(BRANDS_PATH.read_text(encoding="utf-8"))
    words = frozenset(str(w).lower() for w in data["words"])
    phrases = tuple(str(p).lower() for p in data["phrases"])
    return words, phrases


# The prompt-ready form of a media_name, or None when it may not be used in a prompt.
def safe_media_name(name: str) -> str | None:
    cleaned = name.strip().lower()
    if not cleaned or len(cleaned) > MAX_MEDIA_NAME or not MEDIA_NAME.fullmatch(cleaned):
        return None
    words, phrases = _brands()
    tokens = re.split(r"[ -]", cleaned)
    if any(token in words for token in tokens):
        return None
    padded = f" {' '.join(tokens)} "
    if any(f" {phrase} " in padded for phrase in phrases):
        return None
    return cleaned
