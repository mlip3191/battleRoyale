"""The intake routes on a scripted chat model: ok, one question then ok, and expiry (D08)."""

import json
import sqlite3
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.intake import EXPIRED_MESSAGE, get_chat, get_db
from app.config import Settings
from app.db.connection import connect
from app.db.intake_pending import (
    MAX_QUESTION_CHARS,
    PENDING_TTL_SECONDS,
    PendingQuestion,
    save_pending,
    take_pending,
)
from app.db.migrate import apply_migrations
from app.intake.answer import START_OVER, merge_answer
from app.intake.parser import COMMON_KIND_NOTE, INPUT_END, INPUT_START
from app.main import create_app
from app.providers.base import ChatMessage


def side(raw: str, entity: str) -> dict[str, Any]:
    return {"raw": raw, "entity": entity}


WHICH_BEAR = {
    "question": "Which bear?",
    "options": ["grizzly bear", "polar bear", "black bear"],
}
VAGUE = {
    "fighters": [side("bear", "bear"), side("wolf", "wolf")],
    "needs_clarification": WHICH_BEAR,
}
# What the scripted model replies for each text it is shown.
REPLIES: dict[str, Any] = {
    "a grizzly bear vs a gray wolf": {
        "fighters": [side("a grizzly bear", "grizzly bear"), side("a gray wolf", "gray wolf")]
    },
    "bear vs wolf": VAGUE,
    "grizzly bear vs wolf": {
        "fighters": [side("grizzly bear", "grizzly bear"), side("wolf", "wolf")]
    },
    "bear vs wolf (the big one)": VAGUE,
    "bear vs wolf (gibberish)": "not json",
}


class ScriptedChat:
    """Stand-in chat model that replies from REPLIES and remembers each text it saw."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    async def complete(self, messages: list[ChatMessage], **_: Any) -> str:
        content = messages[1]["content"]
        text = content.removeprefix(f"{INPUT_START}\n").removesuffix(f"\n{INPUT_END}")
        self.texts.append(text)
        reply = REPLIES[text]
        return reply if isinstance(reply, str) else json.dumps(reply)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "app.db"


@pytest.fixture
def chat() -> ScriptedChat:
    return ScriptedChat()


# The app with a throwaway database and the scripted chat model.
@pytest.fixture
def client(settings: Settings, db_path: Path, chat: ScriptedChat) -> Iterator[TestClient]:
    async def temp_db() -> AsyncIterator[sqlite3.Connection]:
        connection = connect(db_path)
        apply_migrations(connection)
        yield connection
        connection.close()

    app = create_app(settings, frontend_dist=db_path.parent / "missing")
    app.dependency_overrides[get_db] = temp_db
    app.dependency_overrides[get_chat] = lambda: chat
    with TestClient(app) as test_client:
        yield test_client


def pending_rows(db_path: Path) -> int:
    connection = connect(db_path)
    try:
        return connection.execute("SELECT COUNT(*) FROM intake_pending").fetchone()[0]
    finally:
        connection.close()


# Ask about "bear vs wolf" and return the question's pending_id.
def ask_which_bear(client: TestClient) -> str:
    body = client.post("/api/intake", json={"text": "bear vs wolf"}).json()
    assert body["status"] == "clarify" and body["question"] == "Which bear?"
    assert body["options"] == WHICH_BEAR["options"]
    return body["pending_id"]


def test_ok_on_the_first_try_stores_nothing(client: TestClient, db_path: Path) -> None:
    response = client.post("/api/intake", json={"text": "a grizzly bear vs a gray wolf"})
    body = response.json()
    assert response.status_code == 200 and body["status"] == "ok"
    assert [f["entity"] for f in body["matchup"]["fighters"]] == ["grizzly bear", "gray wolf"]
    assert body["pending_id"] is None and pending_rows(db_path) == 0


def test_one_clarification_then_ok(client: TestClient, db_path: Path, chat: ScriptedChat) -> None:
    pending_id = ask_which_bear(client)
    assert pending_rows(db_path) == 1
    body = client.post(f"/api/intake/{pending_id}/answer", json={"answer": "grizzly bear"}).json()
    assert body["status"] == "ok" and body["question"] is None and body["pending_id"] is None
    assert body["matchup"]["fighters"][0]["entity"] == "grizzly bear"
    assert chat.texts == ["bear vs wolf", "grizzly bear vs wolf"]
    assert pending_rows(db_path) == 0


def test_still_vague_after_the_answer_adds_an_assumption_and_is_ok(
    client: TestClient, db_path: Path, chat: ScriptedChat
) -> None:
    pending_id = ask_which_bear(client)
    body = client.post(f"/api/intake/{pending_id}/answer", json={"answer": "the big one"}).json()
    assert body["status"] == "ok"
    assert COMMON_KIND_NOTE in body["matchup"]["assumptions"]
    assert body["matchup"]["fighters"][0]["entity"] == "bear"
    # A second question is never asked: no question, no new pending row, one re-parse only.
    assert body["question"] is None and body["options"] == [] and body["pending_id"] is None
    assert pending_rows(db_path) == 0 and len(chat.texts) == 2


def test_an_unusable_answer_ends_with_a_message_not_a_question(client: TestClient) -> None:
    pending_id = ask_which_bear(client)
    body = client.post(f"/api/intake/{pending_id}/answer", json={"answer": "gibberish"}).json()
    assert body["status"] == "blocked" and body["message"] == START_OVER
    assert body["blocked_reason"] == "nonsense"
    assert body["question"] is None and body["pending_id"] is None


def test_unknown_and_used_pending_ids_return_404(client: TestClient) -> None:
    response = client.post("/api/intake/p-nope/answer", json={"answer": "grizzly bear"})
    assert response.status_code == 404 and response.json()["detail"] == EXPIRED_MESSAGE
    pending_id = ask_which_bear(client)
    assert client.post(
        f"/api/intake/{pending_id}/answer", json={"answer": "grizzly bear"}
    ).is_success
    again = client.post(f"/api/intake/{pending_id}/answer", json={"answer": "polar bear"})
    assert again.status_code == 404


def test_pending_question_expires_after_30_minutes(client: TestClient, db_path: Path) -> None:
    assert PENDING_TTL_SECONDS == 30 * 60
    question = PendingQuestion("bear vs wolf", "Which bear?", ["grizzly bear", "polar bear"])
    connection = connect(db_path)
    apply_migrations(connection)
    old = save_pending(connection, question, now=time.time() - PENDING_TTL_SECONDS - 1)
    fresh = save_pending(connection, question, now=time.time() - PENDING_TTL_SECONDS + 60)
    connection.close()
    response = client.post(f"/api/intake/{old}/answer", json={"answer": "grizzly bear"})
    assert response.status_code == 404 and response.json()["detail"] == EXPIRED_MESSAGE
    assert client.post(f"/api/intake/{fresh}/answer", json={"answer": "grizzly bear"}).is_success


@pytest.mark.parametrize("answer", ["   ", "x" * 201])
def test_blank_or_long_answers_get_422_and_keep_the_question(
    client: TestClient, answer: str
) -> None:
    pending_id = ask_which_bear(client)
    response = client.post(f"/api/intake/{pending_id}/answer", json={"answer": answer})
    assert response.status_code == 422
    retry = client.post(f"/api/intake/{pending_id}/answer", json={"answer": "grizzly bear"})
    assert retry.status_code == 200 and retry.json()["status"] == "ok"


def test_text_over_2000_characters_gets_422(client: TestClient, chat: ScriptedChat) -> None:
    response = client.post("/api/intake", json={"text": "a" * 2001})
    assert response.status_code == 422 and chat.texts == []


def test_saving_purges_expired_questions_and_caps_the_question(db_path: Path) -> None:
    connection = connect(db_path)
    apply_migrations(connection)
    now = time.time()
    old = save_pending(
        connection, PendingQuestion("a", "Q?", []), now=now - PENDING_TTL_SECONDS - 1
    )
    long_question = PendingQuestion("bear vs wolf", "Which? " * 200, ["grizzly bear"])
    fresh = save_pending(connection, long_question, now=now)
    count = connection.execute("SELECT COUNT(*) FROM intake_pending").fetchone()[0]
    taken = take_pending(connection, fresh, now=now)
    connection.close()
    assert count == 1 and old != fresh  # the expired row went when the new one was saved
    assert len(fresh) == len("p-") + 32  # a full uuid, not a shortened one
    assert taken is not None and len(taken.question) == MAX_QUESTION_CHARS


def test_both_routes_are_in_openapi(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/api/intake", "/api/intake/{pending_id}/answer"):
        reply = paths[path]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert reply == {"$ref": "#/components/schemas/IntakeResult"}


@pytest.mark.parametrize(
    ("original", "answer", "merged"),
    [
        ("bear vs wolf", "grizzly bear", "grizzly bear vs wolf"),
        ("3 bears vs a wolf", "a polar bear", "3 polar bears vs a wolf"),
        ("3 bears vs a wolf", "3 grizzly bears", "3 grizzly bears vs a wolf"),
        ("a bear vs a wolf", "a grizzly bear", "a grizzly bear vs a wolf"),
        ("a bear", "a goose", "a bear vs a goose"),
        ("a vs b vs c", "a vs c", "a vs c"),
        ("bear vs wolf", "the big one", "bear vs wolf (the big one)"),
        ("bear vs bear", "grizzly bear", "bear vs bear (grizzly bear)"),
        ("bear vs wolf", "  ", "bear vs wolf"),
    ],
)
def test_merge_answer(original: str, answer: str, merged: str) -> None:
    assert merge_answer(original, answer) == merged
