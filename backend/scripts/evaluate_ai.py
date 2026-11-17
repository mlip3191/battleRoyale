"""Live AI evaluation (M09, #51): measure the AI parts against the real course endpoints.

Run by hand (never in CI), from the repo root, with PROVIDER_MODE=live in .env:
  uv run --directory backend python scripts/evaluate_ai.py --sections intake,safety,retrieval

Each run measures the sections it is given and rewrites only those sections of
docs/evaluation.md, keeping the others, with the run date and commit at the top. The whole file
is scanned for hosts and keys before it is written; if any are left, nothing is written.
Exit codes: 0 = written; 2 = a section could not run; 3 = redaction failed; 4 = mock mode.
"""

import argparse
import asyncio
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

SCRIPTS = Path(__file__).resolve().parent
BACKEND = SCRIPTS.parent
sys.path[:0] = [str(BACKEND), str(SCRIPTS)]

from app.config import get_settings  # noqa: E402

REPO = BACKEND.parent
OUTPUT = REPO / "docs" / "evaluation.md"
INTAKE_CASES = BACKEND / "tests" / "fixtures" / "providers" / "intake_cases.yaml"
RETRIEVAL_CASES = BACKEND / "tests" / "fixtures" / "retrieval_cases.yaml"
# Section order in the document: (key, heading). The summary and limitations are written by hand.
SECTIONS = [
    ("summary", "Summary"),
    ("extraction", "1. Extraction accuracy"),
    ("retrieval", "2. Retrieval"),
    ("coverage", "3. Coverage on new fighters"),
    ("intake", "4. Intake accuracy"),
    ("safety", "5. Safety"),
    ("benchmark", "6. Benchmark: seed vs research-only sheets"),
    ("cost", "7. Cost and speed"),
    ("limitations", "What this means and limitations"),
]
RUNNABLE = ("intake", "safety", "retrieval")
NOT_RUN = "_Not measured yet._"
FIELDS = ("entity", "count", "terrain")


@dataclass
class IntakeScore:
    """Exact-match counts for the intake phrasings the live model was asked to read."""

    scored: int = 0
    skipped: int = 0
    """Cases built around broken model output, which a live run can't reproduce."""
    status: int = 0
    exact: dict[str, list[int]] = field(default_factory=lambda: {f: [0, 0] for f in FIELDS})
    """Per field: [right, checked]."""
    full: int = 0
    misses: list[str] = field(default_factory=list)


# True when a case's canned replies include broken output (a plain string), so it tests recovery.
def tests_broken_output(case: dict[str, Any]) -> bool:
    return any(isinstance(reply, str) for reply in case.get("replies", []))


# Compare one live intake result with a case's expectations on status, entity, count, terrain.
def score_intake_case(score: IntakeScore, case: dict[str, Any], result: Any) -> None:
    if tests_broken_output(case):
        score.skipped += 1
        return
    expect, matchup = case["expect"], getattr(result, "matchup", None)
    score.scored += 1
    right = result is not None and result.status == expect["status"]
    score.status += right
    checks: list[tuple[str, Any, Any]] = []
    if "terrain" in expect:
        checks.append(("terrain", expect["terrain"], matchup.terrain.value if matchup else None))
    for i, want in enumerate(expect.get("fighters", [])):
        got = matchup.fighters[i] if matchup and i < len(matchup.fighters) else None
        checks += [(f, want[f], getattr(got, f, None)) for f in ("entity", "count") if f in want]
    for name, want, got in checks:
        score.exact[name][1] += 1
        score.exact[name][0] += want == got
        if want != got:
            right = False
            score.misses.append(f"{case['name']}: {name} expected {want!r}, got {got!r}")
    if result is not None and result.status != expect["status"]:
        score.misses.append(
            f"{case['name']}: status expected {expect['status']}, got {result.status}"
        )
    score.full += right


# A share as "n/d (p%)".
def share(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d:.0%})" if d else "n/a"


# The intake section's Markdown.
def intake_markdown(score: IntakeScore, seconds: float) -> str:
    rows = ["| Measure | Result |", "|---|---|"]
    rows.append(
        f"| Status matches (ok / clarify / blocked) | {share(score.status, score.scored)} |"
    )
    rows += [f"| {f.capitalize()} exact | {share(*score.exact[f])} |" for f in FIELDS]
    rows.append(f"| **Every checked field right** | **{share(score.full, score.scored)}** |")
    out = [
        f"The live chat model read the {score.scored} A02 phrasings in "
        f"`tests/fixtures/providers/intake_cases.yaml` ({seconds:.0f} s). "
        f"{score.skipped} cases that test recovery from broken model output were left out, "
        "because a live model can't be made to send it.",
        "",
        *rows,
    ]
    if score.misses:
        out += ["", "Misses:", *[f"- {miss}" for miss in score.misses]]
    return "\n".join(out)


# Split an existing document into its sections, by the markers this script writes.
def read_sections(text: str) -> dict[str, str]:
    pattern = r"<!-- section:(\w+) -->\n(.*?)\n<!-- /section -->"
    return {key: body.strip() for key, body in re.findall(pattern, text, flags=re.DOTALL)}


# The whole document: header, then every section (new results win over kept ones).
def render(kept: dict[str, str], new: dict[str, str], run_date: str, commit: str) -> str:
    sections = {**kept, **new}
    measured = ", ".join(heading for key, heading in SECTIONS if key in new)
    out = [
        "# Live AI evaluation (M09)",
        "",
        "Does the GenAI actually work? Numbers from the real course endpoints, made by "
        "`backend/scripts/evaluate_ai.py`. Hosts and keys are never written here.",
        "",
        f"Last run: {run_date} on commit `{commit}` (measured: {measured}).",
    ]
    for key, heading in SECTIONS:
        body = sections.get(key, NOT_RUN)
        out += ["", f"## {heading}", "", f"<!-- section:{key} -->", body, "<!-- /section -->"]
    return "\n".join(out) + "\n"


# Run the live intake parser on every A02 phrasing.
async def run_intake() -> str:
    from app.intake.parser import parse_matchup
    from app.providers.live.chat import LiveChatLLM
    from app.providers.registry import service_config

    settings = get_settings()
    chat = LiveChatLLM(service_config("chat", settings), settings)
    cases = yaml.safe_load(INTAKE_CASES.read_text(encoding="utf-8"))
    score, started = IntakeScore(), time.perf_counter()
    for case in cases:
        result = None if tests_broken_output(case) else await parse_matchup(case["text"], chat=chat)
        score_intake_case(score, case, result)
    return intake_markdown(score, time.perf_counter() - started)


# Run the live safety eval (A04's 50-case set plus injections) and summarize it.
async def run_safety() -> str:
    import tempfile

    import httpx
    import safety_eval as se

    from app.intake import parser
    from app.providers.live.chat import LiveChatLLM
    from app.providers.registry import service_config
    from app.safety import wikidata

    settings = get_settings()
    chat = LiveChatLLM(service_config("chat", settings), settings)
    recorder = se.Recorder()
    parser.blocked_result = recorder.blocked_result  # type: ignore[assignment]
    parser.check_parsed_sides = recorder.check_parsed_sides  # type: ignore[assignment]
    cases = se.load_cases()
    with tempfile.TemporaryDirectory() as tmp:
        cache = wikidata.WikidataCache(Path(tmp) / "eval.db")
        async with httpx.AsyncClient(timeout=wikidata.TIMEOUT_S) as client:
            se.use_live_wikidata(wikidata.LiveWikidataLookup(client), cache)
            started = time.perf_counter()
            outcomes = [await se.run_case(case, chat, recorder) for case in cases]
            seconds = time.perf_counter() - started
    lines = se.summary(outcomes, seconds)[2:] + ["", *se.injection_pairs(outcomes)]
    misses = [
        f"- {o.case.id} {o.case.text!r}: expected {o.expected}, got {o.got}"
        for o in outcomes
        if not o.right
    ]
    return "\n".join(
        [
            f"All {len(cases)} cases in `tests/fixtures/safety_cases.yaml` through the live gate "
            "(`scripts/safety_eval.py` has the per-case table).",
            "",
            "```text",
            *[line.removeprefix("## ") for line in lines],
            "```",
            "",
            "Misses:" if misses else "No misses.",
            *misses,
        ]
    )


# Score retrieval hit@5 on G03's cases.
async def run_retrieval() -> str:
    from app.db.connection import connect
    from app.db.migrate import apply_migrations
    from app.models.stats import StatName
    from app.providers.registry import get_provider
    from app.research.evidence_check import normalize_text
    from app.research.retrieve import evidence_for

    cases = yaml.safe_load(RETRIEVAL_CASES.read_text(encoding="utf-8"))["cases"]
    embedder, reranker = get_provider("embedder"), get_provider("reranker")
    connection, ranks = connect(), []
    try:
        apply_migrations(connection)
        for case in cases:
            found = await evidence_for(
                connection, embedder, reranker, case["fighter_id"], StatName(case["stat"])
            )
            phrase = normalize_text(case["phrase"])
            hit = [i for i, p in enumerate(found, 1) if phrase in normalize_text(p.text)]
            ranks.append(hit[0] if hit else None)
    finally:
        connection.close()
    hits = [r for r in ranks if r is not None]
    top1 = sum(r == 1 for r in hits)
    missed = [
        f"- {c['fighter_id']} {c['stat']}: {c['phrase']!r}"
        for c, r in zip(cases, ranks, strict=True)
        if r is None
    ]
    return "\n".join(
        [
            f"{len(cases)} cases from `tests/fixtures/retrieval_cases.yaml`, against the local "
            "knowledge base (run `npm run ingest` first).",
            "",
            "| Measure | Result |",
            "|---|---|",
            f"| hit@5 (target 80%) | {share(len(hits), len(cases))} |",
            f"| Ranked first | {share(top1, len(cases))} |",
            "",
            *(["Not found in the top 5:", *missed] if missed else ["Every case was found."]),
        ]
    )


RUNNERS = {"intake": run_intake, "safety": run_safety, "retrieval": run_retrieval}


# The short commit hash, or "unknown" outside a git checkout.
def current_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=REPO,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# Run the chosen sections live and rewrite them in docs/evaluation.md; return the exit code.
async def main(argv: list[str] | None = None) -> int:
    from smoke_providers import redact

    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument(
        "--sections", default=",".join(RUNNABLE), help=f"any of {', '.join(RUNNABLE)}"
    )
    chosen = [s.strip() for s in args.parse_args(argv).sections.split(",") if s.strip()]
    if unknown := [s for s in chosen if s not in RUNNERS]:
        print(f"Unknown section(s): {', '.join(unknown)}. Choose from {', '.join(RUNNABLE)}.")
        return 2
    settings = get_settings()
    if settings.provider_mode != "live":
        print("This evaluation measures the live endpoints. Set PROVIDER_MODE=live in .env.")
        return 4
    new, failed = {}, []
    for key in chosen:
        print(f"Running {key}...", file=sys.stderr, flush=True)
        try:
            new[key] = await RUNNERS[key]()
        except Exception as error:  # noqa: BLE001 - reported by type only, never with details
            failed.append(f"{key} ({type(error).__name__})")
    kept = read_sections(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    text, remaining = redact(
        render(kept, new, date.today().isoformat(), current_commit()), settings
    )
    if remaining:
        print(f"Redaction scan: {remaining} secret value(s) still present. Nothing written.")
        return 3
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(REPO)}: {', '.join(new) or 'no new sections'}.")
    if failed:
        print(f"Could not run: {', '.join(failed)}.")
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
