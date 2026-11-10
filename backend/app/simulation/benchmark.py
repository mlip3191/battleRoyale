"""The benchmark: how good are the app's verdicts against expert answers? (F07)

Input is Gunnar's matchup set (G07): `data/benchmark/matchups.yaml` (the tuning set) and the sealed
`data/benchmark/heldout.yaml`. Each matchup is simulated and the verdict compared with the expected
answer. The two sets are always reported separately, and held-out results are never used to change
constants. Output is `docs/benchmark-results.md`, newest run first, keeping the last five.

Pass rules (docs/benchmark.md, G07):
- the favorite must match `expected_winner` (0, 1, or draw);
- for high-confidence cases the favorite's win probability must also be at least 0.7;
- for "count" cases the fair-fight count must fall inside the expected range.
"""

import json
import re
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml

from app.config import REPO_ROOT
from app.models.matchup import FighterRequest, Matchup
from app.models.simulation import FairFight, SimulationResult
from app.models.stats import StatSheet
from app.models.terrain import Terrain
from app.simulation.engine import run
from app.simulation.fair import fair_fight

HIGH_CONFIDENCE_MIN_PROB = 0.7
KEEP_RUNS = 5
RESULTS_FILE = REPO_ROOT / "docs" / "benchmark-results.md"
BENCHMARK_DIR = REPO_ROOT / "data" / "benchmark"
FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
MOCK_DIR = FIXTURE_DIR / "benchmark"
CONTRACT_DIR = FIXTURE_DIR / "contracts"

Group = Literal["obvious", "documented", "count"]
GROUPS: tuple[Group, ...] = ("obvious", "documented", "count")


class BenchmarkError(Exception):
    """Something the user can fix (missing file, unknown fighter, input not ready yet)."""


# --- The matchup set --------------------------------------------------------------------


@dataclass(frozen=True)
class Entry:
    """One benchmark matchup and its expert answer."""

    id: str
    group: Group
    matchup: Matchup
    expected_winner: Literal["0", "1", "draw"]
    confidence: Literal["high", "medium"]
    fair_range: tuple[int, int] | None
    source: str
    held_out: bool


def _parse_range(value: Any) -> tuple[int, int] | None:
    """Accept [lo, hi], {min, max}, "lo-hi", or a single number."""
    if value in (None, "", []):
        return None
    if isinstance(value, dict):
        return int(value["min"]), int(value["max"])
    if isinstance(value, str):
        numbers = [int(n) for n in re.findall(r"\d+", value)]
        return (numbers[0], numbers[-1]) if numbers else None
    if isinstance(value, (list, tuple)):
        return int(value[0]), int(value[-1])
    return int(value), int(value)


def _infer_group(raw: dict[str, Any], fair_range: tuple[int, int] | None) -> Group:
    group = raw.get("group")
    if group in GROUPS:
        return group
    if fair_range is not None:
        return "count"
    source = str(raw.get("source", "")).strip().lower()
    return "obvious" if source.startswith("obvious") else "documented"


def parse_entry(raw: dict[str, Any], held_out: bool) -> Entry:
    """Turn one YAML mapping into an Entry, with a clear error if it is malformed."""
    try:
        fighters = [
            FighterRequest(
                entity=str(f["entity"]),
                count=int(f.get("count", 1)),
                variant=f.get("variant"),
                raw=str(f.get("raw", f["entity"])),
            )
            for f in raw["fighters"]
        ]
        terrain = Terrain(raw.get("terrain", "arena"))
        winner = str(raw["expected_winner"]).strip().lower()
        if winner not in ("0", "1", "draw"):
            raise ValueError(f"expected_winner must be 0, 1, or draw, not {winner!r}")
        fair_range = _parse_range(raw.get("expected_fair_count"))
        names = " vs ".join(f.raw for f in fighters)
        return Entry(
            id=str(raw["id"]),
            group=_infer_group(raw, fair_range),
            matchup=Matchup(fighters=fighters, terrain=terrain, raw_text=names),
            expected_winner=winner,  # type: ignore[arg-type]
            confidence="high"
            if str(raw.get("confidence", "medium")).lower() == "high"
            else "medium",
            fair_range=fair_range,
            source=str(raw.get("source", "")),
            held_out=held_out,
        )
    except (KeyError, ValueError, TypeError) as error:
        label = raw.get("id", "?") if isinstance(raw, dict) else "?"
        raise BenchmarkError(f"matchup {label!r} is malformed: {error}") from error


def load_entries(path: Path, held_out: bool) -> list[Entry]:
    """Read a matchup file (a list, or a mapping with a `matchups` list)."""
    if not path.exists():
        raise BenchmarkError(f"{path} does not exist yet (the benchmark set is built in task G07)")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = data.get("matchups", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise BenchmarkError(f"{path} must hold a list of matchups")
    return [parse_entry(item, held_out) for item in items]


# --- Where stat sheets come from --------------------------------------------------------


class SheetSource(Protocol):
    """Gives the benchmark a stat sheet for each fighter request."""

    def get(self, fighter: FighterRequest) -> StatSheet: ...


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class IndexedSheets:
    """Sheets found by fighter id, base name, display name, or media name."""

    def __init__(self, sheets: Sequence[StatSheet]) -> None:
        self.index: dict[str, StatSheet] = {}
        for sheet in sheets:
            keys = {sheet.fighter_id, sheet.fighter_id.split("--")[0]}
            keys |= {_slug(sheet.display_name), _slug(sheet.media_name)}
            for key in keys:
                self.index.setdefault(_slug(key), sheet)

    def get(self, fighter: FighterRequest) -> StatSheet:
        base = _slug(fighter.entity)
        wanted = [f"{base}--{_slug(fighter.variant)}"] if fighter.variant else []
        for key in [*wanted, base]:
            if key in self.index:
                return self.index[key]
        raise BenchmarkError(f"no stat sheet for {fighter.entity!r} (variant {fighter.variant!r})")


def _load_sheets_from(directory: Path, patterns: tuple[str, ...]) -> list[StatSheet]:
    sheets: list[StatSheet] = []
    for pattern in patterns:
        for path in sorted(directory.glob(pattern)):
            try:
                text = path.read_text(encoding="utf-8")
                is_yaml = path.suffix in (".yaml", ".yml")
                data = yaml.safe_load(text) if is_yaml else json.loads(text)
                items = data if isinstance(data, list) else data.get("sheets", [data])
                sheets += [StatSheet.model_validate(item) for item in items]
            except (ValueError, AttributeError, yaml.YAMLError) as error:
                # pydantic's ValidationError and json's decode error are both ValueErrors
                first = str(error).strip().splitlines()[0] if str(error).strip() else "invalid"
                raise BenchmarkError(f"{path.name} is not a valid stat sheet: {first}") from error
    return sheets


def mock_sheets() -> SheetSource:
    """The contract fixture sheets (grizzly, gray wolf, toaster, dragon): no endpoints needed."""
    return IndexedSheets(_load_sheets_from(CONTRACT_DIR, ("stat-sheet*.json",)))


def seed_sheets(directory: Path | None = None) -> SheetSource:
    """Hand-verified seed sheets (G05) from `data/seed/fighters/<id>.json` (or YAML).

    Only that folder is read: G09's top-level `data/seed/*.yaml` files are not stat sheets.
    """
    directory = (directory or REPO_ROOT / "data" / "seed") / "fighters"
    sheets = (
        _load_sheets_from(directory, ("*.json", "*.yaml", "*.yml")) if directory.exists() else []
    )
    sheets = [s for s in sheets if s.category != "mythical"]  # no ground truth for legends
    if not sheets:
        raise BenchmarkError(
            f"no seed stat sheets found in {directory} yet (they are built in task G05)"
        )
    return IndexedSheets(sheets)


def research_sheets() -> SheetSource:
    raise BenchmarkError(
        "--sheets research needs the research pipeline (task G04), which has not landed yet"
    )


# --- Judging ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Judged:
    """One matchup's result against its expected answer."""

    entry: Entry
    outcome: str
    favorite: int | None
    win_pct: tuple[float, float]
    fair_count: int | None
    passed: bool
    reason: str
    skipped: bool = False  # no stat sheet for a fighter: not scored, and said so in the report


def judge(entry: Entry, result: SimulationResult, fair: FairFight | None) -> Judged:
    """Apply the pass rules to one simulation result."""
    p0, p1 = result.win_prob
    favorite = (
        None if result.outcome in ("draw", "no_contest") or p0 == p1 else (0 if p0 > p1 else 1)
    )
    win_pct = (round(p0 * 100, 1), round(p1 * 100, 1))
    fair_count = None if fair is None else fair.count

    if entry.fair_range is not None:
        lo, hi = entry.fair_range
        # `expected_winner` is the side expected to win as written; the range is the other
        # side's count, so the fair-fight search must have varied that other side.
        expected_loser = None if entry.expected_winner == "draw" else 1 - int(entry.expected_winner)
        if fair_count is None:
            why = (
                f"the main fight was a {result.outcome.replace('_', ' ')}, so there is no loser "
                "to even up"
                if result.outcome in ("draw", "no_contest")
                else "no fair count found"
            )
            return Judged(
                entry, result.outcome, favorite, win_pct, None, False, f"{why} (expected {lo}-{hi})"
            )
        if fair is not None and expected_loser is not None and fair.varied_side != expected_loser:
            reason = (
                f"expected side {1 - expected_loser} to win, but the fair-fight search varied "
                f"side {fair.varied_side} (the favorite was "
                f"{'nobody' if favorite is None else f'side {favorite}'})"
            )
            return Judged(entry, result.outcome, favorite, win_pct, fair_count, False, reason)
        ok = lo <= fair_count <= hi
        reason = f"fair count {fair_count} {'inside' if ok else 'outside'} expected {lo}-{hi}"
        return Judged(entry, result.outcome, favorite, win_pct, fair_count, ok, reason)

    expected = entry.expected_winner
    if expected == "draw":
        ok = result.outcome == "draw"
        reason = "draw as expected" if ok else f"expected a draw, got {result.outcome}"
        return Judged(entry, result.outcome, favorite, win_pct, fair_count, ok, reason)

    wanted = int(expected)
    if favorite != wanted:
        got = "no favorite" if favorite is None else f"side {favorite}"
        return Judged(
            entry,
            result.outcome,
            favorite,
            win_pct,
            fair_count,
            False,
            f"expected side {wanted}, got {got}",
        )
    if entry.confidence == "high" and result.win_prob[wanted] < HIGH_CONFIDENCE_MIN_PROB:
        reason = f"right favorite but only {win_pct[wanted]}% (high confidence needs 70%)"
        return Judged(entry, result.outcome, favorite, win_pct, fair_count, False, reason)
    return Judged(entry, result.outcome, favorite, win_pct, fair_count, True, "favorite matches")


def evaluate(entry: Entry, sheets: SheetSource, runs: int) -> Judged:
    """Simulate one matchup (and its fair-fight search for count cases) and judge it."""
    stat_sheets = [sheets.get(f) for f in entry.matchup.fighters]
    result = run(entry.matchup, stat_sheets, runs=runs, explain=False)
    fair = fair_fight(entry.matchup, stat_sheets, result) if entry.fair_range else None
    return judge(entry, result, fair)


# --- The report -------------------------------------------------------------------------


@dataclass
class RunReport:
    """Everything one benchmark run measured."""

    mode: str  # "seed", "research", or "mock"
    judged: list[Judged]
    runtime_s: float
    commit: str
    started: datetime
    traceability: float | None = None  # share of results whose numbers trace to a source
    notes: list[str] = field(default_factory=list)
    tuning_only: bool = False  # held-out matchups were not run, so none of their rows are shown

    def subset(self, held_out: bool | None = None, group: Group | None = None) -> list[Judged]:
        return [
            j
            for j in self.judged
            if (held_out is None or j.entry.held_out == held_out)
            and (group is None or j.entry.group == group)
        ]


def rate(items: Sequence[Judged]) -> str:
    """Pass rate over the matchups that were scored (skipped ones are listed separately)."""
    scored = [j for j in items if not j.skipped]
    if not scored:
        return "n/a"
    passed = sum(j.passed for j in scored)
    return f"{passed}/{len(scored)} ({round(100 * passed / len(scored))}%)"


def current_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=10,
        )  # fmt: skip
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def render_run(report: RunReport) -> str:
    """One run as a markdown section; the heading carries the date so nothing is overwritten."""
    when = report.started.strftime("%Y-%m-%d %H:%M")
    trace = "n/a" if report.traceability is None else f"{round(report.traceability * 100)}%"
    held_rate = (
        "not run (tuning only)" if report.tuning_only else rate(report.subset(held_out=True))
    )
    lines = [
        f"## Run {when} — sheets: {report.mode}",
        "",
        f"Commit `{report.commit}` · runtime {report.runtime_s:.1f} s · traceability {trace}",
        "",
        "| Set | Pass rate |",
        "|---|---|",
        f"| Tuning | {rate(report.subset(held_out=False))} |",
        f"| Held-out (never used to change constants) | {held_rate} |",
        "",
        "| Group | Tuning | Held-out |",
        "|---|---|---|",
    ]
    for group in GROUPS:
        tuning = rate(report.subset(held_out=False, group=group))
        held = rate(report.subset(held_out=True, group=group))
        held = "not run" if report.tuning_only else held
        lines.append(f"| {group} | {tuning} | {held} |")
    skipped = [j for j in report.judged if j.skipped]
    if skipped:
        lines += [
            "",
            f"**Skipped ({len(skipped)}):** not scored, because a stat sheet is missing.",
            "",
        ]
        lines += [f"- {j.entry.id}: {j.reason}" for j in skipped]
    for note in report.notes:
        lines += ["", f"_{note}_"]
    for title, held_out in (("Tuning set", False), ("Held-out set", True)):
        if held_out and report.tuning_only:
            continue  # held-out rows stay hidden while tuning
        rows = report.subset(held_out=held_out)
        lines += ["", f"### {title}", ""]
        if not rows:
            lines.append("No matchups in this set.")
            continue
        lines += [
            "| Matchup | Group | Expected | Favorite | Win % (side 0 / 1) | Fair count | Result |",
            "|---|---|---|---|---|---|---|",
        ]
        for j in rows:
            favorite = {None: "none"}.get(j.favorite, f"side {j.favorite}")
            expected = (
                f"side {j.entry.expected_winner}" if j.entry.expected_winner != "draw" else "draw"
            )
            fair = "—" if j.fair_count is None else str(j.fair_count)
            verdict = (
                "skipped" if j.skipped else "pass" if j.passed else "FAIL"
            ) + f" — {j.reason}"
            lines.append(
                f"| {j.entry.id} | {j.entry.group} | {expected} | {favorite} "
                f"| {j.win_pct[0]} / {j.win_pct[1]} | {fair} | {verdict} |"
            )
    return "\n".join(lines) + "\n"


HEADER = (
    "# Benchmark results\n\n"
    "How often the simulator agrees with expert answers (see `docs/benchmark.md`). "
    "Newest run first; "
    f"the last {KEEP_RUNS} runs are kept. Generated by `backend/scripts/run_benchmark.py`.\n"
)


def write_report(path: Path, report: RunReport) -> None:
    """Put this run on top of the file and keep the previous ones below (last five in all)."""
    previous: list[str] = []
    if path.exists():
        text = path.read_text(encoding="utf-8")
        parts = re.split(r"(?m)^(?=## Run )", text)
        previous = [p for p in parts[1:] if p.strip()]
    sections = [render_run(report)] + [p if p.endswith("\n") else p + "\n" for p in previous]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + "\n" + "\n".join(sections[:KEEP_RUNS]), encoding="utf-8")


# --- Running it -------------------------------------------------------------------------


def run_benchmark(
    sheets: SheetSource,
    mode: str,
    tuning: Sequence[Entry],
    held_out: Sequence[Entry],
    runs: int,
    tuning_only: bool = False,
) -> RunReport:
    """Score every matchup. With `tuning_only` the held-out set is neither run nor shown."""
    if tuning_only:
        held_out = []
    started = datetime.now()
    clock = time.perf_counter()
    judged = []
    for entry in [*tuning, *held_out]:
        try:
            judged.append(evaluate(entry, sheets, runs))
        except BenchmarkError as error:  # e.g. no hand-verified sheet for one fighter yet
            judged.append(Judged(entry, "skipped", None, (0.0, 0.0), None, False, str(error), True))
    return RunReport(
        mode=mode,
        judged=judged,
        runtime_s=time.perf_counter() - clock,
        commit=current_commit(),
        started=started,
        tuning_only=tuning_only,
        notes=[
            "Traceability (G06) is not wired in yet; it shows n/a until research/trace.py lands."
        ],
    )
