"""The replay-log fixtures follow the same rules as the real engine's logs.

The UI builds the replay scene against these fixtures when the backend is not running, so a
fixture that breaks the engine's rules makes the scene behave differently offline. The rules are
the ones in docs/simulation-api.md (the table of event types and "What the replay log contains").
"""

import json
import re

from app.config import REPO_ROOT
from app.models.simulation import EventType, FightEvent, SimulationResult
from app.simulation.engine import run
from tests.property.sim_helpers import load_sheet, matchup_of

CONTRACTS = REPO_ROOT / "backend" / "tests" / "fixtures" / "contracts"


def check_log_rules(log: list[FightEvent], outcome: str) -> None:
    assert log, "an empty replay log"
    assert EventType.ATTACK not in {e.type for e in log}, "the engine never emits ATTACK"
    times = [e.t for e in log]
    assert times == sorted(times) and 0 <= times[0] and times[-1] <= 600, "events in time order"
    assert len(log) <= 300

    # One APPROACH per side, at t = 0, and the END event is last.
    approaches = [e for e in log if e.type == EventType.APPROACH]
    assert sorted(e.side for e in approaches) == [0, 1] and all(e.t == 0 for e in approaches)
    assert log[-1].type == EventType.END
    winner = {"win_0": 0, "win_1": 1}.get(outcome, 0)  # END side is 0 for a draw or no contest
    assert log[-1].side == winner, "END side is the winner"

    fallen: set[tuple[int, int]] = set()
    for event in log:
        assert event.text_hint and not re.search(r"\d", event.text_hint), "neutral hint, no number"
        if event.type == EventType.HIT:
            assert event.damage is not None and event.damage >= 0
        if event.type in (EventType.MISS, EventType.KO, EventType.APPROACH, EventType.END):
            assert event.damage is None
        if event.type == EventType.KO:
            # `side` is the side that went down, `actor` the fallen fighter, and there is no target.
            assert event.target is None
            if event.actor is not None:
                assert (event.side, event.actor) not in fallen, "a fighter falls once"
                fallen.add((event.side, event.actor))
        if event.actor is None and event.type != EventType.APPROACH:
            assert event.group_size >= 1  # a group event says how many acted or fell


def fixture_logs() -> list[tuple[str, list[FightEvent], str]]:
    standalone = SimulationResult.model_validate(
        json.loads((CONTRACTS / "simulation-result.json").read_text("utf-8"))
    )
    record = json.loads((CONTRACTS / "battle-record-done.json").read_text("utf-8"))
    embedded = SimulationResult.model_validate(record["result"])
    return [
        ("simulation-result.json", standalone.representative_log, standalone.outcome),
        ("battle-record-done.json", embedded.representative_log, embedded.outcome),
    ]


def test_the_fixture_logs_follow_the_engine_rules():
    for name, log, outcome in fixture_logs():
        try:
            check_log_rules(log, outcome)
        except AssertionError as error:
            raise AssertionError(f"{name}: {error}") from error


def test_the_two_fixture_logs_are_the_same_fight():
    (_, first, _), (_, second, _) = fixture_logs()
    assert first == second


def test_the_real_engine_follows_the_same_rules():
    bear, wolf = load_sheet("stat-sheet.json"), load_sheet("stat-sheet-gray-wolf.json")
    result = run(matchup_of(1, 6), [bear, wolf], runs=60)
    check_log_rules(result.representative_log, result.outcome)


def test_narration_lines_point_at_real_events():
    record = json.loads((CONTRACTS / "battle-record-done.json").read_text("utf-8"))
    log = SimulationResult.model_validate(record["result"]).representative_log
    for script in record["scripts"]:
        for line in script["lines"]:
            at = line["at_event"]
            assert at is None or 0 <= at < len(log), f"line points at event {at}"
    # The play-by-play lines were written for these moments; keep them true.
    play = next(s for s in record["scripts"] if s["kind"] == "play_by_play")["lines"]
    kinds = {line["at_event"]: log[line["at_event"]].type for line in play}
    assert kinds[0] == EventType.APPROACH
    assert kinds[5] == EventType.KO and log[5].side == 1  # "one wolf is out of the game"
    assert kinds[10] == EventType.KO and log[10].side == 0  # "the bear goes down"
