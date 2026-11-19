"""#403: in live mode a plausible real fighter (a moose, a forklift) fights on estimates, while a
person, a deity, a named character, a weapon or nonsense stays blocked.

When the legend lookup answers found false, the model also picks one reason from a fixed list.
Code maps real_animal and object_or_machine to "not a legend" (an estimate sheet, #401); every
other reason, a missing one or an invalid one stays blocked (fail closed). Mocked chat and HTTP.
"""

import pytest

from app.models.matchup import FighterRequest
from app.pipeline import stages
from app.pipeline.stages import StageFailed
from app.research import lore, sheet_store
from app.research.lore import NONSENSE, NOT_A_LEGEND
from tests.unit.test_legend_cache import ScriptedChat
from tests.unit.test_lore import FakeChat, answer, run
from tests.unit.test_mythical_battles import go_live, matchup

NOT_FOUND = {"found": False, "body_analog": None, "quote": None}
ALLOWED = ["real_animal", "object_or_machine"]
REFUSED = ["person", "deity", "named_character", "weapon", "nonsense"]


def not_a_legend(reason: object) -> dict:
    return answer(**NOT_FOUND, reason=reason)


@pytest.mark.parametrize("reason", ALLOWED)
def test_a_real_animal_or_object_is_not_a_legend(reason: str) -> None:
    outcome = run(FakeChat(not_a_legend(reason)))
    assert outcome == NOT_A_LEGEND and outcome.not_a_legend and not outcome.blocked


@pytest.mark.parametrize("reason", [*REFUSED, "sparkly", "", None, 7, ["real_animal"]])
def test_any_other_reason_or_a_missing_or_invalid_one_stays_blocked(reason: object) -> None:
    assert run(FakeChat(not_a_legend(reason))) == NONSENSE


def test_a_reason_cannot_rescue_an_answer_that_found_a_legend_but_failed_checks() -> None:
    # found true with a made-up quote is a failed check, not "not a legend", whatever the reason.
    bad = answer(quote="The chimera was the size of a whale.", reason="real_animal")
    assert run(FakeChat(bad)) == NONSENSE


def test_no_article_means_nothing_to_ask_so_it_is_not_a_legend() -> None:
    chat = FakeChat()
    assert run(chat, article=None) == NOT_A_LEGEND and chat.calls == 0


async def fighter_for(monkeypatch: pytest.MonkeyPatch, name: str, reason: object) -> tuple:
    go_live(monkeypatch, ScriptedChat(not_a_legend(reason)))
    return await stages.lookup_fighter_or_estimate(FighterRequest(entity=name, raw=f"a {name}"))


@pytest.mark.parametrize("name", ["moose", "forklift"])
async def test_a_moose_and_a_forklift_fight_on_all_estimate_sheets(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    reason = "real_animal" if name == "moose" else "object_or_machine"
    sheet, estimated = await fighter_for(monkeypatch, name, reason)
    assert estimated and sheet.display_name.lower() == name
    assert all(stat.is_estimate for stat in sheet.stats.values())


async def test_research_ends_with_the_estimate_note_for_a_live_moose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    go_live(monkeypatch, ScriptedChat(not_a_legend("real_animal")))
    found = await stages.research(matchup("moose", "duck"))
    assert found.estimated == ["moose"] and len(found.sheets) == 2


@pytest.mark.parametrize("reason", REFUSED)
async def test_a_person_deity_character_weapon_or_nonsense_still_ends_blocked(
    monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    go_live(monkeypatch, ScriptedChat(not_a_legend(reason)))
    with pytest.raises(StageFailed) as failure:
        await stages.lookup_fighter_or_estimate(FighterRequest(entity="zeus", raw="zeus"))
    assert str(failure.value) == stages.LEGEND_BLOCKED.format(name="zeus")


async def test_an_invalid_reason_fails_closed_in_the_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    go_live(monkeypatch, ScriptedChat(not_a_legend("an animal, probably")))
    with pytest.raises(StageFailed):
        await stages.lookup_fighter_or_estimate(FighterRequest(entity="moose", raw="moose"))


async def test_a_legend_lookup_outage_is_still_unavailable_not_an_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    go_live(monkeypatch, ScriptedChat(answer()), status=503)
    with pytest.raises(StageFailed) as failure:
        await stages.lookup_fighter_or_estimate(FighterRequest(entity="moose", raw="moose"))
    assert str(failure.value) == stages.LEGEND_UNAVAILABLE.format(name="moose")


async def test_only_real_refusals_go_into_the_refusal_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = ScriptedChat(not_a_legend("real_animal"))
    go_live(monkeypatch, chat)
    for _ in range(2):
        await stages.lookup_fighter_or_estimate(FighterRequest(entity="moose", raw="moose"))
    assert "moose" not in sheet_store._REFUSED and chat.calls == 2  # asked again, not remembered
    zeus = ScriptedChat(not_a_legend("deity"))
    go_live(monkeypatch, zeus)
    with pytest.raises(StageFailed):
        await stages.lookup_fighter_or_estimate(FighterRequest(entity="zeus", raw="zeus"))
    assert "zeus" in sheet_store._REFUSED


async def test_the_prompt_lists_every_reason_code_knows() -> None:
    prompt = lore.load_prompt()
    assert all(reason in prompt for reason in [*ALLOWED, *REFUSED])
    assert set(lore.NOT_A_LEGEND_REASONS) == set(ALLOWED)
