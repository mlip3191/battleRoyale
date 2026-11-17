"""G06 (#40): prove the promise "every stat on screen links to its source" for a saved battle.

`check_battle` re-checks a finished BattleRecord after the fact, the way a reviewer would:
every sourced stat has its link and quote, every extracted quote is still in the stored article,
every estimate uses an estimate method where the rules allow it, and every number in the
commentary comes from the stat sheets or the result. It reports problems; it never fixes them.
"""

import sqlite3
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.models.battle import BattleRecord
from app.models.stats import ASSUMABLE_STATS, StatName, StatSheet, StatValue
from app.narration.facts import build_facts
from app.narration.writer import unsupported_numbers
from app.research.evidence_check import quote_in_passage

ESTIMATE_METHODS = ("category_default", "assumption")
SOURCED_METHODS = ("extracted", "hand_verified")


@dataclass(frozen=True)
class TraceIssue:
    """One broken link between a number on screen and where it came from."""

    where: str  # e.g. "Gray wolf / mass_kg" or "outro line 1"
    problem: str


@dataclass
class TraceReport:
    """Everything check_battle found for one battle; no issues means fully traceable."""

    battle_id: str
    issues: list[TraceIssue] = field(default_factory=list)
    stats_checked: int = 0
    quotes_checked: int = 0
    # Extracted quotes whose article isn't in this database (a fresh clone has none stored).
    quotes_unchecked: int = 0
    lines_checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.issues

    # One line for a summary table, e.g. "b-7f3k2q: 0 issues (20 stats, 5 quotes, 8 lines)".
    def summary(self) -> str:
        count = len(self.issues)
        noun = "issue" if count == 1 else "issues"
        unchecked = f", {self.quotes_unchecked} quotes unchecked" if self.quotes_unchecked else ""
        return (
            f"{self.battle_id}: {count} {noun} ({self.stats_checked} stats, "
            f"{self.quotes_checked} quotes, {self.lines_checked} lines{unchecked})"
        )


# Check one saved battle. Without a database connection, extracted quotes are counted as
# unchecked rather than flagged, because there is no stored article to compare them with.
def check_battle(record: BattleRecord, connection: sqlite3.Connection | None = None) -> TraceReport:
    report = TraceReport(record.battle_id)
    for sheet in record.stat_sheets:
        for name, stat in sheet.stats.items():
            report.stats_checked += 1
            where = f"{sheet.display_name} / {name.value}"
            for problem in stat_problems(sheet, name, stat):
                report.issues.append(TraceIssue(where, problem))
            if stat.method == "extracted" and stat.source is not None and stat.source.quote.strip():
                _check_quote(report, where, stat, connection)
    _check_scripts(report, record)
    return report


# The rules a single stat must follow, as plain-English problems (empty = traceable).
def stat_problems(sheet: StatSheet, name: StatName, stat: StatValue) -> list[str]:
    problems: list[str] = []
    mythical = sheet.category == "mythical"
    if stat.is_estimate != (stat.method in ESTIMATE_METHODS):
        problems.append(
            f"is_estimate is {stat.is_estimate} but method is {stat.method!r}; "
            "only category_default and assumption are estimates"
        )
    if not stat.is_estimate and stat.method in SOURCED_METHODS:
        problems += _source_problems(stat)
    if stat.is_estimate and stat.source is not None:
        problems.append("an estimate must not carry a source; it was made by code")
    if stat.method == "assumption" and not mythical and name not in ASSUMABLE_STATS:
        problems.append(
            f"assumption is only allowed for {', '.join(sorted(s.value for s in ASSUMABLE_STATS))} "
            "or a mythical creature"
        )
    if mythical and stat.method != "assumption":
        problems.append(f"every stat of a mythical creature is an assumption, not {stat.method!r}")
    if stat.method in ("assumption", "derived") and not (stat.note and stat.note.strip()):
        what = "the formula" if stat.method == "derived" else "the rubric level"
        problems.append(f"{stat.method} value has no note naming {what}")
    return problems


# A sourced value needs a link and the exact words it came from.
def _source_problems(stat: StatValue) -> list[str]:
    if stat.source is None:
        return [f"{stat.method} value has no source (needs a URL and a quote)"]
    problems = []
    if not str(stat.source.url).strip():
        problems.append(f"{stat.method} value's source has no URL")
    if not stat.source.quote.strip():
        problems.append(f"{stat.method} value's source has no quote")
    return problems


# An extracted quote must still appear word for word in the stored article it cites.
def _check_quote(
    report: TraceReport, where: str, stat: StatValue, connection: sqlite3.Connection | None
) -> None:
    assert stat.source is not None  # checked by the caller
    url = str(stat.source.url)
    # A URL can be stored more than once (two fighters sharing an article), so any copy counts.
    texts = (
        [r[0] for r in connection.execute("SELECT raw_text FROM documents WHERE url = ?", (url,))]
        if connection is not None
        else []
    )
    if not texts:
        report.quotes_unchecked += 1
        return
    report.quotes_checked += 1
    if not any(quote_in_passage(stat.source.quote, text) for text in texts):
        report.issues.append(
            TraceIssue(where, f"quote {stat.source.quote!r} is not in the stored article {url}")
        )


# Every number in the commentary must come from the stat sheets or the result (the narration
# number guard, reused, so this check and the script writer agree).
def _check_scripts(report: TraceReport, record: BattleRecord) -> None:
    if not record.scripts:
        return
    if record.result is None or len(record.stat_sheets) != 2:
        report.issues.append(TraceIssue("scripts", "commentary exists without a result to check"))
        return
    counts = [fighter.count for fighter in record.matchup.fighters]
    facts = build_facts(record.stat_sheets, record.result, record.fair_fight, counts)
    for script in record.scripts:
        for n, line in enumerate(script.lines):
            report.lines_checked += 1
            bad = unsupported_numbers(line.text, facts)
            if bad:
                numbers = ", ".join(repr(b.text) for b in bad)
                report.issues.append(
                    TraceIssue(f"{script.kind} line {n}", f"numbers not in the inputs: {numbers}")
                )


# Check every finished battle in the database, oldest first. A record that no longer loads
# (an older shape) is reported as one issue instead of stopping the run.
def trace_stored_battles(connection: sqlite3.Connection) -> list[TraceReport]:
    rows = connection.execute(
        "SELECT battle_id, record_json FROM battles WHERE status = 'done' ORDER BY created_at"
    ).fetchall()
    reports = []
    for battle_id, record_json in rows:
        try:
            record = BattleRecord.model_validate_json(record_json)
        except ValidationError as error:
            report = TraceReport(battle_id)
            errors = error.error_count()
            noun = "error" if errors == 1 else "errors"
            report.issues.append(TraceIssue("record", f"doesn't load ({errors} validation {noun})"))
            reports.append(report)
            continue
        reports.append(check_battle(record, connection))
    return reports


# The share of battles with no issues (the benchmark's traceability column); None with no battles.
# With require_quotes (#370), a battle counts only if every extracted quote was also checked.
def traceable_share(reports: list[TraceReport], require_quotes: bool = False) -> float | None:
    if not reports:
        return None
    return sum(traceable(r, require_quotes) for r in reports) / len(reports)


# A battle with no issues, and in strict mode also no quote left unchecked (#370).
def traceable(report: TraceReport, require_quotes: bool = False) -> bool:
    return report.ok and not (require_quotes and report.quotes_unchecked)
