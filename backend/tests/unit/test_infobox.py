"""#522 part 1: code reads an article's infobox rows that name a stat, quoted word for word."""

from app.research.infobox import infobox_rows, stat_rows

NBSP = '<span typeof="mw:Entity">\xa0</span>'
# Rows as the Wikipedia HTML API writes them: a continuation row has an empty label, values use
# no-break spaces, and footnotes (which may hold a tag with no end tag) and template styles sit
# inside the cells.
DOG = f"""<table class="infobox biota"><tbody>
<tr><th scope="row" class="infobox-label">Other names</th><td class="infobox-data">
<ul><li>Flat-coated</li><li>Golden</li></ul></td></tr>
<tr><th scope="row" class="infobox-label">Height</th><td class="infobox-data infobox-data-a">
Males</td><td class="infobox-data infobox-data-b">56–61{NBSP}cm (22–24{NBSP}in)</td></tr>
<tr><th scope="row" class="infobox-label"></th><td class="infobox-data infobox-data-a">
Females</td><td class="infobox-data infobox-data-b">51–56{NBSP}cm (20–22{NBSP}in)</td></tr>
<tr><th scope="row" class="infobox-label">Weight</th><td colspan="3" class="infobox-data">
25–34{NBSP}kg (55–75{NBSP}lb)<sup class="reference"><img alt=""><a>[1]</a></sup></td></tr>
<tr><th scope="row" class="infobox-label">Litter size</th><td class="infobox-data">7.2±2.7
<style>.mw-parser-output .x{{width:1.25em}}</style></td></tr>
</tbody></table>"""
TANK = """<table class="infobox"><tbody>
<tr><th class="infobox-label">Mass</th><td class="infobox-data">62.3 tonnes (68.7 short tons)
</td></tr>
<tr><th class="infobox-label">Length</th><td class="infobox-data">9.83 m (32 ft 3 in) gun forward
</td></tr>
<tr><th class="infobox-label">Height</th><td class="infobox-data">2.44 m (8 ft)</td></tr>
<tr><th class="infobox-label">Crew</th><td class="infobox-data">4</td></tr>
<tr><th class="infobox-label">Maximum speed</th><td class="infobox-data">67 km/h (42 mph)
<br>48 km/h off-road</td></tr>
<tr><th class="infobox-label">Weight</th><td class="infobox-data">varies by model</td></tr>
</tbody></table>"""


# Each stat row as (field, value, unit, quote).
def read(html: str) -> list[tuple[str, float, str, str]]:
    return [(r.field, r.value, r.unit, r.quote) for r in stat_rows(html)]


# An infobox with one row per (label, data cell HTML).
def table(*rows: tuple[str, str]) -> str:
    cells = "".join(
        f'<tr><th class="infobox-label">{label}</th><td class="infobox-data">{data}</td></tr>'
        for label, data in rows
    )
    return f'<table class="infobox"><tbody>{cells}</tbody></table>'


def test_a_row_and_its_continuation_take_the_upper_figure_quoted_word_for_word() -> None:
    assert read(DOG) == [
        ("height", 61.0, "cm", "Height: Males 56–61 cm (22–24 in)"),
        ("height", 56.0, "cm", "Height: Females 51–56 cm (20–22 in)"),
        ("mass", 34.0, "kg", "Weight: 25–34 kg (55–75 lb)"),
    ]
    assert [r.row for r in stat_rows(DOG)] == [2, 3, 4]


def test_list_items_read_as_words_and_footnotes_and_styles_are_skipped() -> None:
    rows = dict(infobox_rows(DOG))
    assert rows["Other names"] == "Other names: Flat-coated Golden"
    assert rows["Litter size"] == "Litter size: 7.2±2.7"


def test_machine_rows_use_the_first_unit_the_stat_converts_from() -> None:
    assert read(TANK) == [
        ("mass", 62.3, "tonnes", "Mass: 62.3 tonnes (68.7 short tons)"),
        ("length", 9.83, "m", "Length: 9.83 m (32 ft 3 in) gun forward"),
        ("height", 2.44, "m", "Height: 2.44 m (8 ft)"),
        ("speed", 67.0, "km/h", "Maximum speed: 67 km/h (42 mph) 48 km/h off-road"),
    ]


def test_a_page_without_an_infobox_gives_nothing() -> None:
    assert stat_rows("<p>The toaster weighs 2 kg.</p>") == []


# Felipe's review of #643: "25 kg – 34 kg" read as 25, against the upper-figure rule.
def test_a_range_with_the_unit_on_both_ends_takes_the_upper_figure() -> None:
    html = table(("Weight", "25 kg – 34 kg (55–75 lb)"), ("Length", "1.2 m to 1.5 m"))
    assert read(html) == [
        ("mass", 34.0, "kg", "Weight: 25 kg – 34 kg (55–75 lb)"),
        ("length", 1.5, "m", "Length: 1.2 m to 1.5 m"),
    ]


def test_two_measures_in_different_units_are_not_one_range() -> None:
    assert read(table(("Length", "1.2 m to 150 cm"))) == [
        ("length", 1.2, "m", "Length: 1.2 m to 150 cm")
    ]


def test_rows_without_a_usable_measure_are_left_out() -> None:
    html = table(
        ("Length", "120 m² (1,300 sq ft)"),
        ("Mass", "30 m"),
        ("Length", "5 m/s"),
        ("Top speed", "fast"),
    )
    assert read(html) == []


# A footnote never runs past its cell, so a tag left open inside one can't swallow later rows.
def test_a_footnote_with_a_tag_left_open_ends_with_its_cell() -> None:
    html = table(
        ("Weight", '25–34 kg<span class="reference"><span>[1]</span>'),
        ("Height", "56–61 cm"),
    )
    assert read(html) == [
        ("mass", 34.0, "kg", "Weight: 25–34 kg"),
        ("height", 61.0, "cm", "Height: 56–61 cm"),
    ]
