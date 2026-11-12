"""A05 part 3: the next-challenger stage (Structured Decisions shortlist, then code tests) (#36)."""

import asyncio
import time
from collections.abc import Callable
from typing import Any

import pytest

from app.config import Settings, use_settings
from app.models.matchup import Matchup
from app.models.simulation import SimulationResult
from app.models.stats import StatSheet
from app.models.terrain import Terrain
from app.pipeline import challenger, stages
from app.pipeline.orchestrator import FALLBACK_DETAILS, FALLBACK_WITH_VALUE, run_battle
from app.pipeline.store import BattleStore
from app.providers.base import DecisionAnswer, DecisionQuestion
from app.research.seed_fighters import load_seed_fighters
from app.simulation import fair

SIM_RUNS = 20
MATCHUP_IDS = {"grizzly-bear", "gray-wolf"}
STAGE_BUDGET_S = 10.0  # ARCHITECTURE §4, stage 8


@pytest.fixture(autouse=True)
def _mock_mode() -> None:
    use_settings(Settings(_env_file=None, provider_mode="mock", sim_runs=SIM_RUNS))


def fight(first: str = "grizzly bear", second: str = "gray wolf") -> Matchup:
    fighters = [{"entity": name, "raw": name} for name in (first, second)]
    return Matchup.model_validate(
        {"fighters": fighters, "raw_text": f"{first} vs {second}", "terrain": "open_field"}
    )


@pytest.fixture
async def sheets_and_result() -> tuple[list[StatSheet], SimulationResult]:
    found = await stages.research(fight())
    return found.sheets, await stages.simulate(fight(), found)


class FakeDecider:
    """A StructuredLLM that records each call and answers with `reply(options)` or raises."""

    def __init__(
        self,
        reply: Callable[[list[str]], dict[str, float]] | None = None,
        error: BaseException | None = None,
        delay: float = 0.0,
    ) -> None:
        self.reply, self.error, self.delay = reply, error, delay
        self.calls: list[tuple[dict[str, str], dict[str, DecisionQuestion], str]] = []

    async def decide(
        self, state: dict[str, str], questions: dict[str, DecisionQuestion], *, prompt_name: str
    ) -> dict[str, DecisionAnswer]:
        self.calls.append((state, questions, prompt_name))
        await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        options = list(questions[challenger.QUESTION]["criteria"])
        odds = self.reply(options) if self.reply else {o: 1 / len(options) for o in options}
        return {
            challenger.QUESTION: {"choice": options[0], "probabilities": odds, "confidence": 0.5}
        }


# Record which sheets test_challengers is asked to duel, then run it for real.
def spy_on_tests(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    tested: list[list[str]] = []
    real = fair.test_challengers

    def spy(winner: StatSheet, candidates: list[StatSheet], terrain: Terrain) -> Any:
        tested.append([c.fighter_id for c in candidates])
        return real(winner, candidates, terrain)

    monkeypatch.setattr(fair, "test_challengers", spy)
    return tested


# Seed fighters that have a sheet (some seed-list rows don't have one yet).
def seed_ids() -> set[str]:
    with_sheets = {s.fighter_id for s in challenger.seed_sheets()}
    assert with_sheets <= {f.id for f in load_seed_fighters()}
    return with_sheets


def test_candidates_are_seed_fighters_without_the_matchup() -> None:
    found = challenger.load_candidates(MATCHUP_IDS)
    ids = [s.fighter_id for s in found.all]
    assert ids and set(ids) <= seed_ids() and not MATCHUP_IDS & set(ids)
    assert ids == sorted(ids) and len(ids) <= challenger.MAX_SEED
    assert found.cached == []  # no cache until A05 part 4


def test_cached_fighters_join_the_candidates_capped_and_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    horse = challenger.seed_sheets()[0]
    fresh = [horse.model_copy(update={"fighter_id": f"cached-{n:02d}"}) for n in range(25)]
    monkeypatch.setattr(challenger, "cached_sheets", lambda: [horse, *fresh])
    found = challenger.load_candidates(MATCHUP_IDS)
    assert [s.fighter_id for s in found.cached] == [f"cached-{n:02d}" for n in range(19)]


async def test_options_are_only_seed_or_cached_and_never_the_matchup(
    sheets_and_result: tuple[list[StatSheet], SimulationResult],
) -> None:
    sheets, result = sheets_and_result
    fake = FakeDecider()
    pick, fallback = await challenger.suggest(sheets, result, Terrain.OPEN_FIELD, llm=fake)
    assert pick is not None and not fallback
    ((state, questions, prompt_name),) = fake.calls
    options = set(questions[challenger.QUESTION]["criteria"])
    assert options and options <= seed_ids() and not MATCHUP_IDS & options
    assert prompt_name == "challenger" and state["terrain"] == "open_field"
    assert {state["winner"], state["defeated"]} == {s.display_name for s in sheets}
    assert "DATA" in questions[challenger.QUESTION]["instructions"]


async def test_the_mock_pick_is_deterministic_and_tests_the_first_five_by_id(
    sheets_and_result: tuple[list[StatSheet], SimulationResult], monkeypatch: pytest.MonkeyPatch
) -> None:
    sheets, result = sheets_and_result
    tested = spy_on_tests(monkeypatch)
    first = await challenger.suggest(sheets, result, Terrain.OPEN_FIELD)
    second = await challenger.suggest(sheets, result, Terrain.OPEN_FIELD)
    assert first == second and first[0] is not None and first[1] is False
    expected = sorted(seed_ids() - MATCHUP_IDS)[: challenger.SHORTLIST]
    assert tested == [expected, expected]


async def test_unknown_option_ids_are_ignored(
    sheets_and_result: tuple[list[StatSheet], SimulationResult], monkeypatch: pytest.MonkeyPatch
) -> None:
    sheets, result = sheets_and_result
    tested = spy_on_tests(monkeypatch)

    def odds(options: list[str]) -> dict[str, float]:
        return {"unicorn": 0.9, "gray-wolf": 0.05, options[-1]: 0.05}

    pick, fallback = await challenger.suggest(sheets, result, Terrain.OPEN_FIELD, FakeDecider(odds))
    assert tested == [[sorted(seed_ids() - MATCHUP_IDS)[-1]]] and not fallback
    assert pick is not None


async def test_only_unknown_ids_falls_back_to_seed_tests(
    sheets_and_result: tuple[list[StatSheet], SimulationResult],
) -> None:
    sheets, result = sheets_and_result
    fake = FakeDecider(lambda _: {"unicorn": 1.0})
    pick, fallback = await challenger.suggest(sheets, result, Terrain.OPEN_FIELD, fake)
    assert pick is not None and fallback


async def test_model_picks_that_all_fail_the_tests_retry_once_with_the_seed(
    sheets_and_result: tuple[list[StatSheet], SimulationResult], monkeypatch: pytest.MonkeyPatch
) -> None:
    sheets, result = sheets_and_result
    seed = [s.fighter_id for s in challenger.load_candidates(MATCHUP_IDS).seed]
    last, first_five = seed[-1], seed[: challenger.SHORTLIST]
    tested: list[list[str]] = []
    real = fair.test_challengers

    # The model's own pick fails the tests; the seed retry runs for real.
    def spy(winner: StatSheet, candidates: list[StatSheet], terrain: Terrain) -> Any:
        tested.append([c.fighter_id for c in candidates])
        return [] if len(tested) == 1 else real(winner, candidates, terrain)

    monkeypatch.setattr(fair, "test_challengers", spy)
    fake = FakeDecider(lambda _: {last: 1.0})
    pick, fallback = await challenger.suggest(sheets, result, Terrain.OPEN_FIELD, fake)
    assert tested == [[last], [i for i in first_five if i != last]]
    assert pick is not None and fallback


def test_names_sent_to_the_model_are_one_clipped_line() -> None:
    bear, wolf = challenger.seed_sheets()[:2]
    messy = bear.model_copy(update={"display_name": "Big\nBear\x00\t\r  " + "x" * 200})
    state = challenger.build_state(messy, wolf, Terrain.OPEN_FIELD)
    assert state["winner"].startswith("Big Bear x")
    assert len(state["winner"]) == challenger.DATA_LIMIT
    assert all(ch.isprintable() for ch in state["winner"]) and "  " not in state["winner"]
    criteria = challenger.build_questions([messy])[challenger.QUESTION]["criteria"]
    assert all(ch.isprintable() for ch in criteria[messy.fighter_id])


def test_non_finite_odds_are_skipped_when_ranking() -> None:
    a, b, c = challenger.seed_sheets()[:3]
    odds = {a.fighter_id: float("nan"), b.fighter_id: float("inf"), c.fighter_id: 0.1}
    answer: DecisionAnswer = {"choice": a.fighter_id, "probabilities": odds, "confidence": 0.5}
    assert challenger.shortlist(answer, [a, b, c]) == [c]


@pytest.mark.parametrize(
    "fake",
    [FakeDecider(error=RuntimeError("down")), FakeDecider(delay=1.0)],
    ids=["raises", "too-slow"],
)
async def test_model_trouble_falls_back_to_a_seed_tested_challenger(
    sheets_and_result: tuple[list[StatSheet], SimulationResult],
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeDecider,
) -> None:
    monkeypatch.setattr(challenger, "DECIDE_BUDGET_S", 0.05)
    sheets, result = sheets_and_result
    winner = sheets[challenger.winner_side(result, sheets)]
    seed = challenger.load_candidates(MATCHUP_IDS).seed[: challenger.SHORTLIST]
    pick, fallback = await challenger.suggest(sheets, result, Terrain.OPEN_FIELD, fake)
    assert fallback and pick == fair.test_challengers(winner, seed, Terrain.OPEN_FIELD)[0]


async def test_nobody_to_offer_or_nothing_tested_means_no_challenger(
    sheets_and_result: tuple[list[StatSheet], SimulationResult], monkeypatch: pytest.MonkeyPatch
) -> None:
    sheets, result = sheets_and_result
    monkeypatch.setattr(fair, "test_challengers", lambda *_: [])
    assert await challenger.suggest(sheets, result, Terrain.OPEN_FIELD) == (None, True)
    monkeypatch.setattr(challenger, "seed_sheets", lambda: [])
    fake = FakeDecider()
    assert await challenger.suggest(sheets, result, Terrain.OPEN_FIELD, fake) == (None, True)
    assert fake.calls == []


@pytest.mark.parametrize(
    ("outcome", "win_prob", "side"),
    [
        ("win_1", (0.4, 0.5), 1),
        ("draw", (0.2, 0.3), 1),
        ("draw", (0.3, 0.2), 0),
        ("draw", (0.25, 0.25), 1),  # tie: gray-wolf (side 1) sorts before grizzly-bear
        ("no_contest", (0.0, 0.0), 1),
    ],
)
def test_the_winner_side_handles_draws_by_odds_then_fighter_id(
    sheets_and_result: tuple[list[StatSheet], SimulationResult],
    outcome: str,
    win_prob: tuple[float, float],
    side: int,
) -> None:
    sheets, result = sheets_and_result
    changed = result.model_copy(update={"outcome": outcome, "win_prob": win_prob})
    assert challenger.winner_side(changed, sheets) == side


async def test_a_draw_offers_neither_side_and_names_the_likelier_winner(
    sheets_and_result: tuple[list[StatSheet], SimulationResult],
) -> None:
    sheets, result = sheets_and_result
    draw = result.model_copy(update={"outcome": "draw", "win_prob": (0.4, 0.2)})
    fake = FakeDecider()
    await challenger.suggest(sheets, draw, Terrain.OPEN_FIELD, fake)
    ((state, questions, _),) = fake.calls
    assert state["winner"] == sheets[0].display_name
    assert not MATCHUP_IDS & set(questions[challenger.QUESTION]["criteria"])


async def test_the_stage_finishes_well_under_its_budget_on_mocks() -> None:
    found = await stages.research(fight())
    result = await stages.simulate(fight(), found)
    began = time.perf_counter()
    out = await stages.challenger(fight(), found, result)
    assert time.perf_counter() - began < STAGE_BUDGET_S / 2
    assert out.value is not None and not out.fallback and not out.stub


async def test_a_battle_saves_the_challenger_and_marks_done() -> None:
    store = BattleStore()
    record = await store.create(fight())
    await asyncio.wait_for(run_battle(record.battle_id, store), 30)
    final = await store.get(record.battle_id)
    assert final is not None and final.challenger is not None
    stage = next(s for s in final.stages if s.stage == "challenger")
    assert (stage.status, stage.detail) == ("done", None)


@pytest.mark.parametrize("found_one", [True, False])
async def test_a_battle_whose_model_fails_ends_the_stage_fallback(
    monkeypatch: pytest.MonkeyPatch, found_one: bool
) -> None:
    monkeypatch.setattr(challenger, "get_provider", lambda _: FakeDecider(error=OSError()))
    if not found_one:
        monkeypatch.setattr(fair, "test_challengers", lambda *_: [])
    store = BattleStore()
    record = await store.create(fight())
    await asyncio.wait_for(run_battle(record.battle_id, store), 30)
    final = await store.get(record.battle_id)
    assert final is not None and final.status == "done"
    stage = next(s for s in final.stages if s.stage == "challenger")
    note = FALLBACK_WITH_VALUE["challenger"] if found_one else FALLBACK_DETAILS["challenger"]
    assert (stage.status, stage.detail) == ("fallback", note)
    assert (final.challenger is not None) == found_one
