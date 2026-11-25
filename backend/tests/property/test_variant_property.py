"""#522 part 4: preferring the variant only ever drops figures, and another sex never empties."""

from hypothesis import given
from hypothesis import strategies as st

from app.research.variant import prefer_variant

WORDS = ["males", "females", "adult", "newborn", "lioness", "weighs", "kg"]
VARIANTS = ["Adult male", "Adult female", "Adult", "Adult bull, savanna", "Mature plant", None]
QUOTES = st.lists(st.sampled_from(WORDS), max_size=4).map(" ".join)


@given(variant=st.sampled_from(VARIANTS), quotes=st.lists(QUOTES, max_size=6))
def test_only_a_young_animals_figure_is_ever_lost(variant: str | None, quotes: list[str]) -> None:
    kept = prefer_variant(variant, quotes, lambda quote: (quote, ""))
    assert [q for q in quotes if q in kept] == kept  # a subset, in order
    adult = variant is not None and variant.startswith("Adult")
    usable = [q for q in quotes if not (adult and "newborn" in q and "adult" not in q)]
    assert bool(kept) == bool(usable)
