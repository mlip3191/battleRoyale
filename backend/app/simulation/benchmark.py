"""The benchmark: how good are the app's verdicts against expert answers? (F07)

Input is Gunnar's matchup set (G07): `data/benchmark/matchups.yaml` (the tuning set) and the sealed
`data/benchmark/heldout.yaml`. Each matchup is simulated and the verdict compared with the expected
answer. The two sets are always reported separately, and held-out results are never used to change
constants. Output is `docs/benchmark-results.md`, newest run first, keeping the last five.

Pass rules (docs/benchmark.md, G07):
- the favorite must match `expected_winner` (0, 1, or draw);
- for high-confidence cases the favorite's win probability must also be at least 0.7;
- for "count" cases the fair-fight count must fall inside the expected range.

The edge-case set (`data/benchmark/edge.yaml`, #136, scored by #376) has its own rules, applied in
`judge_edge`, `check_pairs` and `swarm_vs_individual`, and is always reported in its own table.
"""

import json
import re
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml

from app.config import REPO_ROOT
from app.models.matchup import FighterRequest, Matchup
from app.models.simulation import FairFight, SimulationResult
from app.models.stats import StatSheet
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import run
from app.simulation.fair import fair_fight

HIGH_CONFIDENCE_MIN_PROB = 0.7
KEEP_RUNS = 5
RESULTS_FILE = REPO_ROOT / "docs" / "benchmark-results.md"
BENCHMARK_DIR = REPO_ROOT / "data" / "benchmark"
FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
MOCK_DIR = FIXTURE_DIR / "benchmark"
CONTRACT_DIR = FIXTURE_DIR / "contracts"

Group = Literal["obvious", "documented", "count", "swarm", "showcase", "mirror", "draw", "terrain"]
GROUPS: tuple[Group, ...] = ("obvious", "documented", "count")  # the main set
EDGE_GROUPS: tuple[Group, ...] = ("swarm", "showcase", "mirror", "draw", "terrain")  # edge.yaml

# The edge-case pass rules (docs/benchmark.md, "Edge-case set").
MIRROR_BAND = 0.1  # rule 2: |p - 0.5| at most this
DRAW_MIN_PROB = 0.5  # rule 3: a draw probability of at least this
PAIR_SLACK = 0.03  # rule 4: the bigger swarm's win share is at least the smaller's minus this
MODE_AGREEMENT = 0.03  # rule 5 (D-45): swarm and one-by-one win shares agree within this
ALWAYS_INDIVIDUAL = 10**9  # a head-count threshold no fight reaches


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
    edge: bool = False  # from edge.yaml: scored by its own rules and reported in its own table


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


def _edge_group(raw: dict[str, Any]) -> Group:
    """The group of an edge-case entry: one of the five edge groups, and an `edge-` id."""
    group = raw.get("group")
    if group not in EDGE_GROUPS:
        raise ValueError(
            f"an edge-case group must be one of {', '.join(EDGE_GROUPS)}, not {group!r}"
        )
    if not str(raw["id"]).startswith("edge-"):
        raise ValueError("an edge-case id must start with 'edge-'")
    return group


def parse_entry(raw: dict[str, Any], held_out: bool, edge: bool = False) -> Entry:
    """Turn one YAML mapping into an Entry, with a clear error if it is malformed."""
    try:
        fighters = [
            FighterRequest(
                entity=str(f["entity"]),
                count=int(f.get("count", 1)),
                variant=f.get("variant"),
                size_reference=f.get("size_reference"),
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
        if not edge and raw.get("group") in EDGE_GROUPS:
            raise ValueError(f"group {raw['group']!r} belongs in the edge-case file, not here")
        return Entry(
            id=str(raw["id"]),
            group=_edge_group(raw) if edge else _infer_group(raw, fair_range),
            matchup=Matchup(fighters=fighters, terrain=terrain, raw_text=names),
            expected_winner=winner,  # type: ignore[arg-type]
            confidence=_parse_confidence(raw.get("confidence", "medium")),
            fair_range=fair_range,
            source=str(raw.get("source", "")),
            held_out=held_out,
            edge=edge,
        )
    except (KeyError, ValueError, TypeError) as error:
        label = raw.get("id", "?") if isinstance(raw, dict) else "?"
        raise BenchmarkError(f"matchup {label!r} is malformed: {error}") from error


def load_entries(path: Path, held_out: bool, edge: bool = False) -> list[Entry]:
    """Read a matchup file (a list, or a mapping with a `matchups` list)."""
    if not path.exists():
        raise BenchmarkError(f"{path} does not exist yet (the benchmark set is built in task G07)")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = data.get("matchups", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise BenchmarkError(f"{path} must hold a list of matchups")
    return [parse_entry(item, held_out, edge) for item in items]


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
        suffix = f" (variant {fighter.variant!r})" if fighter.variant else ""
        raise BenchmarkError(f"no stat sheet for {fighter.entity!r}{suffix}")


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
    mode_gap: float | None = None  # edge swarm cases: |swarm - one by one| win share (D-45)


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


def reference_sheets(entry: Entry, sheets: SheetSource) -> list[StatSheet | None] | None:
    """The sheet of each fighter's `size_reference` entity (the showcase's duck-sized horses)."""
    found: list[StatSheet | None] = [
        sheets.get(FighterRequest(entity=f.size_reference, raw=f.size_reference))
        if f.size_reference
        else None
        for f in entry.matchup.fighters
    ]
    return found if any(sheet is not None for sheet in found) else None


def evaluate(entry: Entry, sheets: SheetSource, runs: int) -> Judged:
    """Simulate one matchup (and its fair-fight search for count cases) and judge it."""
    stat_sheets = [sheets.get(f) for f in entry.matchup.fighters]
    refs = reference_sheets(entry, sheets)
    result = run(entry.matchup, stat_sheets, runs=runs, reference_sheets=refs, explain=False)
    fair = fair_fight(entry.matchup, stat_sheets, result) if entry.fair_range else None
    return judge(entry, result, fair)


# --- The edge-case set (#136 entries, #376 scoring) ---------------------------------------


class WithLegends:
    """Adds the legends in data/seed/mythical.yaml to a sheet source (the showcase dragon).

    The main set leaves legends out because they have no right answer; the edge set only checks
    that the showcase battle behaves as planned, so it needs the dragon's sheet.
    """

    def __init__(self, inner: SheetSource) -> None:
        self.inner = inner

    def get(self, fighter: FighterRequest) -> StatSheet:
        try:
            return self.inner.get(fighter)
        except BenchmarkError:
            from app.research.mythical import build_mythical_sheet, find_creature  # lazy: layers

            creature = find_creature(fighter.entity)
            if creature is None:
                raise
            return build_mythical_sheet(creature)


def judge_edge(entry: Entry, result: SimulationResult) -> Judged:
    """Rules 1 to 3: the favorite rule, the mirror band, and the draw rule."""
    p0, p1 = result.win_prob
    win_pct = (round(p0 * 100, 1), round(p1 * 100, 1))
    if entry.group == "mirror":
        ok = abs(p0 - 0.5) <= MIRROR_BAND + 1e-9
        reason = f"side 0 wins {win_pct[0]}%, {'inside' if ok else 'outside'} 40 to 60%"
        return Judged(entry, result.outcome, None, win_pct, None, ok, reason)
    if entry.group == "draw":
        # A fight nobody can hurt anybody in ends as `no_contest` (win and draw shares 0), which is
        # the same "nobody wins" as a draw; the other draws are counted from the runs.
        harmless = result.outcome == "no_contest"
        ok = harmless or result.draw_prob >= DRAW_MIN_PROB
        reason = (
            "no contest: neither side can hurt the other, so nobody wins"
            if harmless
            else f"a draw {round(result.draw_prob * 100, 1)}% of the time, "
            f"{'at least' if ok else 'under'} 50%"
        )
        return Judged(entry, result.outcome, None, win_pct, None, ok, reason)
    return judge(entry, result, None)  # swarm, showcase, terrain: the same favorite rule


# `edge-swarm-01a` (about 150 per side) and `edge-swarm-01b` (about 300) are a pair.
def _pair_key(entry_id: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"(.*\d)([ab])", entry_id)
    return (match.group(1), match.group(2)) if match else None


def check_pairs(judged: Sequence[Judged]) -> list[Judged]:
    """Rule 4: the bigger swarm's win share is at least the smaller one's minus 0.03.

    The swarm side is the side with more fighters in the smaller (`a`) matchup. A pair with a
    skipped half is left alone. The check is added to the `b` row, which fails if it breaks.
    """
    by_key = {_pair_key(j.entry.id): j for j in judged if j.entry.group == "swarm"}
    out = []
    for j in judged:
        key = _pair_key(j.entry.id) if j.entry.group == "swarm" else None
        small = by_key.get((key[0], "a")) if key and key[1] == "b" else None
        if small is None or small.skipped or j.skipped:
            out.append(j)
            continue
        counts = [f.count for f in small.entry.matchup.fighters]
        side = counts.index(max(counts))
        low, high = small.win_pct[side], j.win_pct[side]
        ok = high / 100 >= low / 100 - PAIR_SLACK - 1e-9
        note = f"the bigger swarm wins {high}% against {low}% for the smaller"
        note += "" if ok else " (more than 3 points lower: more fighters should never hurt)"
        out.append(replace(j, passed=j.passed and ok, reason=f"{j.reason}; {note}"))
    return out


def swarm_vs_individual(entry: Entry, sheets: SheetSource, runs: int) -> float:
    """Rule 5 (D-45): how far apart side 0's win share is in swarm mode and one by one.

    Each mode is forced the way `scripts/validate_swarm.py` does it: swarm through the work rule
    (so the real step cap applies), one by one through a head-count threshold no fight reaches.
    Changes two module constants and restores them in `finally`; not safe to run in threads.
    """
    stat_sheets = [sheets.get(f) for f in entry.matchup.fighters]
    refs = reference_sheets(entry, sheets)
    saved = (c.SWARM_THRESHOLD, c.SWARM_WORK_BUDGET)
    shares = []
    try:
        for threshold, budget in ((saved[0], 0.0), (ALWAYS_INDIVIDUAL, float("inf"))):
            c.SWARM_THRESHOLD, c.SWARM_WORK_BUDGET = threshold, budget
            result = run(
                entry.matchup, stat_sheets, runs=runs, reference_sheets=refs, explain=False
            )
            shares.append(result.win_prob[0])
    finally:
        c.SWARM_THRESHOLD, c.SWARM_WORK_BUDGET = saved
    return abs(shares[0] - shares[1])


def evaluate_edge(
    entries: Sequence[Entry], sheets: SheetSource, runs: int, check_modes: bool = True
) -> list[Judged]:
    """Score the edge-case set with its own rules (a fighter with no sheet is skipped)."""
    sheets = WithLegends(sheets)
    judged: list[Judged] = []
    for entry in entries:
        try:
            stat_sheets = [sheets.get(f) for f in entry.matchup.fighters]
            refs = reference_sheets(entry, sheets)
            result = run(
                entry.matchup, stat_sheets, runs=runs, reference_sheets=refs, explain=False
            )
            judged.append(judge_edge(entry, result))
        except BenchmarkError as error:
            judged.append(Judged(entry, "skipped", None, (0.0, 0.0), None, False, str(error), True))
    judged = check_pairs(judged)
    if not check_modes:
        return judged
    for index, j in enumerate(judged):
        if j.entry.group != "swarm" or j.skipped:
            continue
        gap = swarm_vs_individual(j.entry, sheets, runs)
        ok = gap <= MODE_AGREEMENT + 1e-9
        note = f"swarm and one by one differ by {gap:.3f} ({'within' if ok else 'over'} 0.03)"
        judged[index] = replace(
            j, passed=j.passed and ok, reason=f"{j.reason}; {note}", mode_gap=gap
        )
    return judged


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
    edge: list[Judged] = field(default_factory=list)  # the edge-case set: its own table and rates

    def subset(self, held_out: bool | None = None, group: Group | None = None) -> list[Judged]:
        return [
            j
            for j in self.judged
            if (held_out is None or j.entry.held_out == held_out)
            and (group is None or j.entry.group == group)
        ]


def _parse_confidence(value: object) -> str:
    text = str(value).strip().lower()
    if text not in ("high", "medium"):
        raise ValueError(f"confidence must be high or medium, not {value!r}")
    return text


def rate(items: Sequence[Judged]) -> str:
    """Pass rate over the matchups that were scored; says how many were skipped (no sheet)."""
    scored = [j for j in items if not j.skipped]
    skipped = len(items) - len(scored)
    if not scored:
        return "n/a" if not skipped else f"n/a ({skipped} skipped, no sheet)"
    passed = sum(j.passed for j in scored)
    text = f"{passed}/{len(scored)} ({round(100 * passed / len(scored))}%)"
    return f"{text}, {skipped} skipped" if skipped else text


def current_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=10,
        )  # fmt: skip
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def render_edge(report: RunReport) -> list[str]:
    """The edge-case set's own rates and table. It never mixes into the main set's scores."""
    rows = report.edge
    if not rows:
        return []
    lines = [
        "",
        "### Edge-case set (reported separately)",
        "",
        'Judged by the rules in `docs/benchmark.md`, section "Edge-case set". These are not part '
        "of the tuning or held-out scores above, or of the 80% target.",
        "",
        "| Group | Pass rate |",
        "|---|---|",
    ]
    for group in EDGE_GROUPS:
        in_group = [j for j in rows if j.entry.group == group]
        if in_group:
            lines.append(f"| {group} | {rate(in_group)} |")
    lines.append(f"| all edge cases | {rate(rows)} |")
    lines += [
        "",
        "| Matchup | Group | Expected | Favorite | Win % (side 0 / 1) | Swarm v 1-by-1 | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    for j in rows:
        favorite = {None: "none"}.get(j.favorite, f"side {j.favorite}")
        wins = f"{j.win_pct[0]} / {j.win_pct[1]}"
        if j.skipped:
            favorite = wins = "—"
        expected = (
            f"side {j.entry.expected_winner}" if j.entry.expected_winner != "draw" else "draw"
        )
        gap = "—" if j.mode_gap is None else f"{j.mode_gap:.3f}"
        verdict = ("skipped" if j.skipped else "pass" if j.passed else "FAIL") + f" — {j.reason}"
        lines.append(
            f"| {j.entry.id} | {j.entry.group} | {expected} | {favorite} | {wins} | {gap} "
            f"| {verdict} |"
        )
    return lines


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
    lines += render_edge(report)
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
            wins = f"{j.win_pct[0]} / {j.win_pct[1]}"
            if j.skipped:  # nothing was simulated, so there is no favorite or win share to show
                favorite = wins = "—"
            expected = (
                f"side {j.entry.expected_winner}" if j.entry.expected_winner != "draw" else "draw"
            )
            fair = "—" if j.fair_count is None else str(j.fair_count)
            verdict = (
                "skipped" if j.skipped else "pass" if j.passed else "FAIL"
            ) + f" — {j.reason}"
            lines.append(
                f"| {j.entry.id} | {j.entry.group} | {expected} | {favorite} "
                f"| {wins} | {fair} | {verdict} |"
            )
    return "\n".join(lines) + "\n"


HEADER = (
    "# Benchmark results\n\n"
    "How often the simulator agrees with expert answers (see `docs/benchmark.md`). "
    "Newest run first; "
    f"the last {KEEP_RUNS} runs are kept. Generated by `backend/scripts/run_benchmark.py`.\n"
    "\n"
    "## Known limits (D-58)\n\n"
    "Three cases fail in the baseline and are recorded as known limits, not fixed (Mike's ruling "
    "on #304, recorded as D-58 in `docs/DECISIONS.md`). No sheet, expected range or constant was "
    "changed to make them pass, and a held-out case never changes any of them.\n\n"
    "- **cnt-05** (tuning), Roman legionary v grizzly: the fair count is 24 against an expected 2 "
    "to 8. The legionary keeps its sourced 150 N thrust (D-54). The gap is in the engine: "
    "`weapon_melee` does not change a fight (D-57), so a gladius is a 150 N push with no edge. A "
    "blade effect is post-MVP, with loadouts (D-56).\n"
    "- **cnt-04** (held-out), duck v horse: the fair count is 320 against an expected 20 to 300, "
    "about 7% outside. Reported as a fail. The duck's 30 N bite is a category estimate; a sourced "
    "one may replace it through normal sheet work, and then this is re-run.\n"
    "- **doc-05** (held-out), 4 gray wolves v a horse: the expected winner is the wolves, the "
    "simulator gives the horse. The source is about wolves preying on wild horses, not a duel, and "
    "the engine models a standing fight (no chase, exhaustion or pack hunting over time). The pack "
    "rule is not adjusted from a held-out case.\n\n"
    'None of the three is an "obvious" case, so the 80% held-out "obvious" target is unaffected.\n'
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
    edge: Sequence[Entry] = (),
    check_modes: bool = True,
) -> RunReport:
    """Score every matchup. With `tuning_only` the held-out set is neither run nor shown.

    The edge-case set (`edge`) is scored on its own rules and reported in its own table.
    """
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
    edge_judged = evaluate_edge(edge, sheets, runs, check_modes) if edge else []
    return RunReport(
        mode=mode,
        judged=judged,
        runtime_s=time.perf_counter() - clock,
        commit=current_commit(),
        started=started,
        tuning_only=tuning_only,
        edge=edge_judged,
    )
