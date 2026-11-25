"""Which intake step is running, so a timed-out attempt can name the slow one (#547).

Each step marks itself with @intake_step. Outside run_attempt marking does nothing, so the same
functions work unchanged elsewhere (the pipeline's own safety check, direct calls in tests).
Only step names are kept: never the user's text, messages, URLs or hosts.
"""

import asyncio
import functools
from collections.abc import Awaitable, Callable, Coroutine
from contextvars import ContextVar
from typing import Any

PARSE = "parse"
SAFETY_CLASSIFY = "safety classify"
WIKIDATA = "Wikidata"
STEP_ORDER = (PARSE, SAFETY_CLASSIFY, WIKIDATA)

# The steps in progress in the current attempt (a shared list, so tasks started inside the
# attempt add to it too); None outside an attempt.
_running: ContextVar[list[str] | None] = ContextVar("intake_steps_running", default=None)


class StepTimeout(TimeoutError):
    """One intake attempt ran out of time; `steps` names what was in progress, nothing else."""

    def __init__(self, steps: str) -> None:
        super().__init__(f"Intake timed out during {steps}.")
        self.steps = steps


# Mark an async function as the named intake step while it runs.
def intake_step[**P, T](
    name: str,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Coroutine[Any, Any, T]]]:
    def mark(func: Callable[P, Awaitable[T]]) -> Callable[P, Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def marked(*args: P.args, **kwargs: P.kwargs) -> T:
            running = _running.get()
            if running is None:
                return await func(*args, **kwargs)
            running.append(name)
            try:
                return await func(*args, **kwargs)
            finally:
                running.remove(name)

        return marked

    return mark


# "parse", "parse and safety classify", ...; in a fixed order so the log line is stable.
def describe_steps(running: list[str]) -> str:
    names = [step for step in STEP_ORDER if step in running]
    return " and ".join(names) if names else "no named step"


# Run one attempt for at most `limit` seconds. On time-out, note the steps still running, then
# cancel the work and raise StepTimeout naming them. The work never outlives the call.
async def run_attempt[T](work: Callable[[], Coroutine[Any, Any, T]], limit: float) -> T:
    running: list[str] = []
    token = _running.set(running)
    try:
        task = asyncio.create_task(work())  # copies the context, so its steps land in `running`
    finally:
        _running.reset(token)
    try:
        done, _ = await asyncio.wait({task}, timeout=limit)
        if task in done:
            return task.result()
        raise StepTimeout(describe_steps(running))  # named before the cancel unwinds the steps
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
