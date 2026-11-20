"""#345: a plausible fighter with no sheet fights on an all-estimate sheet from code defaults."""

import asyncio
from pathlib import Path

import pytest

from app.config import use_settings
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.battle import BattleRecord, StageStatus
from app.models.matchup import FighterRequest, Matchup
from app.models.stats import StatName, StatSheet
from app.pipeline import orchestrator, stages
from app.pipeline.orchestrator import ESTIMATED_FIGHTER, ESTIMATED_FIGHTERS, run_battle
from app.pipeline.stages import StageFailed
from app.pipeline.store import BattleStore
from app.research.defaults import behavioral_default, category_default
from app.research.estimate_sheet import ESTIMATE_CATEGORY, estimate_sheet
from app.research.lore import NONSENSE, UNAVAILABLE
from app.research.sheet_hash import compute_sheet_hash
from app.research.statsheet import BEHAVIORAL
from tests.conftest import mock_settings

SIM_RUNS = 20  # enough for a verdict; keeps each battle quick
HARD_TIMEOUT = 20.0  # no battle in this file may take longer than this
SMALL_BUDGET = 8.0  # every stage's limit in these tests
WOLVERINE = FighterRequest(entity="wolverine", raw="a wolverine")


@pytest.fixture(autouse=True)
def _quick_and_bounded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    use_settings(mock_settings(sim_runs=SIM_RUNS, data_dir=tmp_path / "data"))
    for stage in stages.STAGE_BUDGETS_S:
        monkeypatch.setitem(stages.STAGE_BUDGETS_S, stage, SMALL_BUDGET)


def matchup(*fighters: dict[str, object]) -> Matchup:
    sides = [{"raw": f["entity"], **f} for f in fighters]
    names = " vs ".join(str(f["entity"]) for f in fighters)
    return Matchup.model_validate({"fighters": sides, "raw_text": names})


# Run one battle to the end (or fail the test after HARD_TIMEOUT) and return its record.
async def battle(fight: Matchup) -> BattleRecord:
    store = BattleStore()
    record = await store.create(fight)
    await asyncio.wait_for(run_battle(record.battle_id, store), HARD_TIMEOUT)
    final = await store.get(record.battle_id)
    assert final is not None
    return final


def research_stage(record: BattleRecord) -> StageStatus:
    return next(stage for stage in record.stages if stage.stage == "research")


def saved_sheet_count() -> int:
    connection = connect()
    try:
        apply_migrations(connection)
        return connection.execute("SELECT COUNT(*) FROM stat_sheets").fetchone()[0]
    finally:
        connection.close()


# Every stat on the sheet is the code default for its category, labeled as an estimate.
def assert_all_code_defaults(sheet: StatSheet) -> None:
    assert set(sheet.stats) == set(StatName)
    for name, stat in sheet.stats.items():
        expected = (
            behavioral_default(ESTIMATE_CATEGORY, name)
            if name in BEHAVIORAL
            else category_default(ESTIMATE_CATEGORY, name)
        )
        assert expected is not None
        assert stat.is_estimate and stat.source is None
        assert stat.method in ("category_default", "assumption")
        assert (stat.value, stat.low, stat.high) == (expected.value, expected.low, expected.high)
        assert (stat.note or "").startswith("Estimate: we have no stat sheet")


def test_the_estimate_sheet_is_all_code_defaults_and_valid() -> None:
    sheet = estimate_sheet("wolverine")
    assert (sheet.fighter_id, sheet.display_name, sheet.media_name) == (
        "wolverine",
        "Wolverine",
        "wolverine",
    )
    assert (sheet.category, sheet.body, sheet.habitat, sheet.weapons) == (
        "other",
        "inert",
        "land",
        ["none"],
    )
    assert sheet.lore is None
    assert sheet.sheet_hash == compute_sheet_hash(sheet.stats)
    assert StatSheet.model_validate(sheet.model_dump()) == sheet
    assert_all_code_defaults(sheet)


@pytest.mark.parametrize(
    "typed, display, fighter_id",
    [
        ("polar bear", "Polar bear", "polar-bear"),
        ("forklift!", "Forklift", "forklift"),
        ("  rock / paper  ", "Rock paper", "rock-paper"),
        ("$$$", "Unknown fighter", "unknown-fighter"),
    ],
)
def test_the_estimate_sheet_name_passes_the_name_allowlist(
    typed: str, display: str, fighter_id: str
) -> None:
    sheet = estimate_sheet(typed)
    assert (sheet.display_name, sheet.fighter_id) == (display, fighter_id)


async def test_an_unknown_fighter_reaches_done_on_an_all_estimate_sheet() -> None:
    record = await battle(matchup({"entity": "wolverine"}, {"entity": "grizzly bear"}))
    assert record.status == "done" and record.result is not None
    research = research_stage(record)
    assert research.status == "fallback"
    assert research.detail == "We have no stat sheet for 'wolverine', so its stats are estimates."
    wolverine, bear = record.stat_sheets
    assert wolverine == estimate_sheet("wolverine")
    assert_all_code_defaults(wolverine)
    assert bear.fighter_id == "grizzly-bear"
    # The estimate must not poison the sheet store for a later, real sheet.
    assert saved_sheet_count() == 0


async def test_two_unknown_fighters_share_one_plain_note() -> None:
    record = await battle(matchup({"entity": "wolverine"}, {"entity": "forklift"}))
    assert record.status == "done"
    assert research_stage(record).detail == ESTIMATED_FIGHTERS.format(
        names="'wolverine' and 'forklift'"
    )
    assert all(stat.is_estimate for sheet in record.stat_sheets for stat in sheet.stats.values())


async def test_the_estimate_note_comes_before_a_missing_size_reference_note() -> None:
    fight = matchup(
        {"entity": "wolverine"},
        {"entity": "duck", "size_reference": "school bus", "raw": "a school-bus-sized duck"},
    )
    record = await battle(fight)
    assert record.status == "done"
    assert research_stage(record).detail == " ".join(
        (
            ESTIMATED_FIGHTER.format(names="'wolverine'"),
            orchestrator.MISSING_REFERENCE.format(names="'school bus'"),
        )
    )


async def test_research_lists_only_the_fighters_on_estimates() -> None:
    found = await stages.research(matchup({"entity": "gray wolf"}, {"entity": "wolverine"}))
    assert found.estimated == ["wolverine"]
    assert found.sheets[0].fighter_id == "gray-wolf"
    found = await stages.research(matchup({"entity": "gray wolf"}, {"entity": "duck"}))
    assert found.estimated == []


@pytest.mark.parametrize(
    "outcome, message",
    [(NONSENSE, stages.LEGEND_BLOCKED), (UNAVAILABLE, stages.LEGEND_UNAVAILABLE)],
    ids=["blocked", "unavailable"],
)
async def test_a_blocked_or_unavailable_legend_still_fails_the_battle(
    monkeypatch: pytest.MonkeyPatch, outcome: object, message: str
) -> None:
    async def legend(*_: object) -> object:
        return outcome

    monkeypatch.setattr(stages, "resolve_legend", legend)
    with pytest.raises(StageFailed) as failure:
        await stages.lookup_fighter(WOLVERINE)
    assert str(failure.value) == message.format(name="wolverine")
    record = await battle(matchup({"entity": "wolverine"}, {"entity": "grizzly bear"}))
    assert record.status == "failed" and record.result is None
    assert (research_stage(record).status, research_stage(record).detail) == (
        "failed",
        message.format(name="wolverine"),
    )


async def test_a_seed_fighter_whose_build_failed_still_fails_the_battle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sheet(*_: object) -> None:
        return None

    monkeypatch.setattr(stages, "lookup_sheet", no_sheet)
    record = await battle(matchup({"entity": "pickup truck"}, {"entity": "wolverine"}))
    assert record.status == "failed"
    assert (research_stage(record).status, research_stage(record).detail) == (
        "failed",
        stages.NOT_FOUND.format(name="pickup truck"),
    )


# --- #453: a real animal off the seed list fights as a living animal, not an inert object ------
# The legend lookup's fixed reason (real_animal / object_or_machine) now reaches the estimate.
# Code decides from that reason alone: no model text, no model number. Every stat stays a labeled
# estimate from code defaults.


def test_a_real_animal_estimate_is_a_living_fighter_with_a_bite() -> None:
    from app.models.stats import Body

    sheet = estimate_sheet("moose", "real_animal")
    assert sheet.body == Body.LIVING and "teeth" in sheet.weapons and sheet.habitat == "land"
    assert sheet.category == "mammal" and sheet.display_name == "Moose"
    assert all(stat.is_estimate and stat.source is None for stat in sheet.stats.values())
    assert sheet.stats[StatName.ATTACK_FORCE].value > 0
    assert sheet.sheet_hash == compute_sheet_hash(sheet.stats)


def test_an_object_or_no_reason_stays_inert_as_before() -> None:
    from app.models.stats import Body

    assert estimate_sheet("forklift", "object_or_machine") == estimate_sheet("forklift")
    plain = estimate_sheet("forklift")
    assert plain.body == Body.INERT and plain.category == ESTIMATE_CATEGORY
    assert estimate_sheet("moose", None) == estimate_sheet("moose")  # mock mode: no reason
    assert estimate_sheet("moose", "something else") == estimate_sheet("moose")  # fail closed


def test_the_animal_estimate_is_the_mammal_category_default_and_nothing_else() -> None:
    sheet = estimate_sheet("moose", "real_animal")
    for stat, value in sheet.stats.items():
        if stat in BEHAVIORAL:
            continue
        assert value.method == "category_default"
        assert value.value == category_default("mammal", stat).value


async def test_a_real_animal_that_is_not_a_legend_keeps_its_reason(monkeypatch) -> None:
    from app.models.stats import Body
    from app.research import sheet_store
    from tests.unit.test_legend_cache import ScriptedChat
    from tests.unit.test_mythical_battles import go_live

    chat = ScriptedChat({"found": False, "reason": "real_animal"})
    go_live(monkeypatch, chat)
    request = FighterRequest(entity="moose", raw="a moose")
    first, estimated = await stages.lookup_fighter_or_estimate(request)
    again, _ = await stages.lookup_fighter_or_estimate(request)  # answered from the memory
    assert estimated and first.body == Body.LIVING and again.body == Body.LIVING
    assert chat.calls == 1 and sheet_store.not_a_legend_kind("moose") == "real_animal"


async def test_an_object_that_is_not_a_legend_stays_inert(monkeypatch) -> None:
    from app.models.stats import Body
    from tests.unit.test_legend_cache import ScriptedChat
    from tests.unit.test_mythical_battles import go_live

    go_live(monkeypatch, ScriptedChat({"found": False, "reason": "object_or_machine"}))
    sheet, estimated = await stages.lookup_fighter_or_estimate(
        FighterRequest(entity="forklift", raw="a forklift")
    )
    assert estimated and sheet.body == Body.INERT


def test_a_moose_v_a_forklift_is_no_longer_a_no_contest() -> None:
    from app.simulation.engine import run

    fight = matchup({"entity": "moose"}, {"entity": "forklift"})
    sheets = [
        estimate_sheet("moose", "real_animal"),
        estimate_sheet("forklift", "object_or_machine"),
    ]
    assert run(fight, sheets, runs=100, explain=False).outcome == "win_0"


def test_a_tiger_does_not_lose_to_a_small_bird_every_time() -> None:
    # The bug bash's goose has no hand-verified sheet; the duck (a similar bird) stands in.
    from app.models.stats import StatSheet
    from app.simulation import benchmark as bm
    from app.simulation.engine import run

    duck = bm.seed_sheets().get(FighterRequest(entity="duck", raw="duck"))
    assert isinstance(duck, StatSheet)
    fight = matchup({"entity": "tiger"}, {"entity": "duck"})
    result = run(fight, [estimate_sheet("tiger", "real_animal"), duck], runs=200, explain=False)
    assert result.win_prob[1] < 1.0 and result.outcome != "no_contest"
