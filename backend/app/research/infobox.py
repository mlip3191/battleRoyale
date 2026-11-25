"""Read a Wikipedia article's infobox rows with code (#522): "Weight: 25–34 kg" becomes a number.

The infobox is the article's own summary table. A row whose label names a stat (mass, weight,
length, height, speed) gives one number and its unit, with the row's text as its quote, so the
number and unit are in the quote by construction; no model reads these rows.
"""

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from app.models.stats import StatName
from app.research.evidence_check import NUMBER, normalize_text, number_has_unit_in_quote
from app.research.units import UnitError, to_stat_unit

# Row labels that name a stat -> the fact's field (named like facts.PROPERTIES' values).
LABELS = {
    "mass": "mass",
    "weight": "mass",
    "length": "length",
    "height": "height",
    "speed": "speed",
    "top speed": "speed",
    "maximum speed": "speed",
}
FIELD_STATS = {
    "mass": StatName.MASS,
    "length": StatName.SIZE,
    "height": StatName.SIZE,
    "speed": StatName.SPEED,
}
# A number, an optional range end ("25-34"), then its unit ("kg", "km/h"), in normalized text.
MEASURE = re.compile(
    rf"({NUMBER.pattern})(?:\s*(?:-|to)\s*({NUMBER.pattern}))?(?:\s*|-)([A-Za-z]+(?:/[A-Za-z]+)?)"
)
# The same limit extraction puts on a model's quote (extract.MAX_QUOTE_CHARS).
MAX_QUOTE_CHARS = 300
FOOTNOTE = re.compile(r"\[[^\]]*\]")


@dataclass(frozen=True)
class StatRow:
    """One infobox row that names a stat, read by code."""

    field: str
    """What it measures: "mass", "length", "height" or "speed"."""
    value: float
    """The number as the row writes it (a range's upper figure), in `unit`."""
    unit: str
    quote: str
    """The row's text, label first: "Weight: 25–34 kg (55–75 lb)"."""
    row: int
    """Its place among the infobox's rows, from 1."""


class _Rows(HTMLParser):
    """Collects (label, data cells) for every infobox row; footnotes and styles are skipped."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[str, list[str]]] = []
        self._skip: tuple[str, int] | None = None  # the skipped element's tag, and its depth
        self._label: list[str] | None = None
        self._in_label = False
        self._cells: list[str] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if self._skip is not None:
            if tag == self._skip[0]:
                self._skip = (tag, self._skip[1] + 1)
        elif tag in ("style", "script") or "reference" in classes:
            self._skip = (tag, 1)
        elif tag == "tr":
            self._label, self._cells, self._cell = None, [], None
        elif tag == "th" and "infobox-label" in classes:
            self._label, self._in_label = [], True
        elif tag == "td" and any(c.startswith("infobox-data") for c in classes):
            self._cell = []
        elif tag in ("br", "li") and self._cell is not None:
            self._cell.append(" ")  # a line break or list item reads as a space

    def handle_endtag(self, tag: str) -> None:
        if self._skip is not None:
            if tag == self._skip[0]:
                self._skip = None if self._skip[1] == 1 else (tag, self._skip[1] - 1)
        elif tag == "th":
            self._in_label = False
        elif tag == "td" and self._cell is not None:
            self._cells.append("".join(self._cell))
            self._cell = None
        elif tag == "tr" and self._label is not None and self._cells:
            self.rows.append(("".join(self._label), self._cells))
            self._label = None

    def handle_data(self, data: str) -> None:
        if self._skip is not None:
            return
        if self._cell is not None:
            self._cell.append(data)
        elif self._in_label and self._label is not None:
            self._label.append(data)


# Text as it reads on the page: footnote marks dropped, spaces (and no-break spaces) collapsed.
def _clean(text: str) -> str:
    return " ".join(FOOTNOTE.sub("", text).replace("\xa0", " ").split())


# Every infobox row as (label, row text). A row with an empty label continues the one above it
# ("Height: Males ..." then "Females ..."), so it takes that row's label.
def infobox_rows(html: str) -> list[tuple[str, str]]:
    parser = _Rows()
    parser.feed(html)
    rows, last = [], ""
    for label, cells in parser.rows:
        label = _clean(label).rstrip(":") or last
        last = label
        data = _clean(" ".join(cells))
        if label and data:
            rows.append((label, f"{label}: {data}"))
    return rows


# The row's first number with a unit this stat converts from: the upper end of a range
# (docs/research.md prefers the upper figure), with the unit as written.
def row_measure(text: str, stat: StatName) -> tuple[float, str] | None:
    for match in MEASURE.finditer(normalize_text(text)):
        written = (match.group(2) or match.group(1)).replace(",", "")
        value, unit = float(written), match.group(3)
        try:
            to_stat_unit(value, unit, stat)
        except UnitError:
            continue
        return value, unit
    return None


# The article's infobox rows that name a stat, each with its number. A row whose number and unit
# don't pass extraction's own quote check is left out.
def stat_rows(html: str) -> list[StatRow]:
    found = []
    for n, (label, quote) in enumerate(infobox_rows(html), start=1):
        field = LABELS.get(label.lower())
        if field is None or len(quote) > MAX_QUOTE_CHARS:
            continue
        measure = row_measure(quote, FIELD_STATS[field])
        if measure is None or not number_has_unit_in_quote(*measure, quote):
            continue
        found.append(StatRow(field, measure[0], measure[1], quote, n))
    return found
