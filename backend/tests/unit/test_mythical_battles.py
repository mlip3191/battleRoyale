"""G09 (#39): battles use mythical creatures, from the file or modeled from their article."""

import httpx
import pytest

from app.models.matchup import FighterRequest, Matchup
from app.models.stats import StatName
from app.pipeline import stages
from app.pipeline.stages import StageFailed
from app.providers.live.http import ProviderError
from app.providers.registry import get_provider
from app.research import sheet_store
from tests.unit.test_lore import ARTICLE, FakeChat, answer


def matchup(first: str, second: str) -> Matchup:
    fighters = [{"entity": name, "raw": name} for name in (first, second)]
    return Matchup.model_validate({"fighters": fighters, "raw_text": f"{first} vs {second}"})


# Serve ARTICLE for any Wikipedia request, and use `chat` as the chat model in research.
def go_live(monkeypatch: pytest.MonkeyPatch, chat: FakeChat) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"ETag": '"123/abc"'}, content=ARTICLE.encode())

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
    with pytest.raises(StageFailed) as failure:
        await stages.lookup_fighter(FighterRequest(entity="chimera", raw="a chimera"))
    assert str(failure.value) == stages.LEGEND_UNAVAILABLE.format(name="chimera")


async def test_mock_mode_never_goes_online_for_an_unknown_name() -> None:
    assert sheet_store.legend_client() is None
    with pytest.raises(StageFailed) as failure:
        await stages.lookup_fighter(FighterRequest(entity="okapi", raw="an okapi"))
    assert str(failure.value) == stages.NOT_FOUND.format(name="okapi")
