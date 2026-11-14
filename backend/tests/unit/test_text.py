"""The shared pluralizer and its word tables (app/text.py, #258, #271)."""

import ast
from pathlib import Path

import pytest

import app.text
from app.intake.rules import singular_word
from app.text import IRREGULAR_PLURALS, counted_name, pluralize


# Names ending in f or fe take -ves again, as the old fair-fight helper did (#271).
@pytest.mark.parametrize(
    ("singular", "plural"),
    [
        ("half", "halves"),
        ("shelf", "shelves"),
        ("self", "selves"),
        ("wharf", "wharves"),
        ("scarf", "scarves"),
        ("wolf", "wolves"),
        ("knife", "knives"),
        ("elf", "elves"),
        ("dwarf", "dwarves"),  # decided in #271: "dwarves", as before #258
    ],
)
def test_f_words_take_ves(singular, plural):
    assert pluralize(singular) == plural
    assert pluralize(f"stone {singular}") == f"stone {plural}"
    assert singular_word(plural) == singular  # intake reads the same table back


def test_chief_stays_chiefs():
    # "chief" is not an f-to-ves word; the old documented form "chiefs" stays (#271).
    assert pluralize("chief") == "chiefs"
    assert counted_name("Chief", 2) == "chiefs"
    assert counted_name("chief", 1) == "chief"


def test_counted_name_uses_ves_after_a_count():
    assert counted_name("Dwarf", 3) == "dwarves"
    assert counted_name("Wharf", 2) == "wharves"
    assert counted_name("Dwarf", 1) == "dwarf"


def test_both_dwarf_plurals_still_read_as_one_dwarf():
    assert singular_word("dwarfs") == "dwarf"
    assert singular_word("dwarves") == "dwarf"


def test_every_irregular_singular_pluralizes_to_one_of_its_listed_plurals():
    for singular in set(IRREGULAR_PLURALS.values()):
        listed = {p for p, s in IRREGULAR_PLURALS.items() if s == singular}
        assert pluralize(singular) in listed, singular


def test_the_shared_tables_do_not_import_intake():
    """simulation and narration use app.text; it must not pull in app.intake (#271)."""
    tree = ast.parse(Path(app.text.__file__).read_text(encoding="utf-8"))
    imported = [
        node.module if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    ]
    assert not any(name and name.startswith("app.intake") for name in imported)
