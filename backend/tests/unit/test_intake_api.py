"""The intake routes on a scripted chat model: ok, one question then ok, and expiry (D08)."""

import asyncio
import json
import sqlite3
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import intake as intake_api
from app.api.intake import EXPIRED_MESSAGE, UNAVAILABLE_MESSAGE, get_chat, get_db
from app.config import Settings
from app.db.connection import connect
from app.db.intake_pending import (
    MAX_ORIGINAL_CHARS,
    MAX_QUESTION_CHARS,
    PENDING_TTL_SECONDS,
    PendingQuestion,
    restore_pending,
    save_pending,
    take_pending,
)
from app.db.migrate import apply_migrations
from app.intake.answer import START_OVER, merge_answer
from app.intake.parser import COMMON_KIND_NOTE, INPUT_END, INPUT_START, parse_matchup
from app.main import create_app
from app.providers.base import ChatMessage
from app.providers.live.chat import LiveChatLLM
from app.providers.live.http import ProviderError
from app.providers.mock.text import MockChatLLM


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
    """Stand-in chat model that replies from REPLIES and remembers each text it saw.

    Set `down` to make every call fail like an outage, or `delay` to make each call slow.
    """

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.down = False
        self.delay = 0.0

    async def complete(self, messages: list[ChatMessage], **_: Any) -> str:
        if self.down:
            raise ProviderError("chat endpoint unavailable")
        await asyncio.sleep(self.delay)
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


def test_saving_purges_expired_questions_and_caps_the_question_and_text(db_path: Path) -> None:
    connection = connect(db_path)
    apply_migrations(connection)
    now = time.time()
    old = save_pending(
        connection, PendingQuestion("a", "Q?", []), now=now - PENDING_TTL_SECONDS - 1
    )
    long_question = PendingQuestion("bear vs wolf " * 200, "Which? " * 200, ["grizzly bear"])
    fresh = save_pending(connection, long_question, now=now)
    count = connection.execute("SELECT COUNT(*) FROM intake_pending").fetchone()[0]
    taken = take_pending(connection, fresh, now=now)
    connection.close()
    assert count == 1 and old != fresh  # the expired row went when the new one was saved
    assert len(fresh) == len("p-") + 32  # a full uuid, not a shortened one
    assert taken is not None and len(taken.question) == MAX_QUESTION_CHARS
    assert len(taken.original_text) == MAX_ORIGINAL_CHARS  # the parser reads 500 at most


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
        ("a bear vs a wolf", "grizzly bear and wolf", "a bear vs a wolf (grizzly bear and wolf)"),
        ("a bear vs a wolf", "Grizzly AND gray wolf", "a bear vs a wolf (Grizzly AND gray wolf)"),
        ("a bear vs a wolf", "a sandy bear", "a sandy bear vs a wolf"),
    ],
)
def test_merge_answer(original: str, answer: str, merged: str) -> None:
    assert merge_answer(original, answer) == merged


# --- Safety (A04 runs inside parse_matchup), outages, and the 25 s deadline ---------------------


def test_unsafe_first_text_is_blocked_and_saves_no_question(
    client: TestClient, db_path: Path, chat: ScriptedChat
) -> None:
    body = client.post("/api/intake", json={"text": "a toddler vs a goose"}).json()
    assert body["status"] == "blocked" and body["blocked_reason"] == "minor"
    assert body["matchup"] is None and body["pending_id"] is None
    assert pending_rows(db_path) == 0 and chat.texts == []  # code rules ran before any model call


def test_unsafe_answer_is_blocked_and_asks_nothing_more(
    client: TestClient, db_path: Path, chat: ScriptedChat
) -> None:
    pending_id = ask_which_bear(client)
    body = client.post(f"/api/intake/{pending_id}/answer", json={"answer": "a toddler"}).json()
    assert body["status"] == "blocked" and body["blocked_reason"] == "minor"
    assert body["matchup"] is None and body["question"] is None and body["pending_id"] is None
    assert pending_rows(db_path) == 0 and chat.texts == ["bear vs wolf"]


def test_an_outage_on_the_first_text_is_a_503_not_a_500(
    client: TestClient, db_path: Path, chat: ScriptedChat
) -> None:
    chat.down = True
    response = client.post("/api/intake", json={"text": "bear vs wolf"})
    assert response.status_code == 503 and response.json()["detail"] == UNAVAILABLE_MESSAGE
    assert pending_rows(db_path) == 0


def test_an_outage_on_the_answer_is_a_503_and_keeps_the_question(
    client: TestClient, db_path: Path, chat: ScriptedChat
) -> None:
    pending_id = ask_which_bear(client)
    chat.down = True
    response = client.post(f"/api/intake/{pending_id}/answer", json={"answer": "grizzly bear"})
    assert response.status_code == 503 and response.json()["detail"] == UNAVAILABLE_MESSAGE
    assert pending_rows(db_path) == 1
    chat.down = False  # the retry with the same id works once the model is back
    retry = client.post(f"/api/intake/{pending_id}/answer", json={"answer": "grizzly bear"})
    assert retry.status_code == 200 and retry.json()["status"] == "ok"


def test_a_slow_model_hits_the_deadline_on_both_routes(
    client: TestClient, db_path: Path, chat: ScriptedChat, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert intake_api.INTAKE_DEADLINE_SECONDS == 25.0
    pending_id = ask_which_bear(client)
    monkeypatch.setattr(intake_api, "INTAKE_DEADLINE_SECONDS", 0.05)
    chat.delay = 1.0
    first = client.post("/api/intake", json={"text": "a grizzly bear vs a gray wolf"})
    assert first.status_code == 503 and first.json()["detail"] == UNAVAILABLE_MESSAGE
    answer = client.post(f"/api/intake/{pending_id}/answer", json={"answer": "grizzly bear"})
    assert answer.status_code == 503 and pending_rows(db_path) == 1  # the question is kept


def test_a_restored_question_keeps_its_id_and_age(db_path: Path) -> None:
    connection = connect(db_path)
    apply_migrations(connection)
    now = time.time()
    question = PendingQuestion("bear vs wolf", "Which bear?", ["grizzly bear"])
    pending_id = save_pending(connection, question, now=now - PENDING_TTL_SECONDS + 5)
    taken = take_pending(connection, pending_id, now=now)
    assert taken is not None
    restore_pending(connection, pending_id, taken)
    later = take_pending(connection, pending_id, now=now + 10)  # past the original 30 minutes
    connection.close()
    assert later is None


# #169: in live mode both routes read matchups with intake's chat (15 s per call, one retry).
def test_the_routes_use_the_short_timeout_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    live = Settings(
        _env_file=None,
        provider_mode="live",
        course_api_key="decoy-key-0000",
        chat_llm_url="http://decoy-host.invalid:9001",
        chat_llm_model="decoy/chat-model",
    )
    monkeypatch.setattr("app.providers.registry.get_settings", lambda: live)
    chat = get_chat()
    assert isinstance(chat, LiveChatLLM)
    assert (chat.timeout_s, chat.retries) == (15.0, 1)


# #169: the safety check (and the parse call, when no chat is given) use the intake chat.
async def test_the_safety_check_in_intake_uses_the_intake_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[int] = []

    def intake_chat() -> MockChatLLM:
        asked.append(1)
        return MockChatLLM()

    monkeypatch.setattr("app.intake.parser.get_intake_chat", intake_chat)
    text = "a grizzly bear vs 6 gray wolves in a forest"
    result = await parse_matchup(text, chat=MockChatLLM())
    assert result.status == "ok" and asked == [1]
    asked.clear()
    result = await parse_matchup(text)  # no chat passed: the parse call uses it too
    assert result.status == "ok" and asked == [1, 1]
