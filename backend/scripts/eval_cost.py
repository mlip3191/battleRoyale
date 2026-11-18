"""Cost and speed section of the live AI evaluation (M09 part 3, #51).

Imported by scripts/evaluate_ai.py; live mode only, never in CI. The five showcase battles run
twice through the real pipeline in this process: a fresh run, then a repeat that the
repeat-battle cache should answer. Every course endpoint call goes through
providers/live/http.py's one request function, so wrapping it counts calls by service without
touching the app. The scoring and Markdown helpers are plain functions, tested offline.
"""

import asyncio
import math
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# A whole battle's overall deadline here, beyond the app's own stage budgets.
BATTLE_LIMIT_S = 300.0


@dataclass
class BattleRun:
    """One battle's timings and endpoint calls."""

    title: str
    repeat: bool
    status: str = "?"
    verdict_s: float | None = None
    show_s: float | None = None
    cached: bool = False
    calls: Counter[str] = field(default_factory=Counter)


# The p-th percentile by the nearest-rank method (p in 0-100), or None for no values.
def percentile(values: list[float], p: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


# "n.n s", or "-" when there's no value.
def secs(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f} s"


# The cost and speed section's Markdown.
def cost_markdown(runs: list[BattleRun], seconds: float) -> str:
    services = sorted({s for r in runs for s in r.calls})
    head = "| Battle | Run | Status | Verdict | Full show | " + " | ".join(services) + " |"
    rows = [head, "|---|---|---|---|---|" + "---|" * len(services)]
    for r in runs:
        calls = " | ".join(str(r.calls[s]) for s in services)
        run = "repeat" + (" (cached)" if r.cached else "") if r.repeat else "fresh"
        rows.append(
            f"| {r.title} | {run} | {r.status} | {secs(r.verdict_s)} | {secs(r.show_s)} | {calls} |"
        )
    out = [
        f"The {len(runs) // 2} showcase battles ran twice through the real pipeline in this "
        f"process ({seconds:.0f} s): a fresh run, then a repeat that the repeat-battle cache "
        "should answer. Times start when the battle starts; intake (reading the typed matchup, "
        "about 8 s a reading in section 4) comes before that and isn't included. Calls are "
        "course endpoint calls, each counted once however many times it was retried. Images "
        "came from the local media cache, and voice and music weren't made (no live voice or "
        "music service is wired up yet), so their calls and time aren't in these numbers. The "
        "repeat-battle cache skips only the simulation: the show is written again, so its "
        "time varies with the live model.",
        "",
        *rows,
        "",
        "| Measure | Fresh | Repeat |",
        "|---|---|---|",
    ]
    for label, attr in (("time to verdict", "verdict_s"), ("time to full show", "show_s")):
        for p, name in ((50, "Median"), (90, "90th percentile")):
            cells = []
            for repeat in (False, True):
                values = [getattr(r, attr) for r in runs if r.repeat == repeat]
                cells.append(secs(percentile([v for v in values if v is not None], p)))
            out.append(f"| {name} {label} | {cells[0]} | {cells[1]} |")
    fresh = [r for r in runs if not r.repeat]
    for service in services:
        mean = sum(r.calls[service] for r in fresh) / max(len(fresh), 1)
        out.append(f"| Calls per battle: {service} | {mean:.1f} | |")
    repeats = [r for r in runs if r.repeat]
    hits = sum(r.cached for r in repeats)
    out.append(f"| Repeat battles answered from the cache | | {hits} of {len(repeats)} |")
    return "\n".join(out)


# Run the showcase battles fresh and then again, counting calls and timing each (live).
async def run_cost() -> str:
    from run_showcase import SHOWCASE

    from app.models.matchup import Matchup
    from app.pipeline import orchestrator
    from app.pipeline.store import BattleStore
    from app.providers.live import http

    # A database of its own: the repeat-battle cache only reads saved battles, and this keeps
    # them out of the app's own database.
    scratch = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # Windows may hold the file
    store = BattleStore(db_path=Path(scratch.name) / "eval_battles.db")
    verdict_at: dict[str, float] = {}
    original_update = store.update

    # Note when the verdict is saved, the moment a viewer would see the result.
    async def update(battle_id: str, **fields: Any) -> None:
        if "result" in fields:
            verdict_at.setdefault(battle_id, time.perf_counter())
        await original_update(battle_id, **fields)

    store.update = update  # type: ignore[method-assign]
    calls: Counter[str] = Counter()
    original_request = http._request_json

    async def counted(method: str, provider: str, *args: Any, **kwargs: Any) -> Any:
        calls[provider] += 1
        return await original_request(method, provider, *args, **kwargs)

    http._request_json = counted  # type: ignore[assignment]
    runs: list[BattleRun] = []
    started_all = time.perf_counter()
    try:
        for repeat in (False, True):
            for title, data in SHOWCASE:
                run = BattleRun(title, repeat)
                calls.clear()
                record = await store.create(Matchup.model_validate(data))
                started = time.perf_counter()
                try:
                    await asyncio.wait_for(
                        orchestrator.run_battle(record.battle_id, store), BATTLE_LIMIT_S
                    )
                except TimeoutError:
                    run.status = "timed out"
                run.show_s = time.perf_counter() - started
                if record.battle_id in verdict_at:
                    run.verdict_s = verdict_at[record.battle_id] - started
                final = await store.get(record.battle_id)
                if final is not None:
                    run.status = run.status if run.status == "timed out" else final.status
                    simulate = next((s for s in final.stages if s.stage == "simulate"), None)
                    run.cached = simulate is not None and simulate.detail == orchestrator.CACHED
                run.calls = Counter(calls)
                runs.append(run)
    finally:
        http._request_json = original_request  # type: ignore[assignment]
        scratch.cleanup()
    return cost_markdown(runs, time.perf_counter() - started_all)
