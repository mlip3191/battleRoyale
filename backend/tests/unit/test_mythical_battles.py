"""G09 (#39): battles use mythical creatures, from the file or modeled from their article."""

import asyncio
import json

import httpx
import pytest

from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.matchup import FighterRequest, Matchup
from app.models.stats import StatName
from app.pipeline import challenger, stages
from app.pipeline.stages import StageFailed
from app.providers.live.http import ProviderError
from app.providers.registry import get_provider
from app.research import sheet_store, sources
from tests.unit.test_lore import ARTICLE, FakeChat, answer

PUG_QUOTE = "The pug is a breed of dog originally from China, with a wrinkly, short-muzzled face."
PUG_ARTICLE = f"<html><body><p>{PUG_QUOTE} Pugs weigh 6 to 8 kg.</p></body></html>"
CHIMERA = FighterRequest(entity="chimera", raw="a chimera")


def matchup(first: str, second: str) -> Matchup:
    fighters = [{"entity": name, "raw": name} for name in (first, second)]
    return Matchup.model_validate({"fighters": fighters, "raw_text": f"{first} vs {second}"})


class SlowChat:
    """A chat model that never answers in time."""

    async def complete(self, messages, *, prompt_name, json_schema=None) -> str:
        await asyncio.sleep(5)
        return "{}"


# Serve `article` (or `status`) for any Wikipedia request, and use `chat` in research.
def go_live(
    monkeypatch: pytest.MonkeyPatch, chat, article: str = ARTICLE, status: int = 200
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"ETag": '"123/abc"'}, content=article.encode())

    monkeypatch.setattr(
        sheet_store,
        "legend_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(
        stages, "get_provider", lambda name: chat if name == "chat" else get_provider(name)
    )


async def test_a_dragon_battle_gets_an_all_assumption_sheet_with_its_lore() -> None:
    found = await stages.research(matchup("dragon", "main battle tank"))
    dragon, tank = found.sheets
    assert dragon.category == "mythical" and dragon.lore is not None
    assert all(stat.method == "assumption" for stat in dragon.stats.values())
    assert tank.fighter_id == "main-battle-tank"


async def test_a_creature_in_the_file_works_as_a_size_reference() -> None:
    fight = Matchup.model_validate(
        {
            "fighters": [
                {"entity": "duck", "raw": "a dragon-sized duck", "size_reference": "dragon"},
                {"entity": "horse", "raw": "a horse"},
            ],
            "raw_text": "a dragon-sized duck vs a horse",
        }
    )
    found = await stages.research(fight)
    assert found.reference_sheets[0] is not None and found.missing_references == []


async def test_a_legend_off_the_file_is_modeled_once_then_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = FakeChat(answer())  # one reply only: a second model call would fail the test
    go_live(monkeypatch, chat)
    first = await stages.research(matchup("chimera", "gray wolf"))
    chimera = first.sheets[0]
    assert chimera.fighter_id == "chimera" and chimera.category == "mythical"
    assert all(stat.method == "assumption" for stat in chimera.stats.values())
    assert "African lion" in (chimera.stats[StatName.MASS].note or "")
    again = await stages.research(matchup("chimera", "gray wolf"))
    assert again.sheets[0] == chimera and chat.calls == 1


async def test_a_made_up_quote_stops_the_battle_with_a_friendly_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    go_live(monkeypatch, FakeChat(answer(quote="The chimera was the size of a whale.")))
    with pytest.raises(StageFailed) as failure:
        await stages.lookup_fighter(FighterRequest(entity="chimera", raw="a chimera"))
    assert str(failure.value) == stages.LEGEND_BLOCKED.format(name="chimera")


async def test_an_outage_asks_the_user_to_try_again(monkeypatch: pytest.MonkeyPatch) -> None:
    go_live(monkeypatch, FakeChat(ProviderError("down"), ProviderError("down")))
    await expect_try_again()


# The try-again message, and nothing saved for a later battle to reuse.
async def expect_try_again() -> None:
    with pytest.raises(StageFailed) as failure:
        await stages.lookup_fighter(CHIMERA)
    assert str(failure.value) == stages.LEGEND_UNAVAILABLE.format(name="chimera")
    connection = connect()
    try:
        assert connection.execute("SELECT COUNT(*) FROM stat_sheets").fetchone()[0] == 0
    finally:
        connection.close()


async def test_a_legend_past_its_time_limit_asks_the_user_to_try_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sheet_store, "LEGEND_BUDGET_S", 0.01)
    go_live(monkeypatch, SlowChat())
    await expect_try_again()


async def test_a_wikipedia_outage_asks_the_user_to_try_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sources, "BACKOFF_S", 0.0)  # retry at once instead of backing off
    go_live(monkeypatch, FakeChat(), status=500)
    await expect_try_again()


async def test_a_sheet_that_cannot_be_built_asks_the_user_to_try_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_sheet(creature):
        raise ValueError("analog 'African lion' is not a seed-list fighter")

    monkeypatch.setattr(sheet_store, "build_mythical_sheet", no_sheet)
    go_live(monkeypatch, FakeChat(answer()))
    await expect_try_again()


async def test_code_trusts_found_true_so_the_prompt_must_refuse_real_animals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Documents a known limit (Mike, #322): no code check tells a legend from a real animal, so
    # a found:true reply for an ordinary article is built and cached. lore_extract.md tells the
    # model to answer found false for real animals, people, deities and named characters.
    reply = answer(body_analog="Golden retriever", abilities=[], quote=PUG_QUOTE)
    go_live(monkeypatch, FakeChat(reply), article=PUG_ARTICLE)
    sheet = await stages.lookup_fighter(FighterRequest(entity="pug", raw="a pug"))
    assert sheet.category == "mythical" and sheet.fighter_id == "pug"


async def test_mock_mode_never_goes_online_for_an_unknown_name() -> None:
    assert sheet_store.legend_client() is None
    with pytest.raises(StageFailed) as failure:
        await stages.lookup_fighter(FighterRequest(entity="okapi", raw="an okapi"))
    assert str(failure.value) == stages.NOT_FOUND.format(name="okapi")


# A legend sheet saved under `fighter_id`, as resolve_legend would save one.
def save_legend(fighter_id: str, display_name: str) -> None:
    dragon = sheet_store.build_mythical_sheet(sheet_store.find_creature("dragon"))
    legend = dragon.model_copy(update={"fighter_id": fighter_id, "display_name": display_name})
    connection = connect()
    try:
        apply_migrations(connection)
        sheet_store.save_sheet(connection, legend)
    finally:
        connection.close()


async def test_a_seed_fighter_whose_build_failed_is_never_modeled_as_a_legend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sheet(*_: object) -> None:
        return None

    async def must_not_run(*_: object) -> None:
        raise AssertionError("a seed-list fighter reached resolve_legend")

    monkeypatch.setattr(stages, "lookup_sheet", no_sheet)
    monkeypatch.setattr(stages, "resolve_legend", must_not_run)
    with pytest.raises(StageFailed) as failure:
        await stages.lookup_fighter(FighterRequest(entity="pickup truck", raw="a pickup truck"))
    assert str(failure.value) == stages.NOT_FOUND.format(name="pickup truck")


def test_a_cached_legend_never_replaces_a_seed_fighters_sheet() -> None:
    save_legend("pickup-truck", "Pickup truck")  # e.g. cached before it joined the seed list
    connection = connect()
    try:
        providers = (get_provider("chat"), get_provider("embedder"), get_provider("reranker"))
        sheet = asyncio.run(sheet_store.resolve_stat_sheet(connection, providers, "pickup truck"))
    finally:
        connection.close()
    assert sheet is not None and sheet.category == "vehicle"


def test_cached_legends_are_not_offered_as_challengers_or_listed_in_search() -> None:
    save_legend("chimera", "Chimera")
    assert all(s.fighter_id != "chimera" for s in challenger.cached_sheets())
    connection = connect()
    try:
        assert sheet_store.search_fighters(connection, "chimera") == []
    finally:
        connection.close()


class CountingChat:
    """Answers every call (slowly, so lookups overlap) and counts the calls."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, *, prompt_name, json_schema=None) -> str:
        self.calls += 1
        await asyncio.sleep(0.05)
        return json.dumps(answer())


async def test_two_lookups_of_one_new_legend_model_it_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = CountingChat()
    go_live(monkeypatch, chat)
    first, second = await asyncio.gather(
        stages.lookup_fighter(CHIMERA), stages.lookup_fighter(CHIMERA)
    )
    assert first == second and chat.calls == 1
