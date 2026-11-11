"""Intake routes (ARCHITECTURE §6): read a matchup, and take the answer to one question (D08)."""

import sqlite3
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from app.db.connection import connect
from app.db.intake_pending import PendingQuestion, save_pending, take_pending
from app.db.migrate import apply_migrations
from app.intake.answer import resolve_answer
from app.intake.parser import parse_matchup
from app.models.matchup import IntakeResult
from app.providers.base import ChatLLM
from app.providers.registry import get_provider

router = APIRouter(prefix="/api/intake", tags=["intake"])
EXPIRED_MESSAGE = (
    "That question has expired or was already answered. Please type your matchup again."
)


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


# The chat model that reads matchups; tests swap in a scripted one.
def get_chat() -> ChatLLM:
    return get_provider("chat")


Db = Annotated[sqlite3.Connection, Depends(get_db)]
Chat = Annotated[ChatLLM, Depends(get_chat)]


# Read the user's text; when a question is needed, save it and hand back its pending_id.
@router.post("")
async def start_intake(body: IntakeRequest, db: Db, chat: Chat) -> IntakeResult:
    result = await parse_matchup(body.text, chat=chat)
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
    return await resolve_answer(pending, body.answer, chat)
