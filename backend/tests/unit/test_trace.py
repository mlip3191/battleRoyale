"""G06 (#40): the traceability checker passes a clean battle and flags each broken link."""

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import HttpUrl

from app.db import battles as saved
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.battle import BattleRecord
from app.models.narration import Script
from app.models.stats import StatName, StatSheet, StatValue
from app.research.trace import (
    check_battle,
    trace_stored_battles,
    traceable,
    traceable_share,
    value_in_quote,
)
from app.simulation import benchmark as bm
from scripts import run_benchmark, trace_report

FIXTURE = Path(__file__).parents[1] / "fixtures" / "contracts" / "battle-record-done.json"


def clean() -> BattleRecord:
    return BattleRecord.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


# A database whose documents hold every extracted quote of the clean battle, as ingest stores them.
@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "app.db")
    apply_migrations(connection)
    texts: dict[str, list[str]] = {}
    for sheet in clean().stat_sheets:
        for stat in sheet.stats.values():
            if stat.method == "extracted" and stat.source is not None:
                texts.setdefault(str(stat.source.url), []).append(stat.source.quote)
    for n, (url, quotes) in enumerate(texts.items()):
        body = "Some text before. " + " Then more text. ".join(quotes) + " The end."
        connection.execute(
            "INSERT INTO documents (doc_id, fighter_id, source, title, url, license, "
            "retrieved_at, raw_text, content_hash) VALUES (?, ?, 'wikipedia', ?, ?, "
            "'CC BY-SA 4.0', '2026-11-01T00:00:00+00:00', ?, ?)",
            (f"doc-{n}", f"fighter-{n}", f"Doc {n}", url, body, f"hash-{n}"),
        )
    connection.commit()
    yield connection
    connection.close()


# The battle with one stat swapped out; model_copy skips validation, as a broken record would.
def with_stat(side: int, name: StatName, **changes: object) -> BattleRecord:
    record = clean()
    sheet = record.stat_sheets[side]
    stat = sheet.stats[name].model_copy(update=changes)
    sheets = list(record.stat_sheets)
    sheets[side] = sheet.model_copy(update={"stats": {**sheet.stats, name: stat}})
    return record.model_copy(update={"stat_sheets": sheets})


def problems(record: BattleRecord, connection: sqlite3.Connection | None = None) -> list[str]:
    return [f"{i.where}: {i.problem}" for i in check_battle(record, connection).issues]


def test_the_clean_battle_passes_with_0_issues(db: sqlite3.Connection) -> None:
    report = check_battle(clean(), db)
    assert report.ok and report.issues == []
    assert report.summary().startswith("b-7f3k2q: 0 issues")
    assert report.stats_checked == 20 and report.lines_checked == 8
    assert report.quotes_checked == 5 and report.quotes_unchecked == 0


def test_without_a_database_quotes_are_counted_as_unchecked_not_flagged() -> None:
    report = check_battle(clean())
    assert report.ok and report.quotes_unchecked == 5
    assert "5 quotes unchecked" in report.summary()


def test_a_non_estimate_without_url_or_quote_is_flagged(db: sqlite3.Connection) -> None:
    no_source = problems(with_stat(1, StatName.MASS, source=None), db)
    assert no_source == [
        "Gray wolf / mass_kg: extracted value has no source (needs a URL and a quote)"
    ]
    source = clean().stat_sheets[1].stats[StatName.MASS].source
    assert source is not None
    no_quote = with_stat(1, StatName.MASS, source=source.model_copy(update={"quote": " "}))
    assert problems(no_quote, db) == ["Gray wolf / mass_kg: extracted value's source has no quote"]


def test_a_quote_no_longer_in_the_stored_article_is_flagged(db: sqlite3.Connection) -> None:
    source = clean().stat_sheets[0].stats[StatName.MASS].source
    assert source is not None
    tampered = source.model_copy(update={"quote": source.quote.replace("389", "489")})
    found = problems(with_stat(0, StatName.MASS, source=tampered), db)
    assert len(found) == 1
    assert "Grizzly bear - adult male / mass_kg: quote" in found[0]
    assert "is not in the stored article" in found[0]


def test_an_estimate_with_the_wrong_method_is_flagged(db: sqlite3.Connection) -> None:
    # An estimate labeled as extracted, with no source: not an estimate method.
    mislabeled = with_stat(1, StatName.SPEED, method="extracted")
    assert any(
        "is_estimate is True but method is 'extracted'" in p for p in problems(mislabeled, db)
    )
    # An assumption on a physical stat of a real animal: only behavioral stats may be assumed.
    assumed = with_stat(
        1, StatName.ATTACK_FORCE, method="assumption", note="rubric level 3: a guess"
    )
    found = problems(assumed, db)
    assert len(found) == 1 and "assumption is only allowed for" in found[0]
    # A derived value must name its formula.
    unexplained = with_stat(0, StatName.REACH, note=None)
    assert problems(unexplained, db) == [
        "Grizzly bear - adult male / reach_m: derived value has no note naming the formula"
    ]


# The battle with its first outro line making up a number.
def invented_number() -> BattleRecord:
    record = clean()
    outro = next(s for s in record.scripts if s.kind == "outro")
    line = outro.lines[0].model_copy(update={"text": "That bear weighs 9,999 kilograms, folks!"})
    changed: Script = outro.model_copy(update={"lines": [line, *outro.lines[1:]]})
    scripts = [changed if s.kind == "outro" else s for s in record.scripts]
    return record.model_copy(update={"scripts": scripts})


def test_a_script_number_not_in_the_inputs_is_flagged(db: sqlite3.Connection) -> None:
    assert problems(invented_number(), db) == ["outro line 0: numbers not in the inputs: '9,999'"]


def test_a_mythical_creature_must_assume_every_stat() -> None:
    record = clean()
    myth = record.stat_sheets[0].model_copy(update={"category": "mythical"})
    found = problems(record.model_copy(update={"stat_sheets": [myth, record.stat_sheets[1]]}))
    assert any("every stat of a mythical creature is an assumption" in p for p in found)


# --- Every stored battle: trace_report.py and the benchmark (F07) -------------------------


def store(connection: sqlite3.Connection, *records: BattleRecord) -> None:
    for record in records:
        saved.save(connection, record, cache_key=None)


def test_trace_report_checks_every_stored_battle_and_exits_1_on_an_issue(
    db: sqlite3.Connection, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = invented_number().model_copy(update={"battle_id": "b-broken"})
    store(db, clean(), broken)
    reports = trace_stored_battles(db)
    assert [r.battle_id for r in reports] == ["b-7f3k2q", "b-broken"]
    assert traceable_share(reports) == 0.5
    assert trace_report.main(["--db", str(tmp_path / "app.db")]) == 1
    printed = capsys.readouterr().out
    assert "b-7f3k2q: 0 issues" in printed and "b-broken: 1 issue " in printed
    assert "outro line 0: numbers not in the inputs: '9,999'" in printed
    assert "Traceable: 1 of 2 battles (50%)." in printed
    assert "Quotes checked against stored articles: 10; not checkable here: 0." in printed


def test_a_stored_record_that_no_longer_loads_is_one_issue(db: sqlite3.Connection) -> None:
    store(db, clean())
    db.execute('UPDATE battles SET record_json = \'{"battle_id": "b-7f3k2q"}\'')
    (report,) = trace_stored_battles(db)
    assert [i.where for i in report.issues] == ["record"]
    assert "doesn't load" in report.issues[0].problem


def test_trace_report_with_no_battles_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty.db"
    apply_migrations(connect(empty))  # an existing database with no battles in it
    assert trace_report.main(["--db", str(empty)]) == 0
    assert "No finished battles stored yet" in capsys.readouterr().out
    assert traceable_share([]) is None


def test_trace_report_refuses_a_database_path_that_does_not_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    typo = tmp_path / "typo.db"
    assert trace_report.main(["--db", str(typo)]) == 2
    assert "No database at" in capsys.readouterr().err
    assert not typo.exists()  # a typo never creates an empty database


# Mike's #353 review: with no articles stored, every battle passes, so the footer and the
# benchmark note must say that 0 quotes were actually checked.
def test_100_percent_with_no_stored_articles_says_no_quote_was_checked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "no-articles.db"
    connection = connect(path)
    apply_migrations(connection)
    store(connection, clean())
    assert trace_report.main(["--db", str(path)]) == 0
    printed = capsys.readouterr().out
    assert "Traceable: 1 of 1 battles (100%)." in printed
    assert "Quotes checked against stored articles: 0; not checkable here: 5." in printed
    monkeypatch.setattr(run_benchmark, "connect", lambda: connect(path))
    report = bm.RunReport("seed", [], 0.0, "abc1234", datetime.now())
    run_benchmark.add_traceability(report, mock=False)
    assert "0 quotes were checked" in report.notes[0]
    assert "5 could not be checked here" in report.notes[0]
    connection.close()


def test_a_quote_found_in_any_stored_copy_of_its_article_passes(db: sqlite3.Connection) -> None:
    source = clean().stat_sheets[0].stats[StatName.MASS].source
    assert source is not None
    # A second copy of the same URL whose text lacks the quote, read first (lower rowid).
    db.execute(
        "INSERT INTO documents (rowid, doc_id, fighter_id, source, title, url, license, "
        "retrieved_at, raw_text, content_hash) VALUES (0, 'a-copy', 'other', 'wikipedia', "
        "'Copy', ?, 'CC BY-SA 4.0', '2026-11-01T00:00:00+00:00', 'An older revision.', 'h')",
        (str(source.url),),
    )
    report = check_battle(clean(), db)
    assert report.ok and report.quotes_checked == 5


def test_the_benchmark_fills_its_traceability_column_from_stored_battles(
    db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store(db, clean())
    monkeypatch.setattr(run_benchmark, "connect", lambda: connect(tmp_path / "app.db"))
    report = bm.RunReport("seed", [], 0.0, "abc1234", datetime.now())
    run_benchmark.add_traceability(report, mock=False)
    assert report.traceability == 1.0
    assert "traceability 100%" in bm.render_run(report)
    assert (
        "5 quotes were checked against stored articles and 0 could not be checked"
        in (report.notes[0])
    )
    mock = bm.RunReport("mock", [], 0.0, "abc1234", datetime.now())
    run_benchmark.add_traceability(mock, mock=True)
    assert mock.traceability is None and "isn't checked in mock mode" in mock.notes[0]


# --- #369: hand-verified quotes are re-checked, and every value must be in its own quote --------

SEED_DIR = Path(__file__).parents[3] / "data" / "seed" / "fighters"


def sourced(
    value: float, unit: str, quote: str, method: str = "hand_verified", note: str | None = None
) -> StatValue:
    source = clean().stat_sheets[0].stats[StatName.MASS].source
    assert source is not None
    return StatValue(
        value=value,
        unit=unit,
        source=source.model_copy(update={"quote": quote}),
        confidence="medium",
        is_estimate=False,
        method=method,
        note=note,
    )


def test_a_hand_verified_quote_missing_from_its_stored_article_is_flagged(
    db: sqlite3.Connection,
) -> None:
    source = clean().stat_sheets[0].stats[StatName.MASS].source
    assert source is not None
    tampered = source.model_copy(update={"quote": source.quote.replace("389", "489")})
    record = with_stat(0, StatName.MASS, method="hand_verified", source=tampered, value=489.0)
    found = [p for p in problems(record, db) if "/ mass_kg" in p]  # the script's 389 is apart
    assert len(found) == 1 and "is not in the stored article" in found[0]


def test_a_value_that_matches_no_number_in_its_quote_is_flagged(db: sqlite3.Connection) -> None:
    record = with_stat(0, StatName.MASS, value=500.0)  # its quote says 389 kilograms (858 lb)
    # (The commentary's "389" is now flagged too, as a number not in the inputs.)
    assert [p for p in problems(record, db) if "/ mass_kg" in p] == [
        "Grizzly bear - adult male / mass_kg: value 500.0 kg isn't a number in its quote, "
        "even after unit conversion"
    ]


def test_a_value_converted_from_the_quotes_unit_passes() -> None:
    speed = sourced(13.33, "m/s", "It can run at speeds of up to 48 km/h (30 mph).")
    assert value_in_quote(StatName.SPEED, speed)
    pounds = sourced(389.0, "kg", "males weighing up to 858 lb")
    assert value_in_quote(StatName.MASS, pounds)


def test_a_unit_written_as_a_capital_symbol_passes() -> None:
    kick = sourced(1924.0, "N", "90% of the impacts had a maximum value below 1924 N.")
    assert value_in_quote(StatName.ATTACK_FORCE, kick)


def test_a_table_row_with_no_units_passes_but_a_wrong_number_does_not() -> None:
    row = "Anas platyrhynchos Mallard 1.14 0.890 0.107 19.7 1.55 21"
    assert value_in_quote(StatName.MASS, sourced(1.14, "kg", row))
    assert not value_in_quote(StatName.MASS, sourced(1.5, "kg", row))
    # Once the quote states a unit for this stat, a bare number no longer counts.
    assert not value_in_quote(StatName.MASS, sourced(21.0, "kg", "weighs 1.14 kg, 21 of them"))


def test_a_figure_converted_in_the_note_passes_only_from_a_quoted_number() -> None:
    quote = "It is powerful enough to lift up to 350 kg (770 lb)"
    good = sourced(3432.0, "N", quote, note="350 kgf x 9.80665 m/s^2 = 3432 N.")
    assert value_in_quote(StatName.ATTACK_FORCE, good)
    other_start = sourced(3432.0, "N", quote, note="400 kgf x 8.58 = 3432 N.")
    assert not value_in_quote(StatName.ATTACK_FORCE, other_start)  # 400 isn't in the quote
    wrong_end = sourced(3432.0, "N", quote, note="350 kgf x 9.80665 = 3000 N.")
    assert not value_in_quote(StatName.ATTACK_FORCE, wrong_end)


def test_every_committed_seed_sheet_passes_the_value_check() -> None:
    failing = []
    for path in sorted(SEED_DIR.glob("*.json")):
        sheet = StatSheet.model_validate_json(path.read_text(encoding="utf-8"))
        for name, stat in sheet.stats.items():
            if stat.method in ("extracted", "hand_verified") and stat.source is not None:
                if not value_in_quote(name, stat):
                    failing.append(f"{path.stem}/{name.value}")
    assert failing == []


# #379 review: the checker accepts exactly the unit spellings extraction accepts.
@pytest.mark.parametrize(
    ("stat", "value", "unit", "quote"),
    [
        (StatName.MASS, 389.18, "kg", "males weighing up to 858 lbs"),
        (StatName.SPEED, 13.3333, "m/s", "It can run at 48 kilometres per hour."),
        (StatName.SPEED, 13.3333, "m/s", "It can run at 48 kilometers per hour."),
        (StatName.SPEED, 13.4112, "m/s", "It was clocked at 30 MPH."),
        (StatName.ATTACK_FORCE, 4000.0, "N", "Its bite reaches 4 kN."),
        (StatName.MASS, 4.0, "kg", "Adults weigh 4-5 kg."),
        (StatName.MASS, 5.0, "kg", "Adults weigh 4-5 kg."),
    ],
)
def test_extraction_spellings_and_range_ends_pass(
    stat: StatName, value: float, unit: str, quote: str
) -> None:
    assert value_in_quote(stat, sourced(value, unit, quote, method="extracted"))


def test_an_extracted_value_must_match_to_its_stored_digits() -> None:
    quote = "males weighing 389 kilograms (858 lb)"
    assert value_in_quote(StatName.MASS, sourced(389.0, "kg", quote, method="extracted"))
    assert not value_in_quote(StatName.MASS, sourced(392.0, "kg", quote, method="extracted"))
    # A hand-verified value may be rounded by the person who checked it (within 1%).
    assert value_in_quote(StatName.MASS, sourced(391.0, "kg", quote))


def test_a_note_formula_with_wrong_arithmetic_is_flagged() -> None:
    quote = "It is powerful enough to lift up to 350 kg (770 lb)"
    wrong = sourced(5000.0, "N", quote, note="350 kgf x 2 = 5000 N.")
    assert not value_in_quote(StatName.ATTACK_FORCE, wrong)


# --- #370: strict mode, so "traceable" means every quote was really checked -----------------


# A database holding the clean battle but none of its articles: 5 quotes can't be checked.
def no_articles(tmp_path: Path) -> Path:
    path = tmp_path / "no-articles.db"
    connection = connect(path)
    apply_migrations(connection)
    store(connection, clean())
    connection.close()
    return path


def test_require_quotes_fails_when_a_quote_could_not_be_checked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = no_articles(tmp_path)
    assert trace_report.main(["--db", str(path), "--require-quotes"]) == 1
    printed = capsys.readouterr().out
    assert "Strict mode (--require-quotes): 5 quotes couldn't be checked, in b-7f3k2q." in printed
    assert "Traceable: 0 of 1 battles (0%)." in printed  # the footer agrees with the exit code
    assert trace_report.main(["--db", str(path)]) == 0  # without the flag: unchanged


def test_require_quotes_passes_when_every_quote_was_checked(
    db: sqlite3.Connection, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store(db, clean())  # the db fixture stores every quote's article
    assert trace_report.main(["--db", str(tmp_path / "app.db"), "--require-quotes"]) == 0
    assert "Strict mode" not in capsys.readouterr().out


def test_strict_benchmark_counts_an_uncheckable_battle_as_not_traceable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = no_articles(tmp_path)
    monkeypatch.setattr(run_benchmark, "connect", lambda: connect(path))
    relaxed = bm.RunReport("seed", [], 0.0, "abc1234", datetime.now())
    run_benchmark.add_traceability(relaxed, mock=False)
    strict = bm.RunReport("seed", [], 0.0, "abc1234", datetime.now())
    run_benchmark.add_traceability(strict, mock=False, require_quotes=True)
    assert relaxed.traceability == 1.0 and strict.traceability == 0.0
    # The count in the note follows the same rule as the percentage (#377 QA review).
    assert "1 of 1 stored battles have no issues;" in relaxed.notes[0]
    assert "0 of 1 stored battles have no issues and every quote checked;" in strict.notes[0]
    assert any("Strict mode (--require-quotes)" in note for note in strict.notes)
    assert not any("Strict mode" in note for note in relaxed.notes)


def test_strict_share_only_counts_fully_checked_battles(db: sqlite3.Connection) -> None:
    checked = check_battle(clean(), db)
    unchecked = check_battle(clean())  # no database: its 5 quotes are unchecked
    assert traceable_share([checked, unchecked]) == 1.0
    assert traceable_share([checked, unchecked], require_quotes=True) == 0.5


def test_strict_mode_on_an_empty_database_has_nothing_to_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # No finished battles means nothing was claimed, so strict mode doesn't fail; the
    # benchmark shows n/a rather than a percentage (#377 review: pinned on purpose).
    empty = tmp_path / "empty.db"
    apply_migrations(connect(empty))
    assert trace_report.main(["--db", str(empty), "--require-quotes"]) == 0
    assert "No finished battles stored yet" in capsys.readouterr().out
    monkeypatch.setattr(run_benchmark, "connect", lambda: connect(empty))
    report = bm.RunReport("seed", [], 0.0, "abc1234", datetime.now())
    run_benchmark.add_traceability(report, mock=False, require_quotes=True)
    assert report.traceability is None


def test_strict_mode_says_quote_for_a_count_of_one() -> None:
    one = check_battle(clean())
    one.quotes_unchecked = 1
    assert "1 quote couldn't be checked" in trace_report.render([one], require_quotes=True)


# --- #379 re-review: hand-verified quotes in strict mode, and tiny stored values ------------------


def test_require_quotes_counts_a_hand_verified_quote_with_no_stored_article(
    db: sqlite3.Connection, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Every extracted quote's article is stored (the db fixture); this one points elsewhere.
    source = clean().stat_sheets[0].stats[StatName.MASS].source
    assert source is not None
    elsewhere = source.model_copy(update={"url": HttpUrl("https://example.org/not-stored")})
    store(db, with_stat(0, StatName.MASS, method="hand_verified", source=elsewhere))
    path = str(tmp_path / "app.db")
    assert trace_report.main(["--db", path]) == 0  # unchecked, not an issue
    assert "0 issues" in capsys.readouterr().out
    assert trace_report.main(["--db", path, "--require-quotes"]) == 1
    assert "1 quote couldn't be checked" in capsys.readouterr().out


def test_a_tiny_extracted_value_must_still_match_to_its_stored_digits() -> None:
    # 2.5e-06 prints in exponent form; its digits must still be read as 0.0000025 (#379 review).
    quote = "A female weighs about 2.5 mg."
    assert value_in_quote(StatName.MASS, sourced(2.5e-06, "kg", quote, method="extracted"))
    assert not value_in_quote(StatName.MASS, sourced(3.0e-06, "kg", quote, method="extracted"))


def test_a_hand_verified_quote_counts_as_unchecked_without_a_database() -> None:
    # The fixture's five quotes are all extracted; this pins the hand-verified path (#379 review).
    report = check_battle(with_stat(0, StatName.MASS, method="hand_verified"))
    assert report.ok and report.quotes_unchecked == 5
    assert traceable(report) is True
    assert traceable(report, require_quotes=True) is False
