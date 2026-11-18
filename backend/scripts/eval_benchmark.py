"""Benchmark section of the live AI evaluation (M09 part 4, #51).

The F07 benchmark (scripts/run_benchmark.py) checks the simulator against expert answers. Here it
runs on one commit with the hand-verified seed sheets once, and with research-only sheets twice
(the live models aren't fully repeatable), so the two can be compared side by side. It reuses F07's
code and writes nothing to docs/benchmark-results.md.
"""

import asyncio
import time
from collections.abc import Sequence

from app.simulation import benchmark as bm

RESEARCH_PASSES = 2
# One research pass builds every benchmark fighter live; stop a hung pass instead of waiting.
BUILD_LIMIT_S = 1800.0


# "pass", "FAIL" or "skipped" for one matchup in one run.
def verdict(judged: bm.Judged | None) -> str:
    if judged is None or judged.skipped:
        return "skipped"
    return "pass" if judged.passed else "FAIL"


# The markdown section: pass rates per sheet source, then the matchups whose result differs.
def benchmark_markdown(seed: bm.RunReport, research: Sequence[bm.RunReport], seconds: float) -> str:
    runs = [seed, *research]
    heads = ["Seed sheets", *(f"Research-only, run {i}" for i in range(1, len(research) + 1))]
    out = [
        f"The F07 benchmark ran on one commit with the hand-verified seed sheets, then "
        f"{len(research)} times with sheets built by the research pipeline alone ({seconds:.0f} s "
        "in all). The simulation is seeded, so seed-sheet results repeat exactly; research-only "
        "sheets come from the live models, which aren't fully repeatable. A held-out matchup was "
        "never used to change a constant. Three known limits fail by design (D-58; see "
        "`docs/benchmark-results.md`).",
        "",
        "| Set | " + " | ".join(heads) + " |",
        "|---|" + "---|" * len(heads),
    ]
    for label, held, group in [
        ("**Held-out**", True, None),
        *((f"Held-out: {g}", True, g) for g in bm.GROUPS),
        ("Tuning", False, None),
    ]:
        cells = [bm.rate(run.subset(held, group)) for run in runs]
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    by_id = [{j.entry.id: j for j in run.judged} for run in runs]
    differ = [
        j.entry for j in seed.judged if len({verdict(index.get(j.entry.id)) for index in by_id}) > 1
    ]
    out += ["", "Matchups whose result depends on the sheets or the run:", ""]
    if not differ:
        out.append("- none: every matchup got the same result in every run.")
        return "\n".join(out)
    out += [
        "| Matchup | Set | Group | " + " | ".join(heads) + " |",
        "|---|---|---|" + "---|" * len(heads),
    ]
    for entry in differ:
        cells = [verdict(index.get(entry.id)) for index in by_id]
        kind = "held-out" if entry.held_out else "tuning"
        out.append(f"| {entry.id} | {kind} | {entry.group} | " + " | ".join(cells) + " |")
    return "\n".join(out)


# Build research-only sheets for every benchmark fighter, live (F07's builder, awaited directly).
async def research_source(entries: Sequence[bm.Entry]) -> bm.SheetSource:
    from app.db.connection import connect
    from app.db.migrate import apply_migrations
    from app.providers.registry import get_provider
    from app.research.benchmark_sheets import research_sheets

    providers = (get_provider("chat"), get_provider("embedder"), get_provider("reranker"))
    connection = connect()
    try:
        apply_migrations(connection)
        if connection.execute("SELECT 1 FROM chunks LIMIT 1").fetchone() is None:
            raise bm.BenchmarkError("the knowledge base is empty: run `npm run ingest` first")
        return await asyncio.wait_for(
            research_sheets(entries, connection, providers), BUILD_LIMIT_S
        )
    finally:
        connection.close()


# Run the benchmark with seed sheets once and research-only sheets RESEARCH_PASSES times (live).
async def run_benchmark_section() -> str:
    from app.config import get_settings

    tuning = bm.load_entries(bm.BENCHMARK_DIR / "matchups.yaml", False)
    held = bm.load_entries(bm.BENCHMARK_DIR / "heldout.yaml", True)
    runs = get_settings().sim_runs
    started = time.perf_counter()
    seed = bm.run_benchmark(bm.seed_sheets(), "seed", tuning, held, runs)
    research = []
    for _ in range(RESEARCH_PASSES):
        sheets = await research_source([*tuning, *held])
        research.append(bm.run_benchmark(sheets, "research", tuning, held, runs))
    return benchmark_markdown(seed, research, time.perf_counter() - started)
