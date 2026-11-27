"""#522 part 1: an infobox row gives its upper figure and unit, quoted as the row reads."""

from hypothesis import given
from hypothesis import strategies as st

from app.research.infobox import stat_rows

UNITS = {"Mass": ["kg", "lb", "g", "tonnes"], "Length": ["m", "cm", "ft"], "Top speed": ["km/h"]}
NUMBERS = st.decimals(min_value="0.1", max_value="9999", places=1)
# What may sit before the number ("~25 kg", "c. 25 kg") and the footnotes after its unit.
BEFORE = ["", "~", "c. ", "about "]
FOOTNOTES = ["", "[1]", '<sup class="reference"><a>[2]</a></sup>']


@given(
    label=st.sampled_from(sorted(UNITS)),
    low=NUMBERS,
    span=NUMBERS,
    pick=st.integers(min_value=0, max_value=3),
    ranged=st.booleans(),
    unit_on_both_ends=st.booleans(),
    dash=st.sampled_from(["–", "-", " to "]),
    before=st.sampled_from(BEFORE),
    footnote=st.sampled_from(FOOTNOTES),
)
def test_the_fact_is_the_rows_upper_figure_with_its_unit_as_the_row_reads(
    label, low, span, pick, ranged, unit_on_both_ends, dash, before, footnote
) -> None:
    unit = UNITS[label][pick % len(UNITS[label])]
    high = low + span
    first = f"{low:,}\xa0{unit}" if unit_on_both_ends else f"{low:,}"
    shown = f"{first}{dash}{high:,}" if ranged else f"{high:,}"
    html = (
        f'<table class="infobox"><tr><th class="infobox-label">{label}</th>'
        f'<td class="infobox-data">{before}{shown}\xa0{unit}{footnote} (approx.)</td></tr></table>'
    )
    rows = stat_rows(html)
    assert len(rows) == 1
    row = rows[0]
    assert row.value == float(high) and row.unit == unit
    # The quote is the row as a reader sees it: the upper figure next to its unit, no footnote.
    assert row.quote == f"{label}: {before}{shown.replace(chr(0xA0), ' ')} {unit} (approx.)"
    assert f"{high:,} {unit}" in row.quote
