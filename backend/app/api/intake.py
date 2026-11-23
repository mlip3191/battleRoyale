"""Intake routes (ARCHITECTURE §6): read a matchup, and take the answer to one question (D08)."""

import asyncio
import logging
import sqlite3
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from app.db.connection import connect
from app.db.intake_pending import PendingQuestion, restore_pending, save_pending, take_pending
from app.db.migrate import apply_migrations
from app.intake.answer import resolve_answer
from app.intake.parser import LONG_TEXT_CHARS, IntakeUnavailable, parse_matchup, too_long
from app.intake.steps import StepTimeout, run_attempt
from app.models.matchup import IntakeResult
from app.providers.base import ChatLLM
from app.providers.registry import get_intake_chat

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/intake", tags=["intake"])
EXPIRED_MESSAGE = (
    "That question has expired or was already answered. Please type your matchup again."
)
UNAVAILABLE_MESSAGE = "Our matchup desk is having trouble right now. Please try again in a moment."
# Whole-request limit for reading a matchup (Adam's live timings: median 6.9 s, max 19.4 s).
INTAKE_DEADLINE_SECONDS = 25.0
# Tries within the deadline: one retry when an attempt times out (#547).
ATTEMPTS = 2
# The first attempt's share of the deadline: 15 of 25 s, the same as one live intake call
# (Settings.intake_timeout_s), leaving 10 s for the retry. A share, so a patched deadline scales.
ATTEMPT_SHARE = 0.6


class IntakeRequest(BaseModel):
    """Body of POST /api/intake."""

    text: str = Field(max_length=2000)


class IntakeAnswer(BaseModel):
    """Body of POST /api/intake/{pending_id}/answer."""

    # Blank answers are refused (422) before the question is used up.
    answer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


# The app database with migrations applied; async so it opens on the thread that uses it.
async def get_db() -> AsyncIterator[sqlite3.Connection]:
    connection = connect()
    try:
        apply_migrations(connection)
        yield connection
    finally:
        connection.close()


# The chat model that reads matchups (intake's short timeout, #169); tests swap in a scripted one.
def get_chat() -> ChatLLM:
    return get_intake_chat()


Db = Annotated[sqlite3.Connection, Depends(get_db)]
Chat = Annotated[ChatLLM, Depends(get_chat)]


# Run the intake work under the deadline, trying again once if an attempt times out (#547): the
# first attempt gets ATTEMPT_SHARE of the deadline, the retry whatever is left, so two timeouts
# still end inside the deadline. Each timeout logs one line naming the slow step. An outage or a
# timeout becomes a plain 503, never a 500; an outage is not retried here (ask_model already
# retries a failed call).
async def within_deadline[T](work: Callable[[], Coroutine[Any, Any, T]]) -> T:
    loop = asyncio.get_running_loop()
    deadline = INTAKE_DEADLINE_SECONDS
    ends_at = loop.time() + deadline
    timed_out: StepTimeout | None = None
    for attempt in range(1, ATTEMPTS + 1):
        left = ends_at - loop.time()
        if left <= 0:
            break  # no time left for a retry
        limit = left if attempt == ATTEMPTS else min(left, deadline * ATTEMPT_SHARE)
        try:
            return await run_attempt(work, limit)
        except StepTimeout as error:
            timed_out = error
            logger.warning(
                "Intake attempt %d of %d timed out during %s.", attempt, ATTEMPTS, error.steps
            )
        except (IntakeUnavailable, TimeoutError) as error:
            raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE) from error
    raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE) from timed_out


# Read the user's text; when a question is needed, save it and hand back its pending_id.
@router.post("")
async def start_intake(body: IntakeRequest, db: Db, chat: Chat) -> IntakeResult:
    try:
        result = await within_deadline(lambda: parse_matchup(body.text, chat=chat))
    except HTTPException as error:
        if error.status_code == 503 and len(body.text.strip()) > LONG_TEXT_CHARS:
            return too_long()  # the same long text would fail again: ask for less (#362)
        raise
    if result.status != "clarify" or not result.question:
        return result
    pending = PendingQuestion(body.text.strip(), result.question, result.options)
    return result.model_copy(update={"pending_id": save_pending(db, pending)})


# Take the answer to the one question; the reply is never another question.
@router.post("/{pending_id}/answer")
async def answer_intake(pending_id: str, body: IntakeAnswer, db: Db, chat: Chat) -> IntakeResult:
    pending = take_pending(db, pending_id)
    if pending is None:
        raise HTTPException(status_code=404, detail=EXPIRED_MESSAGE)
    try:
        return await within_deadline(lambda: resolve_answer(pending, body.answer, chat))
    except HTTPException:
        restore_pending(db, pending_id, pending)  # not the user's fault: keep the question
        raise
