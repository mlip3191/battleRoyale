"""#622: a first fight on estimates while research runs says so, and no build gives up silently.

Mike's call on #622: keep the 20 s wait, and when a fighter's research is still running, the
research note says its stats are estimates and that a rematch will use sourced stats. Every way
an on-demand build can end with nothing logs one line saying why (the warthog built nothing and
said nothing).
"""

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from app.config import use_settings
from app.models.stats import StatName
from app.pipeline import orchestrator, stages
from app.pipeline.orchestrator import ESTIMATED_FIGHTER, RESEARCHING_FIGHTER, RESEARCHING_FIGHTERS
from app.research import on_demand
from app.research.estimate_sheet import estimate_sheet
from app.research.sources import SourceError
from tests.conftest import mock_settings
from tests.unit.test_estimate_sheet import battle, matchup, research_stage
from tests.unit.test_on_demand_research import MOOSE, OSTRICH, go_live, quoted_mass, stub_research

LOGGER = on_demand.logger.name


@pytest.fixture(autouse=True)
async def _clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    use_settings(mock_settings(data_dir=tmp_path / "data", sim_runs=20))
    for stage in stages.STAGE_BUDGETS_S:
        monkeypatch.setitem(stages.STAGE_BUDGETS_S, stage, 8.0)
    await on_demand.forget_research()
    yield
    await on_demand.forget_research()


# A build for `fighter_id` that is still running, as if the 20 s wait had run out.
@pytest.fixture
def running_build() -> Iterator[asyncio.Future[None]]:
    loop = asyncio.get_event_loop()
    pending: asyncio.Future[None] = loop.create_future()
    yield pending
    pending.cancel()


# --- the note and what research reports ----------------------------------------------------------


async def test_research_running_is_true_only_while_the_build_is_in_flight(monkeypatch) -> None:
    go_live(monkeypatch)
    monkeypatch.setattr(on_demand, "ON_DEMAND_RESEARCH_S", 0.05)
    finish = asyncio.Event()

    async def research(estimate, kind, size_class, title):
        await finish.wait()
        return None

    monkeypatch.setattr(on_demand, "_research", research)
    assert not on_demand.research_running("moose")
    assert await on_demand.researched_or_estimate(MOOSE, "real_animal") is MOOSE
    assert on_demand.research_running("moose")  # the battle moved on; the build did not
    build = on_demand._BUILDS["moose"]
    finish.set()
    await build
    assert not on_demand.research_running("moose")


async def test_a_fighter_whose_research_is_running_is_listed_apart(running_build) -> None:
    on_demand._BUILDS["wolverine"] = running_build  # type: ignore[assignment]
    found = await stages.research(matchup({"entity": "gray wolf"}, {"entity": "wolverine"}))
    assert found.researching == ["wolverine"]
    assert found.estimated == []  # not also "we have no stat sheet"


async def test_an_estimate_with_no_build_running_keeps_the_old_note() -> None:
    found = await stages.research(matchup({"entity": "gray wolf"}, {"entity": "wolverine"}))
    assert (found.estimated, found.researching) == (["wolverine"], [])


def test_the_note_names_the_fighter_and_promises_a_rematch() -> None:
    found = stages.Research(sheets=[], reference_sheets=[], researching=["moose"])
    note = orchestrator._research_note(found)
    assert note == RESEARCHING_FIGHTER.format(names="'moose'")
    assert note == (
        "Research on 'moose' is still running, so its stats here are estimates. "
        "A rematch will use sourced stats."
    )
    both = stages.Research(sheets=[], reference_sheets=[], researching=["moose", "warthog"])
    assert orchestrator._research_note(both) == RESEARCHING_FIGHTERS.format(
        names="'moose' and 'warthog'"
    )


def test_a_researching_and_an_estimated_fighter_each_get_their_own_sentence() -> None:
    found = stages.Research(
        sheets=[], reference_sheets=[], estimated=["wolverine"], researching=["moose"]
    )
    assert orchestrator._research_note(found) == " ".join(
        (
            RESEARCHING_FIGHTER.format(names="'moose'"),
            ESTIMATED_FIGHTER.format(names="'wolverine'"),
        )
    )


async def test_the_battle_says_research_is_still_running(running_build) -> None:
    on_demand._BUILDS["wolverine"] = running_build  # type: ignore[assignment]
    record = await battle(matchup({"entity": "gray wolf"}, {"entity": "wolverine"}))
    assert record.status == "done"
    stage = research_stage(record)
    assert stage.status == "fallback"
    assert stage.detail == RESEARCHING_FIGHTER.format(names="'wolverine'")


# --- a build that ends with nothing says why -----------------------------------------------------


def reasons(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LOGGER]


async def test_no_article_is_logged(monkeypatch, caplog) -> None:
    stub_research(monkeypatch, article=None)
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert await on_demand._research(OSTRICH, "real_animal", "medium", "ostrich") is None
    assert reasons(caplog) == ["On-demand research for ostrich gave up: no article for 'ostrich'."]


async def test_an_unreachable_wikipedia_is_not_called_a_missing_article(
    monkeypatch, caplog
) -> None:
    stub_research(monkeypatch)

    async def unreachable(client, title):
        raise SourceError("Wikipedia did not answer", status=503)

    monkeypatch.setattr(on_demand, "fetch_article", unreachable)
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert await on_demand._research(OSTRICH, "real_animal", "medium", "ostrich") is None
    assert reasons(caplog) == [
        "On-demand research for ostrich gave up: "
        "couldn't fetch the article for 'ostrich': Wikipedia did not answer"
    ]


async def test_an_article_with_no_animal_taxobox_is_logged(monkeypatch, caplog) -> None:
    stub_research(monkeypatch, article="<p>Ostrich may refer to: a band</p>")
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert await on_demand._research(OSTRICH, "real_animal", "medium", "ostrich") is None
    assert reasons(caplog) == [
        "On-demand research for ostrich gave up: the article has no animal taxobox."
    ]


async def test_nothing_sourced_is_logged(monkeypatch, caplog) -> None:
    stub_research(monkeypatch, mass=None)
    caplog.set_level(logging.INFO, logger=LOGGER)
    sheet = await on_demand._research(OSTRICH, "real_animal", "medium", "ostrich")
    assert sheet is not None and all(v.is_estimate for v in sheet.stats.values())
    assert reasons(caplog) == [
        "On-demand research for ostrich gave up: no stat in the article could be sourced."
    ]


async def test_no_web_client_is_logged(monkeypatch, caplog) -> None:
    monkeypatch.setattr(on_demand, "legend_client", lambda: None)
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert await on_demand._research(OSTRICH, "real_animal", "medium", "ostrich") is None
    assert reasons(caplog) == ["On-demand research for ostrich gave up: no web client."]


async def test_a_build_that_times_out_says_so(monkeypatch, caplog) -> None:
    monkeypatch.setattr(on_demand, "BUILD_LIMIT_S", 0.05)

    async def research(*args):
        await asyncio.sleep(5)

    monkeypatch.setattr(on_demand, "_research", research)
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert await on_demand._build(MOOSE, "real_animal", "large", "moose") is None
    assert reasons(caplog) == ["On-demand research for moose gave up: timed out after 0.05 s."]


async def test_a_timeout_inside_the_build_keeps_its_own_message(monkeypatch, caplog) -> None:
    async def research(*args):
        raise TimeoutError("the chat model took too long")

    monkeypatch.setattr(on_demand, "_research", research)
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert await on_demand._build(MOOSE, "real_animal", "large", "moose") is None
    assert reasons(caplog) == [
        "On-demand research for moose gave up: TimeoutError: the chat model took too long"
    ]


async def test_a_build_that_breaks_names_the_error(monkeypatch, caplog) -> None:
    async def research(*args):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(on_demand, "_research", research)
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert await on_demand._build(MOOSE, "real_animal", "large", "moose") is None
    assert reasons(caplog) == ["On-demand research for moose gave up: ConnectError: no route"]


async def test_a_build_that_sources_a_stat_logs_no_give_up(monkeypatch, caplog) -> None:
    stub_research(monkeypatch, mass=120.0)
    caplog.set_level(logging.INFO, logger=LOGGER)
    sheet = await on_demand._research(OSTRICH, "real_animal", "medium", "ostrich")
    assert sheet is not None and sheet.stats[StatName.MASS] == quoted_mass(120.0)
    assert not [line for line in reasons(caplog) if "gave up" in line]


def test_the_shared_estimate_helper_still_builds_a_moose() -> None:
    # Guards the fixtures above: the moose estimate is the large mammal (#517).
    assert MOOSE == estimate_sheet("moose", "real_animal", category="mammal", size_class="large")
