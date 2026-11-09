"""docs/simulation-api.md: the guide's examples must run, and what it says must be true."""

import re

import pytest

from app.config import REPO_ROOT
from app.models.simulation import EventType
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import run
from tests.property.sim_helpers import (
    ant,
    duck,
    horse,
    lion,
    load_sheet,
    make_dragon,
    make_sheet,
    matchup_of,
)

GUIDE = REPO_ROOT / "docs" / "simulation-api.md"


def guide_text() -> str:
    return GUIDE.read_text(encoding="utf-8")


def python_blocks() -> list[str]:
    return re.findall(r"```python\n(.*?)```", guide_text(), flags=re.S)


def test_the_complete_example_runs(monkeypatch, capsys):
    monkeypatch.chdir(REPO_ROOT)  # the example loads fixtures by repo-relative path
    example = next(block for block in python_blocks() if "stat_sheets = [bear, wolf]" in block)
    exec(compile(example, "docs/simulation-api.md", "exec"), {})
    out = capsys.readouterr().out
    assert "Grizzly bear - adult male" in out
    assert "A fair fight needs" in out or "No fair fight" in out


def test_the_size_reference_snippet_matches_how_run_really_works():
    snippet = next(block for block in python_blocks() if "reference_sheets=[horse, None]" in block)
    assert "run(matchup, [duck, lion]" in snippet
    matchup = matchup_of(1, 1, ref_0="horse")
    result = run(
        matchup, [duck(), lion()], runs=50, reference_sheets=[horse(), None], explain=False
    )
    hints = [e.text_hint for e in result.representative_log if e.type == EventType.APPROACH]
    assert any(hint.endswith("scaled to horse size") for hint in hints)
    with pytest.raises(ValueError, match="size_reference"):
        run(matchup, [duck(), lion()], runs=5)


def test_every_function_the_guide_names_exists_and_is_shown_being_called():
    from app.simulation import engine, fair, summary

    text = guide_text()
    for name, module in (
        ("run", engine),
        ("fair_fight", fair),
        ("test_challengers", fair),
        ("summary", summary),
        ("scale_factors", engine),
    ):
        assert callable(getattr(module, name))
        assert re.search(rf"\b{name}\(", text), f"the guide never shows {name}( being called"


def test_the_guide_states_the_engine_version_its_timings_were_taken_at():
    assert f"ENGINE_VERSION {c.ENGINE_VERSION}" in guide_text(), (
        "re-check the timings in the guide and update the version it names"
    )


def test_the_guide_warns_that_unexplained_results_have_a_placeholder_factor():
    text = guide_text()
    assert "Deciding factor not computed." in text and "Never show" in text


# --- The replay-log vocabulary and event shapes --------------------------------------------


def replay_section() -> str:
    text = guide_text()
    return text.split("## What the replay log contains")[1].split("## Speed and good habits")[0]


def documented_phrases_and_words() -> tuple[set[str], set[str], set[str]]:
    section = replay_section()
    phrases = set(re.findall(r'"([^"]+)"', section))
    types = set(re.findall(r"^\| `([a-z]+)`", section, flags=re.M))
    line = next(row for row in section.splitlines() if row.startswith("Weapon words:"))
    listed = line.removeprefix("Weapon words:").split(".")[0].split(",")
    words = {item.strip().split(" (")[0] for item in listed}
    return phrases, words, types


def is_described(hint: str, phrases: set[str], words: set[str]) -> bool:
    if hint in phrases or re.fullmatch(r"closes in, scaled to .+ size", hint):
        return True
    single = re.fullmatch(r"(.+) (?:lands|misses)", hint)
    swarm = re.fullmatch(r"(.+)s land", hint)  # a swarm hint uses the plural: "bites land"
    return any(m and m.group(1) in words for m in (single, swarm))


def scenarios():
    """(label, matchup, sheets, reference sheets) for the kinds of fight the guide describes."""
    wolf, bear = load_sheet("stat-sheet-gray-wolf.json"), load_sheet("stat-sheet.json")
    cactus = make_sheet(
        "cactus", body="inert", weapons=["spines"], mass_kg=100, size_m=1.5, top_speed_mps=0,
        attack_force_n=300, attacks_per_s=0.0, armor_0_1=0.3,
    )  # fmt: skip
    boulder = make_sheet(
        "boulder", body="inert", weapons=["none"], mass_kg=1_000_000, attack_force_n=0,
        attacks_per_s=0, top_speed_mps=0,
    )  # fmt: skip
    tank = make_sheet(
        "tank", body="machine", weapons=["ramming"], mass_kg=3, endurance_s=20,
        attack_force_n=0, spread=0.0,
    )  # fmt: skip
    drones = make_sheet(
        "drones", body="machine", mass_kg=2, endurance_s=2, attack_force_n=1, spread=0.0
    )
    fast = make_sheet("fast", aggression_0_1=0.1, top_speed_mps=25, mass_kg=60, attack_force_n=500)
    slow = make_sheet("slow", top_speed_mps=8, mass_kg=300, attack_force_n=3000, aggression_0_1=0.9)
    runner = make_sheet(
        "runner", aggression_0_1=0.1, top_speed_mps=5, mass_kg=100, attack_force_n=700
    )
    chaser = make_sheet(
        "chaser", top_speed_mps=20, mass_kg=100, attack_force_n=1500, aggression_0_1=1
    )
    rock = make_sheet(
        "rock", body="inert", mass_kg=50, size_m=0.4, top_speed_mps=0, attack_force_n=0,
        attacks_per_s=0, weapons=["none"],
    )  # fmt: skip
    sword = make_sheet(
        "sword", body="inert", mass_kg=1.5, size_m=1.0, top_speed_mps=0, attack_force_n=0,
        attacks_per_s=0, weapons=["none"],
    )  # fmt: skip
    goose = make_sheet("goose", mass_kg=4, size_m=0.8, attack_force_n=100)
    dragon = make_dragon(
        ["flight", "breath_weapon"], name="dragon", mass_kg=3000, attack_force_n=20000
    )
    truck = make_sheet(
        "truck", body="machine", weapons=["ramming"], mass_kg=8000, size_m=6, top_speed_mps=20,
        attack_force_n=0, endurance_s=600, armor_0_1=0.5,
    )  # fmt: skip
    return [
        ("1 v 1", matchup_of(1, 1), [bear, wolf], None),
        ("1 v 6 in a forest", matchup_of(1, 6, terrain=Terrain.FOREST), [bear, wolf], None),
        ("1 v 300 swarm", matchup_of(1, 300), [lion(), ant()], None),
        ("300 v 300 swarm", matchup_of(300, 300), [ant(), ant()], None),
        ("a machine breaks down", matchup_of(1, 1), [tank, boulder], None),
        ("a machine swarm stops", matchup_of(250, 1), [drones, boulder], None),
        ("spines", matchup_of(1, 1), [wolf, cactus], None),
        ("a side escapes", matchup_of(1, 1), [fast, slow], None),
        ("a side retreats but is caught", matchup_of(1, 1), [runner, chaser], None),
        ("a swarm side escapes", matchup_of(300, 300), [fast, slow], None),
        ("a draw", matchup_of(1, 1), [goose, boulder], None),
        ("no contest", matchup_of(1, 1), [rock, sword], None),
        ("a breath weapon", matchup_of(1, 1), [dragon, truck], None),
        ("a size reference", matchup_of(1, 1, ref_0="horse"), [duck(), lion()], [horse(), None]),
    ]


@pytest.fixture(scope="module")
def results():
    return {
        label: run(matchup, sheets, runs=40, reference_sheets=refs, explain=False)
        for label, matchup, sheets, refs in scenarios()
    }


def test_every_emitted_event_type_and_hint_is_described_in_the_guide(results):
    phrases, words, documented_types = documented_phrases_and_words()
    assert "attack" not in documented_types  # the guide says ATTACK is never emitted
    emitted = {(e.type.value, e.text_hint) for r in results.values() for e in r.representative_log}
    for kind, hint in sorted(emitted):
        assert kind in documented_types, f"event type {kind!r} is not in the guide"
        assert is_described(hint, phrases, words), f"{kind}: {hint!r} is not described in the guide"
    assert len(emitted) >= 20  # the scenarios really do exercise a wide vocabulary


def test_the_guides_weapon_words_are_the_engines(results):
    from app.simulation.fighters import _WEAPON_WORD

    _, words, _ = documented_phrases_and_words()
    assert set(_WEAPON_WORD.values()) | {"strike"} == words


def test_every_log_obeys_the_rules_the_guide_states(results):
    for label, result in results.items():
        log = result.representative_log
        assert len(log) <= 300, label
        assert log[-1].type == EventType.END, label
        times = [e.t for e in log]
        assert times == sorted(times) and all(0 <= t <= 600 for t in times), label
        assert EventType.ATTACK not in {e.type for e in log}, label


def test_event_shapes_match_the_guides_table(results):
    # approach: group_size is how many fighters the side has, and there is no actor
    forest = results["1 v 6 in a forest"].representative_log
    approach = [e for e in forest if e.type == EventType.APPROACH]
    assert {(e.side, e.group_size, e.actor) for e in approach} == {(0, 1, None), (1, 6, None)}
    # single-fighter KO: side went down, actor is the fallen index, no target
    kos = [e for e in results["1 v 1"].representative_log if e.type == EventType.KO]
    assert kos and all(e.actor is not None and e.target is None for e in kos)
    # swarm: HIT and KO are group events for both sides, and there are no misses
    swarm = results["1 v 300 swarm"].representative_log
    swarm_acts = [e for e in swarm if e.type in (EventType.HIT, EventType.KO)]
    assert swarm_acts and all(e.actor is None and e.target is None for e in swarm_acts)
    assert {e.side for e in swarm_acts} == {0, 1}
    assert not [e for e in swarm if e.type == EventType.MISS]
    # a swarm hit's damage is the group total; a knock-out has none
    assert all(e.damage is not None for e in swarm if e.type == EventType.HIT)
    assert all(e.damage is None for e in swarm if e.type == EventType.KO)
    # spines: side is the defender (the cactus is side 1), and actor/target are swapped
    spines = results["spines"].representative_log
    jabs = [e for e in spines if e.text_hint == "spines jab back"]
    assert jabs and all(e.side == 1 and e.actor == 0 and e.target == 0 for e in jabs)
    # a machine that breaks: the KO is on the machine's side, and says it was out of action
    machine = results["a machine breaks down"].representative_log
    broke = [(e.side, e.text_hint) for e in machine if e.type == EventType.KO]
    assert broke == [(0, "out of action: its operating time ran out")]
    # retreat without flee: the runner is too slow, so the fight goes on
    caught = [e.type for e in results["a side retreats but is caught"].representative_log]
    assert EventType.RETREAT in caught and EventType.FLEE not in caught
    escaped = [e.type for e in results["a side escapes"].representative_log]
    assert escaped.index(EventType.RETREAT) < escaped.index(EventType.FLEE)
    # END: the winner's side for a decisive fight, 0 for a draw or no contest
    for label in ("1 v 1", "a side escapes"):
        result = results[label]
        winner = 0 if result.outcome == "win_0" else 1
        assert result.representative_log[-1].side == winner, label
    for label in ("a draw", "no contest"):
        assert results[label].representative_log[-1].side == 0, label
