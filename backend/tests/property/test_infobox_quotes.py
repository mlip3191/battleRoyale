"""#522 part 1: an infobox row's number passes extraction's own quote check by construction."""

from hypothesis import given
from hypothesis import strategies as st

from app.research.evidence_check import evidence_is_valid, number_has_unit_in_quote
from app.research.infobox import stat_rows

UNITS = {"Mass": ["kg", "lb", "g", "tonnes"], "Length": ["m", "cm", "ft"], "Top speed": ["km/h"]}
NUMBERS = st.decimals(min_value="0.1", max_value="9999", places=1)


@given(
    label=st.sampled_from(sorted(UNITS)),
    low=NUMBERS,
    span=NUMBERS,
    pick=st.integers(min_value=0, max_value=3),
    ranged=st.booleans(),
    dash=st.sampled_from(["–", "-", " to "]),
)
def test_the_fact_is_the_rows_upper_figure_and_its_quote_holds_it(
    label, low, span, pick, ranged, dash
) -> None:
    unit = UNITS[label][pick % len(UNITS[label])]
    high = low + span
    shown = f"{low:,}{dash}{high:,}" if ranged else f"{high:,}"
    html = (
        f'<table class="infobox"><tr><th class="infobox-label">{label}</th>'
        f'<td class="infobox-data">{shown}\xa0{unit} (approx.)</td></tr></table>'
    )
    rows = stat_rows(html)
    assert len(rows) == 1
    row = rows[0]
    assert row.value == float(high) and row.unit == unit
    assert evidence_is_valid(row.value, row.quote, row.quote)
    assert number_has_unit_in_quote(row.value, row.unit, row.quote)
