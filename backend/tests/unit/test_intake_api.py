"""The intake routes on a scripted chat model: ok, one question then ok, and expiry (D08)."""

import asyncio
import json
import logging
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
from app.intake.parser import (
    COMMON_KIND_NOTE,
    INPUT_END,
    INPUT_START,
    LONG_TEXT_CHARS,
    LONG_TEXT_QUESTION,
    parse_matchup,
)
from app.main import create_app
from app.providers.base import ChatMessage
from app.providers.live.chat import LiveChatLLM
from app.providers.live.http import ProviderError
from app.providers.mock.text import MockChatLLM
from app.safety.verdict import ALLOWED, SafetyVerdict


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
    # Live models often offer bare variants (#296).
    "bear vs goose": {
        "fighters": [side("bear", "bear"), side("goose", "goose")],
        "needs_clarification": {"question": "Which type of bear?", "options": ["Grizzly", "Polar"]},
    },
    "grizzly bear vs goose": {
        "fighters": [side("grizzly bear", "grizzly bear"), side("goose", "goose")]
    },
    # One side typed, and the live model asks about its kind, not its opponent (#360).
    "a bear": {
        "fighters": [side("a bear", "bear")],
        "needs_clarification": {"question": "Which type of bear?", "options": ["Grizzly", "Polar"]},
    },
    "a grizzly bear": {"fighters": [side("a grizzly bear", "grizzly bear")]},
    # The typed terrain must survive the answer (#416): the live re-parse can drop it.
    "a bear vs 6 gray wolves in a forest": {
        "fighters": [side("a bear", "bear"), side("6 gray wolves", "gray wolf")],
        "terrain": "forest",
        "needs_clarification": {"question": "Which type of bear?", "options": ["Grizzly", "Polar"]},
    },
    "a grizzly bear vs 6 gray wolves in a forest": {
        "fighters": [side("a grizzly bear", "grizzly bear"), side("6 gray wolves", "gray wolf")]
    },
    "a grizzly bear vs 6 gray wolves in a lake": {
        "fighters": [side("a grizzly bear", "grizzly bear"), side("6 gray wolves", "gray wolf")],
        "terrain": "lake",
    },
    "a grizzly bear vs 6 gray wolves in the arena": {
        "fighters": [side("a grizzly bear", "grizzly bear"), side("6 gray wolves", "gray wolf")]
    },
    # A fraction gets "How many horses should fight?" from code; a bare count answers it (#508).
    "half a horse vs a dozen house cats": {
        "fighters": [side("half a horse", "horse"), side("a dozen house cats", "house cat")]
    },
    "1 horse vs a dozen house cats": {
        "fighters": [side("1 horse", "horse"), side("a dozen house cats", "house cat")]
    },
    "half a horse vs a dozen house cats (banana)": {
        "fighters": [side("half a horse", "horse"), side("a dozen house cats", "house cat")]
    },
}


# Far longer than any patched deadline: a hung call only ends when the deadline cancels it.
HANG_SECONDS = 30.0


class ScriptedChat:
    """Stand-in chat model that replies from REPLIES and remembers each text it saw.

    Set `down` to make every call fail like an outage, `delay` to make each call slow, or `hangs`
    to make that many calls, from the next one, hang until the deadline cancels them (#547).
    """

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.down = False
        self.delay = 0.0
        self.hangs = 0

    async def complete(self, messages: list[ChatMessage], **_: Any) -> str:
        if self.down:
            raise ProviderError("chat endpoint unavailable")
        if self.hangs:
            self.hangs -= 1
            await asyncio.sleep(HANG_SECONDS)
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
    # #168: the note names the fighter code picks for a bare kind, instead of a vague promise.
    assert "Not sure which bear, so we used the grizzly bear." in body["matchup"]["assumptions"]
    assert COMMON_KIND_NOTE not in body["matchup"]["assumptions"]
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


# Live options are often just the variant ("Grizzly"): splice an offered one in front of the
# fighter the question names, so research gets "grizzly bear", not "bear" (#296).
BEARS = ["Grizzly", "Polar", "American Black"]


@pytest.mark.parametrize(
    ("original", "answer", "question", "options", "merged"),
    [
        (
            "a bear vs 6 wolves in a forest",
            "Grizzly",
            "Which type of bear would you like?",
            BEARS,
            "a grizzly bear vs 6 wolves in a forest",
        ),
        ("3 bears vs a wolf", "Polar", "Which kind of bear?", BEARS, "3 polar bears vs a wolf"),
        ("bear vs wolf", "American Black", "Which bear?", BEARS, "american black bear vs wolf"),
        ("a bear vs 6 wolves", "a grizzly", "Which bear?", BEARS, "a grizzly bear vs 6 wolves"),
        (
            "a bear vs a wolf",
            "Timber",
            "Which kind of wolf?",
            ["Timber"],
            "a bear vs a timber wolf",
        ),
        ("a bear vs 6 wolves", "Arctic", "Which wolf?", ["Arctic"], "a bear vs 6 arctic wolves"),
        ("a bear vs a wolf", "Grizzly", "Which one?", BEARS, "a bear vs a wolf (Grizzly)"),
        ("bear vs bear", "Grizzly", "Which bear?", BEARS, "bear vs bear (Grizzly)"),
        ("bear vs wolf", "the big one", "Which bear?", BEARS, "bear vs wolf (the big one)"),
        ("bear vs wolf", "grizzly bear", "Which bear?", BEARS, "grizzly bear vs wolf"),
        # The answer's last word ("Black") is in the other fighter: still lands on the bear.
        (
            "a bear vs a black wolf",
            "American Black",
            "Which bear?",
            BEARS,
            "a american black bear vs a black wolf",
        ),
    ],
)
def test_merge_answer_splices_an_offered_variant_before_the_asked_fighter(
    original: str, answer: str, question: str, options: list[str], merged: str
) -> None:
    assert merge_answer(original, answer, question, options) == merged


# With one side typed, an offered variant names that fighter; an opponent question, or a typed
# answer, still becomes the other side (#360).
@pytest.mark.parametrize(
    ("original", "answer", "question", "options", "merged"),
    [
        ("a bear", "Grizzly", "Which type of bear are we looking at?", BEARS, "a grizzly bear"),
        ("3 bears", "Polar", "What type of bear is fighting?", BEARS, "3 polar bears"),
        ("a wolf", "Bear", "Who does the wolf fight?", ["Bear", "Eagle"], "a wolf vs Bear"),
        # Live wordings seen in the #360 check:
        (
            "a bear",
            "Grizzly",
            "Which species of bear would you like to fight?",
            BEARS,
            "a grizzly bear",
        ),
        ("a wolf", "Bear", "Which animal should the wolf fight?", ["Bear"], "a wolf vs Bear"),
        ("a bear", "Wolf", "What kind of opponent should it face?", ["Wolf"], "a bear vs Wolf"),
        ("a bear", "Grizzly bear", "Which bear?", ["Grizzly bear"], "a Grizzly bear"),
        ("a bear", "Gray wolf", "Who should a bear fight?", ["Gray wolf"], "a bear vs Gray wolf"),
        ("a bear", "a goose", "Which bear?", BEARS, "a bear vs a goose"),
        ("a bear", "Polar", "", [], "a bear vs Polar"),
    ],
)
def test_merge_answer_with_one_side_names_that_fighter_unless_asked_for_an_opponent(
    original: str, answer: str, question: str, options: list[str], merged: str
) -> None:
    assert merge_answer(original, answer, question, options) == merged


def test_a_variant_answer_to_one_side_asks_to_start_again_not_a_503(
    client: TestClient, chat: ScriptedChat
) -> None:
    pending_id = client.post("/api/intake", json={"text": "a bear"}).json()["pending_id"]
    response = client.post(f"/api/intake/{pending_id}/answer", json={"answer": "Grizzly"})
    assert chat.texts == ["a bear", "a grizzly bear"]
    assert response.status_code == 200
    assert response.json()["status"] == "blocked" and response.json()["message"] == START_OVER


HOW_MANY_HORSES = "How many horses should fight?"
HORSE_OPTIONS = ["a horse vs a dozen house cats", "2 horses vs a dozen house cats"]


# #508: a bare count answers "How many ___ should fight?" by replacing that side's count words.
@pytest.mark.parametrize(
    ("original", "answer", "question", "merged"),
    [
        (
            "half a horse vs a dozen house cats",
            "1",
            HOW_MANY_HORSES,
            "1 horse vs a dozen house cats",
        ),
        (
            "half a horse vs a dozen house cats",
            "one",
            HOW_MANY_HORSES,
            "1 horse vs a dozen house cats",
        ),
        (
            "half a horse vs a dozen house cats",
            "2",
            HOW_MANY_HORSES,
            "2 horse vs a dozen house cats",
        ),
        (
            "half a horse vs a dozen house cats",
            "Two",
            HOW_MANY_HORSES,
            "2 horse vs a dozen house cats",
        ),
        (
            "half a horse vs a dozen house cats",
            "2 horses",
            HOW_MANY_HORSES,
            "2 horse vs a dozen house cats",
        ),
        ("a horse vs 0 wolves", "3", "How many wolves should fight?", "a horse vs 3 wolves"),
        (
            "a horse vs 2.5 house cats",
            "a dozen",
            "How many house cats should fight?",
            "a horse vs 12 house cats",
        ),
        ("0.5 geese vs a wolf", "one", "How many geese should fight?", "1 geese vs a wolf"),
    ],
)
def test_merge_answer_reads_a_bare_count_for_the_side_asked_about(
    original: str, answer: str, question: str, merged: str
) -> None:
    assert merge_answer(original, answer, question, HORSE_OPTIONS) == merged


# A count only counts for a "How many" question; other answers merge as before.
@pytest.mark.parametrize(
    ("answer", "question", "merged"),
    [
        ("banana", HOW_MANY_HORSES, "half a horse vs a dozen house cats (banana)"),
        ("1", "Which horse?", "half a horse vs a dozen house cats (1)"),
        ("2 wolves", HOW_MANY_HORSES, "half a horse vs a dozen house cats (2 wolves)"),
    ],
)
def test_merge_answer_leaves_other_answers_to_a_count_question_alone(
    answer: str, question: str, merged: str
) -> None:
    original = "half a horse vs a dozen house cats"
    assert merge_answer(original, answer, question, HORSE_OPTIONS) == merged


# Ask "How many horses should fight?" about half a horse and send back the answer.
def answer_half_a_horse(client: TestClient, answer: str) -> dict[str, Any]:
    text = "half a horse vs a dozen house cats"
    asked = client.post("/api/intake", json={"text": text}).json()
    assert asked["status"] == "clarify" and asked["question"] == HOW_MANY_HORSES
    return client.post(f"/api/intake/{asked['pending_id']}/answer", json={"answer": answer}).json()


@pytest.mark.parametrize("answer", ["1", "one"])
def test_a_bare_count_answer_sets_up_the_matchup(
    client: TestClient, chat: ScriptedChat, answer: str
) -> None:
    body = answer_half_a_horse(client, answer)
    assert chat.texts[-1] == "1 horse vs a dozen house cats"
    assert body["status"] == "ok"
    assert [f["count"] for f in body["matchup"]["fighters"]] == [1, 12]


def test_a_non_count_answer_to_how_many_still_asks_to_start_again(
    client: TestClient, chat: ScriptedChat
) -> None:
    body = answer_half_a_horse(client, "banana")
    assert body["status"] == "blocked" and body["message"] == START_OVER


def test_a_one_word_option_answer_names_the_fighter(client: TestClient, chat: ScriptedChat) -> None:
    pending_id = client.post("/api/intake", json={"text": "bear vs goose"}).json()["pending_id"]
    body = client.post(f"/api/intake/{pending_id}/answer", json={"answer": "Grizzly"}).json()
    assert chat.texts == ["bear vs goose", "grizzly bear vs goose"]
    assert body["status"] == "ok"
    assert body["matchup"]["fighters"][0]["entity"] == "grizzly bear"


# Ask "Which type of bear?" about the forest fight and send back the answer.
def answer_forest_bear(client: TestClient, answer: str) -> dict[str, Any]:
    text = "a bear vs 6 gray wolves in a forest"
    pending_id = client.post("/api/intake", json={"text": text}).json()["pending_id"]
    return client.post(f"/api/intake/{pending_id}/answer", json={"answer": answer}).json()


def test_the_typed_terrain_survives_a_re_parse_that_falls_back_to_the_arena(
    client: TestClient, chat: ScriptedChat
) -> None:
    body = answer_forest_bear(client, "Grizzly")
    assert chat.texts[-1] == "a grizzly bear vs 6 gray wolves in a forest"
    assert body["status"] == "ok" and body["matchup"]["terrain"] == "forest"
    assert body["matchup"]["fighters"][0]["entity"] == "grizzly bear"
    assert "in the forest" in body["message"]


def test_a_different_terrain_from_the_re_parse_is_kept(
    client: TestClient, chat: ScriptedChat
) -> None:
    body = answer_forest_bear(client, "a grizzly bear vs 6 gray wolves in a lake")
    assert chat.texts[-1] == "a grizzly bear vs 6 gray wolves in a lake"
    assert body["status"] == "ok" and body["matchup"]["terrain"] == "water"


def test_an_answer_that_names_the_arena_beats_the_first_request(
    client: TestClient, chat: ScriptedChat
) -> None:
    body = answer_forest_bear(client, "a grizzly bear vs 6 gray wolves in the arena")
    assert chat.texts[-1] == "a grizzly bear vs 6 gray wolves in the arena"
    assert body["status"] == "ok" and body["matchup"]["terrain"] == "arena"


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


# --- #547: one slow step is retried inside the deadline, and the log names it ---------------

# Short enough to keep the tests quick, long enough for the mock safety check and Wikidata.
SHORT_DEADLINE = 1.0
GRIZZLY_VS_WOLF = "a grizzly bear vs a gray wolf"


class HangOnceChat:
    """Wraps a chat model so its first `hangs` calls hang until the deadline cancels them."""

    def __init__(self, inner: Any, hangs: int = 1) -> None:
        self.inner = inner
        self.hangs = hangs

    async def complete(self, messages: list[ChatMessage], **kwargs: Any) -> str:
        if self.hangs:
            self.hangs -= 1
            await asyncio.sleep(HANG_SECONDS)
        return await self.inner.complete(messages, **kwargs)


# The intake route's log lines (one per timed-out attempt).
def intake_log(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == intake_api.logger.name]


def test_a_model_call_that_times_out_once_is_retried_and_answers(
    client: TestClient, db_path: Path, chat: ScriptedChat, monkeypatch: pytest.MonkeyPatch
) -> None:
    pending_id = ask_which_bear(client)
    monkeypatch.setattr(intake_api, "INTAKE_DEADLINE_SECONDS", SHORT_DEADLINE)
    chat.hangs = 1
    first = client.post("/api/intake", json={"text": GRIZZLY_VS_WOLF})
    assert first.status_code == 200 and first.json()["status"] == "ok"
    assert [f["entity"] for f in first.json()["matchup"]["fighters"]] == [
        "grizzly bear",
        "gray wolf",
    ]
    chat.hangs = 1  # the answer route retries the same way
    answer = client.post(f"/api/intake/{pending_id}/answer", json={"answer": "grizzly bear"})
    assert answer.status_code == 200 and answer.json()["status"] == "ok"
    assert pending_rows(db_path) == 0


def test_two_timeouts_in_a_row_are_a_503_inside_the_deadline(
    client: TestClient,
    chat: ScriptedChat,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    deadline = 0.5
    monkeypatch.setattr(intake_api, "INTAKE_DEADLINE_SECONDS", deadline)
    chat.hangs = 2
    caplog.set_level(logging.WARNING, logger=intake_api.logger.name)
    started = time.monotonic()
    response = client.post("/api/intake", json={"text": GRIZZLY_VS_WOLF})
    elapsed = time.monotonic() - started
    assert response.status_code == 503 and response.json()["detail"] == UNAVAILABLE_MESSAGE
    assert elapsed < deadline + 0.3  # the retry fits in the same deadline, not twice it
    assert chat.hangs == 0  # both attempts reached the model
    lines = [r.getMessage() for r in intake_log(caplog)]
    assert lines == [
        "Intake attempt 1 of 2 timed out during parse.",
        "Intake attempt 2 of 2 timed out during parse.",
    ]


def test_no_retry_starts_when_the_first_attempt_used_the_whole_deadline(
    client: TestClient, chat: ScriptedChat, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(intake_api, "INTAKE_DEADLINE_SECONDS", 0.2)
    monkeypatch.setattr(intake_api, "ATTEMPT_SHARE", 1.0)
    chat.hangs = 2
    response = client.post("/api/intake", json={"text": GRIZZLY_VS_WOLF})
    assert response.status_code == 503 and response.json()["detail"] == UNAVAILABLE_MESSAGE
    assert chat.hangs == 1  # the second call never started


# Make one intake step hang once, by step name.
def hang_once(step: str, chat: ScriptedChat, monkeypatch: pytest.MonkeyPatch) -> None:
    if "parse" in step:
        chat.hangs = 1
    if "safety classify" in step:
        safety = HangOnceChat(MockChatLLM())
        monkeypatch.setattr("app.intake.parser.get_intake_chat", lambda: safety)
    if step == "Wikidata":
        hung: list[int] = []

        async def names_check(*_: Any, **__: Any) -> SafetyVerdict:
            if not hung:
                hung.append(1)
                await asyncio.sleep(HANG_SECONDS)
            return ALLOWED

        monkeypatch.setattr("app.safety.gate.check_names", names_check)


@pytest.mark.parametrize(
    "step", ["parse", "safety classify", "parse and safety classify", "Wikidata"]
)
def test_a_timeout_logs_one_line_naming_the_step_and_no_request_details(
    client: TestClient,
    chat: ScriptedChat,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    step: str,
) -> None:
    monkeypatch.setattr(intake_api, "INTAKE_DEADLINE_SECONDS", SHORT_DEADLINE)
    hang_once(step, chat, monkeypatch)
    caplog.set_level(logging.DEBUG)
    response = client.post("/api/intake", json={"text": GRIZZLY_VS_WOLF})
    assert response.status_code == 200 and response.json()["status"] == "ok"  # the retry worked
    records = intake_log(caplog)
    assert [r.getMessage() for r in records] == [f"Intake attempt 1 of 2 timed out during {step}."]
    for record in caplog.records:  # nothing logged anywhere carries the request
        line = record.getMessage().lower()
        assert GRIZZLY_VS_WOLF not in line and "grizzly" not in line
        assert INPUT_START.lower() not in line and "http" not in line


# About 490 characters: under the 500 limit, so the model is asked to read it (#362).
LONG_MATCHUP = "a " + "very " * 94 + "big bear vs a wolf"


@pytest.mark.parametrize("trouble", ["outage", "slow"])
def test_a_long_matchup_that_fails_asks_for_a_shorter_one_not_a_retry(
    client: TestClient,
    db_path: Path,
    chat: ScriptedChat,
    monkeypatch: pytest.MonkeyPatch,
    trouble: str,
) -> None:
    assert LONG_TEXT_CHARS < len(LONG_MATCHUP) < 500
    if trouble == "outage":
        chat.down = True
    else:
        monkeypatch.setattr(intake_api, "INTAKE_DEADLINE_SECONDS", 0.05)
        chat.delay = 1.0
    response = client.post("/api/intake", json={"text": LONG_MATCHUP})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "clarify" and body["question"] == LONG_TEXT_QUESTION
    assert body["pending_id"] is None and pending_rows(db_path) == 0


def test_a_short_matchup_that_fails_still_says_try_again(
    client: TestClient, chat: ScriptedChat
) -> None:
    chat.down = True
    text = "a grizzly bear vs a gray wolf in a forest " * 4  # just under LONG_TEXT_CHARS
    assert len(text.strip()) <= LONG_TEXT_CHARS
    response = client.post("/api/intake", json={"text": text})
    assert response.status_code == 503 and response.json()["detail"] == UNAVAILABLE_MESSAGE


# Pin the cutoff: exactly LONG_TEXT_CHARS still retries; one more character asks for less.
@pytest.mark.parametrize(
    ("length", "asks_shorter"), [(LONG_TEXT_CHARS, False), (LONG_TEXT_CHARS + 1, True)]
)
def test_the_long_matchup_cutoff_is_exact(
    client: TestClient, chat: ScriptedChat, length: int, asks_shorter: bool
) -> None:
    chat.down = True
    text = ("a grizzly bear vs a gray wolf " * 10)[:length].rstrip().ljust(length, "x")
    assert len(text.strip()) == length
    response = client.post("/api/intake", json={"text": text})
    if asks_shorter:
        assert response.status_code == 200 and response.json()["question"] == LONG_TEXT_QUESTION
    else:
        assert response.status_code == 503 and response.json()["detail"] == UNAVAILABLE_MESSAGE


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
