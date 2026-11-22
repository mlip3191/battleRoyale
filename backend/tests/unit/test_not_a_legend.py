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
from app.providers.live.http import ProviderError
from app.research import lore, sheet_store
from app.research.lore import NONSENSE, UNAVAILABLE, LoreOutcome
from tests.unit.test_legend_cache import ScriptedChat
from tests.unit.test_lore import FakeChat, answer, run
from tests.unit.test_mythical_battles import go_live, matchup

NOT_FOUND = {"found": False, "body_analog": None, "quote": None}
ALLOWED = ["real_animal", "object_or_machine", "generic_kind", "armed_unit", "myth_deity"]
REFUSED = ["person", "deity", "named_character", "weapon", "nonsense"]


def not_a_legend(reason: object) -> dict:
    return answer(**NOT_FOUND, reason=reason)


@pytest.mark.parametrize("reason", ALLOWED)
def test_a_real_animal_or_object_is_not_a_legend(reason: str) -> None:
    outcome = run(FakeChat(not_a_legend(reason)))
    # #453: the outcome now carries the reason, so a real animal can fight as one
    assert outcome == LoreOutcome(not_a_legend=True, kind=reason) and not outcome.blocked


@pytest.mark.parametrize("reason", [*REFUSED, "sparkly", "", None, 7, ["real_animal"]])
def test_any_other_reason_or_a_missing_or_invalid_one_stays_blocked(reason: object) -> None:
    assert run(FakeChat(not_a_legend(reason))) == NONSENSE


def test_a_reason_cannot_rescue_an_answer_that_found_a_legend_but_failed_checks() -> None:
    # found true with a made-up quote is a failed check, not "not a legend", whatever the reason.
    bad = answer(quote="The chimera was the size of a whale.", reason="real_animal")
    assert run(FakeChat(bad)) == NONSENSE


# --- A name with no Wikipedia article: the model is still asked, with the name alone (#403, PM).


@pytest.mark.parametrize("reason", ALLOWED)
def test_no_article_and_a_harmless_reason_is_not_a_legend(reason: str) -> None:
    chat = FakeChat(not_a_legend(reason))
    assert run(chat, article=None) == LoreOutcome(not_a_legend=True, kind=reason)
    assert chat.calls == 1


@pytest.mark.parametrize("reason", [*REFUSED, "sparkly", None])
def test_no_article_and_any_other_reason_is_blocked(reason: object) -> None:
    assert run(FakeChat(not_a_legend(reason)), article=None) == NONSENSE


def test_no_article_and_found_true_is_blocked_because_there_is_no_text_to_check() -> None:
    assert run(FakeChat(answer()), article=None) == NONSENSE


def test_no_article_and_a_model_that_is_down_is_unavailable() -> None:
    down = FakeChat(ProviderError("down"), ProviderError("down"))
    assert run(down, article=None) == UNAVAILABLE


def test_the_model_is_told_there_is_no_article() -> None:
    seen: list[str] = []

    class Spy(FakeChat):
        async def complete(self, messages, *, prompt_name, json_schema=None) -> str:
            seen.append(messages[1]["content"])
            return await super().complete(messages, prompt_name=prompt_name)

    run(Spy(not_a_legend("real_animal")), article=None)
    assert lore.NO_ARTICLE in seen[0]


def test_the_reason_ignores_case_and_surrounding_spaces() -> None:
    assert lore.outcome_for_not_found(" Real_Animal ").kind == "real_animal"
    assert lore.outcome_for_not_found("OBJECT_OR_MACHINE").kind == "object_or_machine"
    assert lore.outcome_for_not_found("real animal") == NONSENSE  # a different word, not a match


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
    # not a refusal, so not in the refusal memory; since #445 it has its own short memory, so the
    # second battle made no new lookup
    assert "moose" not in sheet_store._REFUSED and chat.calls == 1
    zeus = ScriptedChat(not_a_legend("deity"))
    go_live(monkeypatch, zeus)
    with pytest.raises(StageFailed):
        await stages.lookup_fighter_or_estimate(FighterRequest(entity="zeus", raw="zeus"))
    assert "zeus" in sheet_store._REFUSED


async def test_a_live_name_with_no_article_is_asked_about_and_fights_on_estimates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = ScriptedChat(not_a_legend("real_animal"))
    go_live(monkeypatch, chat, status=404)  # Wikipedia has no page for it
    sheet, estimated = await stages.lookup_fighter_or_estimate(
        FighterRequest(entity="quokka", raw="a quokka")
    )
    assert estimated and chat.calls == 1 and sheet.display_name.lower() == "quokka"


@pytest.mark.parametrize("reason", ["person", "nonsense"])
async def test_a_live_name_with_no_article_and_a_refusal_reason_is_blocked_and_remembered(
    monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    chat = ScriptedChat(not_a_legend(reason))
    go_live(monkeypatch, chat, status=404)
    with pytest.raises(StageFailed) as failure:
        await stages.lookup_fighter_or_estimate(
            FighterRequest(entity="dave", raw="my coworker dave")
        )
    assert str(failure.value) == stages.LEGEND_BLOCKED.format(name="dave")
    assert "dave" in sheet_store._REFUSED


async def test_the_prompt_lists_every_reason_code_knows() -> None:
    prompt = lore.load_prompt()
    assert all(reason in prompt for reason in [*ALLOWED, *REFUSED])
    assert set(lore.NOT_A_LEGEND_REASONS) == set(ALLOWED)
    assert lore.NOT_A_LEGEND_REASONS | lore.REFUSAL_REASONS == {*ALLOWED, *REFUSED}
    assert not lore.NOT_A_LEGEND_REASONS & lore.REFUSAL_REASONS


# --- #445: a short memory for "not a legend", so a repeated unknown fighter costs no new lookup.


async def lookup(name: str = "moose") -> tuple:
    return await stages.lookup_fighter_or_estimate(FighterRequest(entity=name, raw=f"a {name}"))


async def test_a_second_battle_with_the_same_unknown_fighter_makes_no_new_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = ScriptedChat(not_a_legend("real_animal"))
    go_live(monkeypatch, chat)
    first, _ = await lookup()
    second, estimated = await lookup()
    assert estimated and second.display_name == first.display_name
    assert chat.calls == 1  # the second battle asked nobody


async def test_the_lookup_is_made_again_after_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = ScriptedChat(not_a_legend("real_animal"))
    go_live(monkeypatch, chat)
    await lookup()
    expired = sheet_store.time.monotonic() - sheet_store.NOT_A_LEGEND_MEMORY_S - 1
    monkeypatch.setitem(sheet_store._NOT_A_LEGEND, "moose", expired)  # backdated, not a fake clock
    await lookup()
    assert chat.calls == 2 and "moose" in sheet_store._NOT_A_LEGEND  # remembered afresh


async def test_each_name_has_its_own_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = ScriptedChat(not_a_legend("real_animal"))
    go_live(monkeypatch, chat)
    await lookup("moose")
    await lookup("forklift")
    assert chat.calls == 2 and set(sheet_store._NOT_A_LEGEND) == {"moose", "forklift"}


async def test_the_two_memories_stay_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    go_live(monkeypatch, ScriptedChat(not_a_legend("real_animal")))
    await lookup("moose")
    go_live(monkeypatch, ScriptedChat(not_a_legend("deity")))
    with pytest.raises(StageFailed):
        await lookup("zeus")
    assert set(sheet_store._NOT_A_LEGEND) == {"moose"}  # no refusal in here
    assert set(sheet_store._REFUSED) == {"zeus"}  # and no "not a legend" in there


async def test_an_outage_is_not_remembered_as_not_a_legend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    go_live(monkeypatch, ScriptedChat(not_a_legend("real_animal")), status=503)
    with pytest.raises(StageFailed):
        await lookup()
    assert not sheet_store._NOT_A_LEGEND


def test_forgetting_clears_both_memories_and_recording_prunes_expired_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expired = sheet_store.time.monotonic() - sheet_store.NOT_A_LEGEND_MEMORY_S - 1
    monkeypatch.setitem(sheet_store._NOT_A_LEGEND, "old-name", expired)
    sheet_store.remember_not_a_legend("new-name")
    assert set(sheet_store._NOT_A_LEGEND) == {"new-name"}
    sheet_store.remember_refusal("zeus")
    sheet_store.forget_refusals()
    assert not sheet_store._NOT_A_LEGEND and not sheet_store._REFUSED


def test_flies_is_kept_only_as_a_real_yes_or_no_for_a_real_animal() -> None:  # #542
    assert lore.outcome_for_not_found("real_animal", "bird", "small", True).flies is True
    assert lore.outcome_for_not_found("real_animal", "bird", "medium", False).flies is False
    for odd in ("yes", "sometimes", 1, None):
        assert lore.outcome_for_not_found("real_animal", "bird", "small", odd).flies is None
    assert lore.outcome_for_not_found("generic_kind", None, "medium", True).flies is None
    assert lore.outcome_for_not_found("person", None, None, True).blocked  # still a refusal


def test_the_animal_kind_and_size_class_are_kept_only_from_their_fixed_lists() -> None:
    outcome = lore.outcome_for_not_found("real_animal", " Bird ", "HUGE")
    assert (outcome.kind, outcome.category, outcome.size_class) == ("real_animal", "bird", "huge")
    odd = lore.outcome_for_not_found("real_animal", "dragon", 7)
    assert (odd.category, odd.size_class) == (None, None)  # off the list or not a word: dropped
    titan = lore.outcome_for_not_found("generic_kind", "mammal", "huge")
    assert (titan.category, titan.size_class) == (None, "huge")  # a kind only for an animal
    seal = lore.outcome_for_not_found("armed_unit", None, "huge")
    assert seal.size_class is None  # soldiers stay human-sized
    assert lore.outcome_for_not_found("deity", "mammal", "huge") == NONSENSE
