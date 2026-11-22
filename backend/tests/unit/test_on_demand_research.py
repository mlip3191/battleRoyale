"""#518: research for an unlisted real animal at battle time (live mode only).

The article fetch, ingest and extraction are stood in for: these tests check what code does with
their results (merging only quoted stats, the time limit, the cache, search and the challenger,
and _research's own steps: the taxobox kind, Wikidata facts, ingest and saving).
"""

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.config import use_settings
from app.db.connection import connect
from app.db.migrate import apply_migrations
from app.models.matchup import FighterRequest
from app.models.stats import Source, StatName, StatSheet, StatValue
from app.pipeline import challenger, stages
from app.research import on_demand
from app.research.estimate_sheet import estimate_sheet
from app.research.sheet_store import LEGEND_BUDGET_S, cached_sheet, save_sheet, search_fighters
from app.research.sources import SourceError
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


# A quoted value, as extraction gives one.
def quoted(value: float, unit: str, words: str) -> StatValue:
    return StatValue(
        value=value,
        unit=unit,
        source=Source(
            title="Moose",
            url="https://en.wikipedia.org/wiki/Moose",
            quote=f"{words} {value:g} {unit}",
            retrieved_at="2026-11-21T00:00:00Z",
            license="CC BY-SA 4.0",
        ),
        confidence="medium",
        is_estimate=False,
        method="extracted",
    )


# A quoted mass, as extraction gives one.
def quoted_mass(value: float) -> StatValue:
    return quoted(value, "kg", "Bulls weigh")


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


def test_a_sourced_size_sets_the_reach_derived_from_it() -> None:  # #535
    size = quoted(2.59, "m", "Bulls measure")
    built = MOOSE.model_copy(update={"stats": {**MOOSE.stats, StatName.SIZE: size}})
    sheet = on_demand.merged(MOOSE, built)
    assert sheet is not None and sheet.stats[StatName.SIZE] == size
    reach = sheet.stats[StatName.REACH]
    assert reach.method == "derived" and not reach.is_estimate
    assert reach.value == pytest.approx(0.25 * 2.59)
    assert (reach.low, reach.high) == (
        pytest.approx(0.25 * size.low) if size.low is not None else reach.value,
        pytest.approx(0.25 * size.high) if size.high is not None else reach.value,
    )
    # With only the mass sourced, the reach's input is still an estimate, so it stays one.
    assert researched(MOOSE).stats[StatName.REACH] == MOOSE.stats[StatName.REACH]


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

    async def research(estimate, kind, size_class, title):
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

    async def research(estimate, kind, size_class, title):
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

    async def research(estimate, kind, size_class, title):
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

    async def research(estimate, kind, size_class, title):
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


# --- the research stage's deadline (#518 QA) ------------------------------------------------


def test_the_legend_lookup_leaves_time_for_research_in_the_stage() -> None:
    assert LEGEND_BUDGET_S + stages.RESEARCH_MARGIN_S < stages.STAGE_BUDGETS_S["research"]


async def test_the_wait_never_runs_past_the_deadline(monkeypatch) -> None:
    go_live(monkeypatch)
    finish = asyncio.Event()

    async def research(estimate, kind, size_class, title):
        await finish.wait()
        return researched(estimate)

    monkeypatch.setattr(on_demand, "_research", research)
    started = time.monotonic()
    late = await on_demand.researched_or_estimate(MOOSE, "real_animal", deadline=started + 0.05)
    assert late is MOOSE and time.monotonic() - started < 1.0  # not the 20 s wait
    past = await on_demand.researched_or_estimate(MOOSE, "real_animal", deadline=started - 1.0)
    assert past is MOOSE  # no time left: estimates now, and the one build keeps running
    finish.set()
    assert (await on_demand._BUILDS["moose"]).stats[StatName.MASS].value == 450.0


async def test_the_battle_researches_within_the_stage_and_never_a_variant(monkeypatch) -> None:
    from app.research import sheet_store

    calls: list[dict] = []

    async def research(estimate, kind, size_class, **options):
        calls.append(options)
        return estimate

    monkeypatch.setattr(stages, "researched_or_estimate", research)
    sheet_store.remember_not_a_legend("moose", "real_animal", "mammal", "large")
    before = time.monotonic()
    await stages.lookup_fighter_or_estimate(FighterRequest(entity="moose", raw="a moose"))
    latest = time.monotonic() + stages.STAGE_BUDGETS_S["research"] - stages.RESEARCH_MARGIN_S
    assert calls[0]["title"] == "moose" and before < calls[0]["deadline"] <= latest
    baby = FighterRequest(entity="moose", variant="baby", raw="a baby moose")
    _, estimated = await stages.lookup_fighter_or_estimate(baby)
    assert estimated and len(calls) == 1  # an adult's article would mislead


async def test_an_adult_is_researched_like_the_plain_animal(monkeypatch) -> None:  # #535
    from app.research import sheet_store

    titles: list[str] = []

    async def research(estimate, kind, size_class, **options):
        titles.append(options["title"])
        return estimate

    monkeypatch.setattr(stages, "researched_or_estimate", research)
    sheet_store.remember_not_a_legend("moose", "real_animal", "mammal", "large")
    adult = FighterRequest(entity="moose", variant="adult", raw="an adult moose")
    await stages.lookup_fighter_or_estimate(adult)
    assert titles == ["moose"]  # the article describes adults
    for variant in ("baby", "adult male", "young"):  # still a variant the article doesn't fit
        request = FighterRequest(entity="moose", variant=variant, raw=f"a {variant} moose")
        _, estimated = await stages.lookup_fighter_or_estimate(request)
        assert estimated
    assert titles == ["moose"]


async def test_a_better_kind_with_nothing_sourced_is_used_once_not_rebuilt(monkeypatch) -> None:
    go_live(monkeypatch)
    runs: list[str] = []
    bird = estimate_sheet("moose", "real_animal", category="bird", size_class="large")

    async def research(estimate, kind, size_class, title):
        runs.append(estimate.fighter_id)
        return bird  # all estimates, only the kind is better

    monkeypatch.setattr(on_demand, "_research", research)
    assert await on_demand.researched_or_estimate(MOOSE, "real_animal") is bird
    assert await on_demand.researched_or_estimate(MOOSE, "real_animal") is MOOSE
    assert runs == ["moose"]


# --- _research's own steps, with the network and the models stood in for ----------------------

AVES = '<table class="infobox"><tr><td>Class:</td><td><a href="./Bird">Aves</a></td></tr></table>'
OSTRICH = estimate_sheet("ostrich", "real_animal", category="mammal", size_class="medium")


# Stand in for every outside call _research makes; returns the record of what it did.
def stub_research(
    monkeypatch,
    *,
    article: str | None = AVES,
    wikidata_fails: bool = False,
    mass: float | None = 100.0,
) -> dict:
    done: dict = {"facts": [], "ingested": [], "profiles": [], "fetches": 0, "articles": []}
    monkeypatch.setattr(
        on_demand,
        "legend_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))),
    )

    async def fetch_article(client, title):
        done["fetches"] += 1
        return None if article is None else SimpleNamespace(body=article.encode())

    async def fetch_wikidata(client, title):
        if wikidata_fails:
            raise SourceError("Wikidata is down", status=503)
        return SimpleNamespace(body=b"{}", retrieved_at=datetime.now(UTC), license="CC0")

    async def ingest(connection, client, parser, embedder, fighter_id, title, *, article=None):
        done["ingested"].append(title)
        done["articles"].append(article)
        return True

    async def build(connection, providers, profile):
        done["profiles"].append(profile)
        sheet = estimate_sheet(profile.display_name, "real_animal", category=profile.category)
        if mass is None:
            return sheet
        return sheet.model_copy(update={"stats": {**sheet.stats, StatName.MASS: quoted_mass(mass)}})

    monkeypatch.setattr(on_demand, "fetch_article", fetch_article)
    monkeypatch.setattr(on_demand, "fetch_wikidata", fetch_wikidata)
    monkeypatch.setattr(on_demand, "wikidata_facts", lambda entity: ["a fact"])
    monkeypatch.setattr(on_demand, "store_facts", lambda *a: done["facts"].append(a[1]))
    monkeypatch.setattr(on_demand, "ingest_on_demand", ingest)
    monkeypatch.setattr(on_demand, "build_sheet_with_evidence", build)
    monkeypatch.setattr(on_demand, "get_provider", lambda name: None)
    return done


def saved(fighter_id: str) -> StatSheet | None:
    connection = connect()
    try:
        apply_migrations(connection)
        return cached_sheet(connection, fighter_id)
    finally:
        connection.close()


async def test_a_bird_article_makes_a_bird_of_the_same_size_and_saves_it(monkeypatch) -> None:
    done = stub_research(monkeypatch)
    sheet = await on_demand._research(OSTRICH, "real_animal", "medium", "ostrich")
    assert sheet is not None and (sheet.category, sheet.weapons) == ("bird", ["beak"])
    assert done["profiles"][0].category == "bird" and done["ingested"] == ["ostrich"]
    assert done["facts"] == ["ostrich"]
    medium_bird = estimate_sheet("ostrich", "real_animal", category="bird", size_class="medium")
    assert sheet.stats[StatName.MASS].value == 100.0  # sourced
    others = {s: v for s, v in sheet.stats.items() if s != StatName.MASS}
    assert others == {s: v for s, v in medium_bird.stats.items() if s != StatName.MASS}
    assert saved("ostrich") == sheet


async def test_the_article_is_downloaded_once_per_build(monkeypatch) -> None:  # #535
    done = stub_research(monkeypatch)
    await on_demand._research(OSTRICH, "real_animal", "medium", "ostrich")
    assert done["fetches"] == 1  # the taxobox and the stored passages share one download
    assert done["articles"][0] is not None and done["articles"][0].body == AVES.encode()


async def test_nothing_sourced_saves_nothing(monkeypatch) -> None:
    stub_research(monkeypatch, mass=None)
    sheet = await on_demand._research(OSTRICH, "real_animal", "medium", "ostrich")
    assert sheet is not None and sheet.category == "bird"  # the better kind, for this battle
    assert all(value.is_estimate for value in sheet.stats.values()) and saved("ostrich") is None


async def test_an_article_without_an_animal_taxobox_gives_nothing(monkeypatch) -> None:
    done = stub_research(monkeypatch, article="<p>Ostrich may refer to: a band, a film</p>")
    assert await on_demand._research(OSTRICH, "real_animal", "medium", "ostrich") is None
    assert (done["facts"], done["ingested"], done["profiles"]) == ([], [], [])
    assert saved("ostrich") is None
    stub_research(monkeypatch, article=None)
    assert await on_demand._research(OSTRICH, "real_animal", "medium", "ostrich") is None


async def test_a_wikidata_failure_still_goes_on_to_the_article(monkeypatch) -> None:
    done = stub_research(monkeypatch, wikidata_fails=True)
    sheet = await on_demand._research(OSTRICH, "real_animal", "medium", "ostrich")
    assert sheet is not None and sheet.stats[StatName.MASS].value == 100.0
    assert done["facts"] == [] and done["ingested"] == ["ostrich"]


async def test_a_flier_stays_a_flier_when_its_article_changes_its_kind(monkeypatch) -> None:  # #542
    stub_research(monkeypatch)
    hawk = estimate_sheet("hawk", "real_animal", category="mammal", size_class="small", flies=True)
    assert hawk.habitat == "air"
    sheet = await on_demand._research(hawk, "real_animal", "small", "hawk")
    assert sheet is not None and sheet.category == "bird" and sheet.habitat == "air"
    walker = estimate_sheet("ostrich", "real_animal", category="mammal", flies=False)
    grounded = await on_demand._research(walker, "real_animal", None, "ostrich")
    assert grounded is not None and grounded.habitat == "land"
