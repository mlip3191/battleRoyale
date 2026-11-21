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


# --- #444: a generic kind of person or supernatural being (a priest, a samurai, "a god") -------


def test_a_generic_kind_estimate_is_a_living_human_sized_fighter() -> None:
    from app.models.stats import Body

    sheet = estimate_sheet("priest", "generic_kind")
    assert sheet.body == Body.LIVING and sheet.category == "human_archetype"
    assert all(stat.is_estimate and stat.source is None for stat in sheet.stats.values())
    for stat, value in sheet.stats.items():
        if stat not in BEHAVIORAL:
            assert value.method == "category_default"
            assert value.value == category_default("human_archetype", stat).value


async def test_generic_kinds_fall_back_to_estimates_and_named_ones_stay_blocked(
    monkeypatch,
) -> None:
    from app.pipeline.stages import StageFailed
    from tests.unit.test_legend_cache import ScriptedChat
    from tests.unit.test_mythical_battles import go_live

    # the model's fixed reasons for each name; code only maps them
    for name, reason in [
        ("priest", "generic_kind"),
        ("monk", "generic_kind"),
        ("god", "generic_kind"),
        ("sword", "object_or_machine"),
    ]:
        go_live(monkeypatch, ScriptedChat({"found": False, "reason": reason}))
        sheet, estimated = await stages.lookup_fighter_or_estimate(
            FighterRequest(entity=name, raw=f"a {name}")
        )
        assert estimated and sheet.display_name == name.capitalize()
        from app.models.stats import Body

        if name == "sword":  # an object stays an inert object
            assert sheet.body == Body.INERT and sheet.category == ESTIMATE_CATEGORY
        else:  # a generic kind fights as a living human archetype
            assert sheet.body == Body.LIVING and sheet.category == "human_archetype"
    for name, reason in [("pope", "person"), ("zeus", "deity"), ("rifle", "weapon")]:
        go_live(monkeypatch, ScriptedChat({"found": False, "reason": reason}))
        with pytest.raises(StageFailed):
            await stages.lookup_fighter_or_estimate(FighterRequest(entity=name, raw=name))


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


async def test_a_bare_god_or_angel_is_a_generic_kind_without_asking_the_model(monkeypatch) -> None:
    from app.models.stats import Body
    from tests.unit.test_legend_cache import ScriptedChat
    from tests.unit.test_mythical_battles import go_live

    # the article for "God" is about one figure, so the model would say deity; code never asks
    chat = ScriptedChat({"found": False, "reason": "deity"})
    go_live(monkeypatch, chat)
    for name in ("god", "angel", "demons"):
        sheet, estimated = await stages.lookup_fighter_or_estimate(
            FighterRequest(entity=name, raw=f"a {name}")
        )
        assert estimated and sheet.body == Body.LIVING and sheet.category == "human_archetype"
    assert chat.calls == 0


async def test_a_bare_god_is_a_living_fighter_in_mock_mode_too() -> None:
    from app.models.stats import Body

    sheet, estimated = await stages.lookup_fighter_or_estimate(
        FighterRequest(entity="god", raw="a god")
    )
    assert estimated and sheet.body == Body.LIVING


async def test_a_spartan_warrior_fights_as_a_generic_human(monkeypatch) -> None:
    from app.models.stats import Body
    from tests.unit.test_legend_cache import ScriptedChat
    from tests.unit.test_mythical_battles import go_live

    go_live(monkeypatch, ScriptedChat({"found": False, "reason": "generic_kind"}))
    sheet, estimated = await stages.lookup_fighter_or_estimate(
        FighterRequest(entity="spartan warrior", raw="100 spartan warriors")
    )
    assert estimated and sheet.body == Body.LIVING and sheet.category == "human_archetype"
    assert all(stat.is_estimate for stat in sheet.stats.values())


# --- D-69: military units carry a firearm; gods of mythology fight as generic kinds ----------


def test_an_armed_unit_is_a_living_human_with_a_labeled_firearm_estimate() -> None:
    from app.models.stats import Body
    from app.research.estimate_sheet import FIREARM_STATS

    sheet = estimate_sheet("navy seal", "armed_unit")
    assert sheet.body == Body.LIVING and sheet.category == "human_archetype"
    assert sheet.weapons == ["weapon_ranged"]
    assert all(stat.is_estimate and stat.source is None for stat in sheet.stats.values())
    for stat, value in FIREARM_STATS.items():
        assert sheet.stats[stat].value == value
        assert sheet.stats[stat].low < value < sheet.stats[stat].high
        assert "Firearm assumption" in (sheet.stats[stat].note or "")
    assert (
        sheet.stats[StatName.MASS].value == category_default("human_archetype", StatName.MASS).value
    )
    assert sheet.sheet_hash == compute_sheet_hash(sheet.stats)


def test_a_god_of_mythology_is_a_living_fighter_without_a_firearm() -> None:
    from app.models.stats import Body

    sheet = estimate_sheet("zeus", "myth_deity")
    assert sheet.body == Body.LIVING and sheet.category == "human_archetype"
    assert "weapon_ranged" not in sheet.weapons


async def test_military_units_and_gods_of_mythology_fight_and_living_religions_stay_blocked(
    monkeypatch,
) -> None:
    from app.models.stats import Body
    from tests.unit.test_legend_cache import ScriptedChat
    from tests.unit.test_mythical_battles import go_live

    for name, reason in [("navy seal", "armed_unit"), ("zeus", "myth_deity")]:
        go_live(monkeypatch, ScriptedChat({"found": False, "reason": reason}))
        sheet, estimated = await stages.lookup_fighter_or_estimate(
            FighterRequest(entity=name, raw=name)
        )
        assert estimated and sheet.body == Body.LIVING
    go_live(monkeypatch, ScriptedChat({"found": False, "reason": "deity"}))
    with pytest.raises(StageFailed):
        await stages.lookup_fighter_or_estimate(FighterRequest(entity="vishnu", raw="vishnu"))


async def test_a_navy_seal_is_an_armed_unit_without_asking_the_model(monkeypatch) -> None:
    from tests.unit.test_legend_cache import ScriptedChat
    from tests.unit.test_mythical_battles import go_live

    # the article is about one real unit, so the model might say person; code never asks
    chat = ScriptedChat({"found": False, "reason": "person"})
    go_live(monkeypatch, chat)
    sheet, estimated = await stages.lookup_fighter_or_estimate(
        FighterRequest(entity="navy seal", raw="25 US navy seals")
    )
    assert estimated and sheet.weapons == ["weapon_ranged"]
    assert chat.calls == 0


def test_only_the_exact_military_words_skip_the_lookup() -> None:
    from app.research.lore import code_kind

    assert code_kind("marine") == "armed_unit" and code_kind("navy seal") == "armed_unit"
    for name in ("marine iguana", "marine biologist", "seal", "elephant seal", "soldier ant"):
        assert code_kind(name) is None, name


# --- #517: the lookup's animal kind and size class shape an estimate ---------------------


def test_the_label_lists_match_the_tables_that_turn_them_into_numbers() -> None:
    from app.research import lore
    from app.research.estimate_sheet import ANIMAL_KINDS, SIZE_FACTORS

    assert set(ANIMAL_KINDS) == lore.ANIMAL_CATEGORIES
    assert set(SIZE_FACTORS) == lore.SIZE_CLASSES
    for kind in ANIMAL_KINDS:
        category_default(kind, StatName.MASS)  # raises for a category with no defaults


def test_a_mouse_and_a_moose_differ_by_size_class() -> None:
    mouse = estimate_sheet("field mouse", "real_animal", category="mammal", size_class="tiny")
    moose = estimate_sheet("moose", "real_animal", category="mammal", size_class="large")
    medium = category_default("mammal", StatName.MASS).value
    assert mouse.stats[StatName.MASS].value == pytest.approx(medium * 0.001)
    assert moose.stats[StatName.MASS].value == pytest.approx(medium * 10)
    for sheet in (mouse, moose):
        assert all(stat.is_estimate for stat in sheet.stats.values())
        mass = sheet.stats[StatName.MASS]
        assert mass.low < mass.value < mass.high and "Sized as a" in (mass.note or "")
        assert sheet.sheet_hash == compute_sheet_hash(sheet.stats)
    # square-cube: height with the cube root, force with the two-thirds power
    assert moose.stats[StatName.SIZE].value == pytest.approx(
        category_default("mammal", StatName.SIZE).value * 10 ** (1 / 3)
    )
    assert moose.stats[StatName.ATTACK_FORCE].value == pytest.approx(
        category_default("mammal", StatName.ATTACK_FORCE).value * 10 ** (2 / 3)
    )


def test_the_animal_kind_sets_its_defaults_weapon_and_habitat() -> None:
    ostrich = estimate_sheet("ostrich", "real_animal", category="bird")
    shark = estimate_sheet("shark", "real_animal", category="fish")
    assert (ostrich.category, ostrich.weapons, ostrich.habitat) == ("bird", ["beak"], "land")
    assert (shark.category, shark.habitat) == ("fish", "water")
    assert ostrich.stats[StatName.MASS].value == category_default("bird", StatName.MASS).value


def test_odd_labels_fall_back_to_a_medium_mammal_and_soldiers_stay_human_sized() -> None:
    odd = estimate_sheet("thing", "real_animal", category="dragon", size_class="gigantic")
    plain = estimate_sheet("thing", "real_animal")
    assert odd.stats == plain.stats and odd.category == "mammal"
    seal = estimate_sheet("navy seal", "armed_unit", size_class="huge")
    assert (
        seal.stats[StatName.MASS].value == category_default("human_archetype", StatName.MASS).value
    )
    titan = estimate_sheet("titan", "generic_kind", size_class="huge")
    assert titan.stats[StatName.MASS].value == pytest.approx(
        category_default("human_archetype", StatName.MASS).value * 100
    )


async def test_the_lookup_labels_shape_the_battle_sheet_and_are_remembered(monkeypatch) -> None:
    from app.research import sheet_store
    from tests.unit.test_legend_cache import ScriptedChat
    from tests.unit.test_mythical_battles import go_live

    chat = ScriptedChat(
        {"found": False, "reason": "real_animal", "category": "bird", "size_class": "huge"}
    )
    go_live(monkeypatch, chat)
    fighter = FighterRequest(entity="ostrich", raw="an ostrich")
    first, estimated = await stages.lookup_fighter_or_estimate(fighter)
    again, _ = await stages.lookup_fighter_or_estimate(fighter)
    assert estimated and first.category == "bird" and first.weapons == ["beak"]
    assert first.stats[StatName.MASS].value == pytest.approx(
        category_default("bird", StatName.MASS).value * 100
    )
    assert again == first and chat.calls == 1  # remembered, not asked again
    assert sheet_store.not_a_legend_shape("ostrich") == ("bird", "huge")
