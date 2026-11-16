"""#324: cached legends can be forgotten, refusals are remembered briefly, "(mythology)" comes
first, lookups run at most two at a time, and research says when a legend may take a while."""

import asyncio
import json
import sqlite3
from collections.abc import Iterator

import httpx
import pytest

from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.matchup import FighterRequest, Matchup
from app.pipeline import orchestrator, stages
from app.pipeline.stages import StageFailed
from app.research import lore, sheet_store
from app.research.sheet_store import cached_legends, cached_sheet, forget_legend
from scripts import forget_legend as forget_script
from tests.unit.test_lore import ARTICLE, answer
from tests.unit.test_mythical_battles import go_live, save_legend

HYDRA = FighterRequest(entity="hydra", raw="a hydra")


@pytest.fixture
def db() -> Iterator[sqlite3.Connection]:
    connection = connect()
    apply_migrations(connection)
    yield connection
    connection.close()


class ScriptedChat:
    """Gives the same reply to every call, slowly, and counts calls and how many ran at once."""

    def __init__(self, reply: dict, pause: float = 0.0) -> None:
        self.reply, self.pause = reply, pause
        self.calls = self.in_flight = self.most = 0

    async def complete(self, messages, *, prompt_name, json_schema=None) -> str:
        self.calls += 1
        self.in_flight += 1
        self.most = max(self.most, self.in_flight)
        await asyncio.sleep(self.pause)
        self.in_flight -= 1
        return json.dumps(self.reply)


# --- 1. Forgetting a cached legend -----------------------------------------------------------


def test_a_cached_legend_can_be_listed_and_forgotten(db: sqlite3.Connection) -> None:
    save_legend("hydra", "Hydra")
    assert cached_legends(db) == [("hydra", "Hydra", 1)]
    assert forget_legend(db, "Hydra") == 1
    assert cached_sheet(db, "hydra") is None and cached_legends(db) == []
    assert forget_legend(db, "hydra") == 0  # nothing left to forget


def test_seed_fighters_and_file_creatures_are_never_forgotten(db: sqlite3.Connection) -> None:
    for name in ("dragon", "gray wolf"):
        with pytest.raises(ValueError, match="not a cached legend"):
            forget_legend(db, name)


def test_the_script_lists_and_forgets(capsys: pytest.CaptureFixture[str]) -> None:
    save_legend("hydra", "Hydra")
    assert forget_script.main(["--list"]) == 0
    assert "hydra: Hydra (1 saved)" in capsys.readouterr().out
    assert forget_script.main(["hydra"]) == 0
    assert "Forgot 'hydra'" in capsys.readouterr().out
    assert forget_script.main(["dragon"]) == 2
    assert "not a cached legend" in capsys.readouterr().err


async def test_a_forgotten_legend_is_modeled_again(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = ScriptedChat(answer())
    go_live(monkeypatch, chat)
    await stages.lookup_fighter(HYDRA)
    await stages.lookup_fighter(HYDRA)
    assert chat.calls == 1  # the second battle used the cached sheet
    connection = connect()
    try:
        forget_legend(connection, "hydra")
    finally:
        connection.close()
    await stages.lookup_fighter(HYDRA)
    assert chat.calls == 2


# --- 2. Remembering a refusal ------------------------------------------------------------------


async def test_a_refused_name_is_not_looked_up_again_for_a_while(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = ScriptedChat(answer(quote="The hydra was the size of a whale."))  # not in the article
    go_live(monkeypatch, chat)
    for _ in range(3):
        with pytest.raises(StageFailed) as failure:
            await stages.lookup_fighter(HYDRA)
        assert str(failure.value) == stages.LEGEND_BLOCKED.format(name="hydra")
    assert chat.calls == 1  # the two retries answered from memory
    later = sheet_store.time.monotonic() + sheet_store.REFUSAL_MEMORY_S + 1
    monkeypatch.setattr(sheet_store.time, "monotonic", lambda: later)
    with pytest.raises(StageFailed):
        await stages.lookup_fighter(HYDRA)
    assert chat.calls == 2  # after the window it asks again


async def test_an_outage_is_not_remembered(monkeypatch: pytest.MonkeyPatch) -> None:
    fetches: list[str] = []

    async def wikipedia_down(client: httpx.AsyncClient, title: str) -> None:
        fetches.append(title)
        raise httpx.ConnectError("Wikipedia is down")

    go_live(monkeypatch, ScriptedChat(answer()))
    monkeypatch.setattr(lore, "fetch_article", wikipedia_down)
    for _ in range(2):
        with pytest.raises(StageFailed) as failure:
            await stages.lookup_fighter(HYDRA)
        assert str(failure.value) == stages.LEGEND_UNAVAILABLE.format(name="hydra")
    assert len(fetches) == 2  # the retry tried Wikipedia again


# --- 3. "(mythology)" first --------------------------------------------------------------------


# Serve the article only for the given page titles, recording every title asked for.
def serve(monkeypatch: pytest.MonkeyPatch, found: set[str], seen: list[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        title = request.url.path.rsplit("/", 1)[-1]
        seen.append(title)
        if title not in found:
            return httpx.Response(404)
        return httpx.Response(200, headers={"ETag": '"123/abc"'}, content=ARTICLE.encode())

    monkeypatch.setattr(
        sheet_store,
        "legend_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_the_mythology_article_is_tried_first(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    go_live(monkeypatch, ScriptedChat(answer()))
    serve(monkeypatch, {"Hydra_(mythology)", "hydra"}, seen)
    sheet = await stages.lookup_fighter(HYDRA)
    assert seen == ["Hydra_(mythology)"]  # the bare name was never needed
    assert sheet.lore is not None and sheet.lore.source.title == "Hydra (mythology)"


async def test_the_bare_name_is_used_when_there_is_no_mythology_article(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    go_live(monkeypatch, ScriptedChat(answer()))
    serve(monkeypatch, {"hydra"}, seen)
    await stages.lookup_fighter(HYDRA)
    assert seen == ["Hydra_(mythology)", "hydra"]


# --- 4. At most two lookups at once --------------------------------------------------------------


async def test_new_legend_lookups_run_at_most_two_at_a_time(
    monkeypatch: pytest.MonkeyPatch, db: sqlite3.Connection
) -> None:
    chat = ScriptedChat(answer(), pause=0.05)
    go_live(monkeypatch, chat)
    names = ["hydra", "basilisk-x", "wyvern-x", "kraken-x", "roc-x"]
    sheets = await asyncio.gather(*(sheet_store.resolve_legend(db, chat, n) for n in names))
    assert all(getattr(s, "category", None) == "mythical" for s in sheets)
    assert chat.calls == 5 and chat.most == sheet_store.MAX_LEGEND_LOOKUPS == 2


async def test_waiting_for_a_slot_counts_toward_the_time_limit(
    monkeypatch: pytest.MonkeyPatch, db: sqlite3.Connection
) -> None:
    monkeypatch.setattr(sheet_store, "LEGEND_BUDGET_S", 0.15)
    chat = ScriptedChat(answer(), pause=0.1)
    go_live(monkeypatch, chat)
    names = ["hydra", "basilisk-x", "wyvern-x", "kraken-x", "roc-x", "griffon-x"]
    outcomes = await asyncio.gather(*(sheet_store.resolve_legend(db, chat, n) for n in names))
    assert any(o is lore.UNAVAILABLE for o in outcomes)  # the end of the queue gave up in time
    assert chat.calls < len(names)  # and never started its model call


# --- 5. The progress line ----------------------------------------------------------------------


def matchup(*names: str) -> Matchup:
    fighters = [{"entity": n, "raw": n} for n in names]
    return Matchup.model_validate({"fighters": fighters, "raw_text": " vs ".join(names)})


def test_research_says_when_a_legend_may_take_a_while() -> None:
    assert orchestrator._looking_up(matchup("hydra", "gray wolf")) == (
        "Looking up hydra and gray wolf (a legend can take up to 30 s)"
    )
    assert orchestrator._looking_up(matchup("dragon", "main battle tank")) == (
        "Looking up dragon and main battle tank"
    )
    assert orchestrator._looking_up(matchup("grizzly bear", "gray wolf")) == (
        "Looking up grizzly bear and gray wolf"
    )
