"""#518: research for an unlisted real animal at battle time (live mode only).

The article fetch, ingest and extraction are stood in for: these tests check what code does with
their results (merging only quoted stats, the time limit, the cache, search and the challenger).
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import use_settings
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.matchup import FighterRequest
from app.models.stats import Source, StatName, StatSheet, StatValue
from app.pipeline import challenger, stages
from app.research import on_demand
from app.research.estimate_sheet import estimate_sheet
from app.research.sheet_store import cached_sheet, save_sheet, search_fighters
from tests.conftest import mock_settings

MOOSE = estimate_sheet("moose", "real_animal", category="mammal", size_class="large")


@pytest.fixture(autouse=True)
async def _clean(tmp_path: Path):
    use_settings(mock_settings(data_dir=tmp_path / "data"))
    await on_demand.forget_research()
    yield
    await on_demand.forget_research()


# Pretend to be in live mode for researched_or_estimate's mock-mode check.
def go_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(on_demand, "get_settings", lambda: SimpleNamespace(provider_mode="live"))


# A quoted mass, as extraction gives one.
def quoted_mass(value: float) -> StatValue:
    return StatValue(
        value=value,
        unit="kg",
        source=Source(
            title="Moose",
            url="https://en.wikipedia.org/wiki/Moose",
            quote=f"Bulls weigh {value:g} kg",
            retrieved_at="2026-11-21T00:00:00Z",
            license="CC BY-SA 4.0",
        ),
        confidence="medium",
        is_estimate=False,
        method="extracted",
    )


def researched(estimate: StatSheet, mass: float = 450.0) -> StatSheet:
    sheet = on_demand.merged(
        estimate,
        estimate.model_copy(update={"stats": {**estimate.stats, StatName.MASS: quoted_mass(mass)}}),
    )
    assert sheet is not None
    return sheet


def test_only_quoted_stats_replace_the_estimate() -> None:
    sheet = researched(MOOSE)
    assert sheet.stats[StatName.MASS].value == 450.0 and not sheet.stats[StatName.MASS].is_estimate
    others = {s: v for s, v in sheet.stats.items() if s != StatName.MASS}
    assert others == {s: v for s, v in MOOSE.stats.items() if s != StatName.MASS}
    assert sheet.sheet_hash != MOOSE.sheet_hash
    assert on_demand.merged(MOOSE, MOOSE) is None  # nothing sourced: nothing to keep


def test_the_taxobox_class_gives_the_animal_kind() -> None:
    html = '<tr class="taxonrow"><td>Class:</td>\n<td><a href="./Bird">Aves</a></td></tr>'
    assert on_demand.kind_from_taxobox(html) == "bird"
    assert on_demand.kind_from_taxobox("<td>Class:</td><td>Unknownia</td>") is None
    assert on_demand.kind_from_taxobox("<p>no taxobox</p>") is None


async def test_mock_mode_and_other_kinds_fight_on_the_estimate(monkeypatch) -> None:
    calls: list[str] = []

    async def research(*args):
        calls.append("research")
        return researched(MOOSE)

    monkeypatch.setattr(on_demand, "_research", research)
    assert await on_demand.researched_or_estimate(MOOSE, "real_animal") is MOOSE  # mock mode
    go_live(monkeypatch)
    seal = estimate_sheet("navy seal", "armed_unit")
    assert await on_demand.researched_or_estimate(seal, "armed_unit") is seal
    assert calls == []


async def test_a_quick_build_is_used_and_cached_for_the_next_battle(monkeypatch) -> None:
    go_live(monkeypatch)

    async def research(estimate, kind, size_class):
        sheet = researched(estimate)
        connection = connect()
        try:
            apply_migrations(connection)
            save_sheet(connection, sheet)
        finally:
            connection.close()
        return sheet

    monkeypatch.setattr(on_demand, "_research", research)
    first = await on_demand.researched_or_estimate(MOOSE, "real_animal", "large")
    assert first.stats[StatName.MASS].value == 450.0

    async def never(*args):
        raise AssertionError("the cached sheet should be used")

    monkeypatch.setattr(on_demand, "_research", never)
    assert await on_demand.researched_or_estimate(MOOSE, "real_animal", "large") == first


async def test_a_slow_build_leaves_the_battle_on_estimates_and_keeps_running(monkeypatch) -> None:
    go_live(monkeypatch)
    monkeypatch.setattr(on_demand, "ON_DEMAND_RESEARCH_S", 0.05)
    started = asyncio.Event()
    finish = asyncio.Event()
    runs: list[str] = []

    async def research(estimate, kind, size_class):
        runs.append(estimate.fighter_id)
        started.set()
        await finish.wait()
        return researched(estimate)

    monkeypatch.setattr(on_demand, "_research", research)
    assert await on_demand.researched_or_estimate(MOOSE, "real_animal") is MOOSE
    assert await on_demand.researched_or_estimate(MOOSE, "real_animal") is MOOSE
    assert started.is_set() and runs == ["moose"]  # one build in flight, shared
    build = on_demand._BUILDS["moose"]
    finish.set()
    assert (await build).stats[StatName.MASS].value == 450.0  # it finished after the battle


async def test_a_build_that_finds_nothing_is_not_retried_for_a_while(monkeypatch) -> None:
    go_live(monkeypatch)
    runs: list[str] = []

    async def research(estimate, kind, size_class):
        runs.append(estimate.fighter_id)
        return None

    monkeypatch.setattr(on_demand, "_research", research)
    assert await on_demand.researched_or_estimate(MOOSE, "real_animal") is MOOSE
    assert await on_demand.researched_or_estimate(MOOSE, "real_animal") is MOOSE
    assert runs == ["moose"]


async def test_a_failing_build_means_estimates_not_an_error(monkeypatch) -> None:
    go_live(monkeypatch)

    async def research(*args):
        raise RuntimeError("the article fetch broke")

    monkeypatch.setattr(on_demand, "_research", research)
    assert await on_demand.researched_or_estimate(MOOSE, "real_animal") is MOOSE


async def test_the_battle_uses_the_researched_sheet_as_sourced(monkeypatch) -> None:
    from app.research import sheet_store

    go_live(monkeypatch)
    sheet_store.remember_not_a_legend("moose", "real_animal", "mammal", "large")

    async def research(estimate, kind, size_class):
        return researched(estimate)

    monkeypatch.setattr(on_demand, "_research", research)
    sheet, estimated = await stages.lookup_fighter_or_estimate(
        FighterRequest(entity="moose", raw="a moose")
    )
    assert sheet.stats[StatName.MASS].value == 450.0 and not estimated


def test_researched_sheets_are_never_searched_or_offered_as_challengers() -> None:
    connection = connect()
    try:
        apply_migrations(connection)
        save_sheet(connection, researched(MOOSE))
        assert cached_sheet(connection, "moose") is not None
        assert search_fighters(connection, "moose") == []
    finally:
        connection.close()
    assert all(sheet.fighter_id != "moose" for sheet in challenger.cached_sheets())
