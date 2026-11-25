"""#620: calm no-contest templates, no fact-list shorthand on air, and no invented weapons."""

import asyncio
import json
import re
from pathlib import Path

import pytest

from app.models.narration import Script, ScriptLine
from app.models.simulation import EventType, FightEvent, SimulationResult
from app.models.stats import StatSheet
from app.narration.facts import NarrationFacts, build_facts, fact_lines
from app.narration.templates import (
    CANT_HURT_BEATS,
    CANT_REACH_BEATS,
    NO_CONTEST_CLOSER,
    REACTIONS,
    play_by_play_script,
    template_scripts,
)
from app.narration.writer import (
    NOT_THEIR_WEAPON,
    SHORTHAND_REJECTED,
    ScriptRejected,
    check_script,
    read_reply,
    write_scripts,
)
from tests.narration_samples import Sample, ScriptedChat, samples

ROOT = Path(__file__).parents[3]
CONTRACTS = ROOT / "backend" / "tests" / "fixtures" / "contracts"
SEED = ROOT / "data" / "seed" / "fighters"
RESULT = SimulationResult.model_validate_json(
    (CONTRACTS / "simulation-result.json").read_text(encoding="utf-8")
)
# Lines from a fight broadcast that a no contest must never get.
HYPE = (*REACTIONS, "And that is the fight!", "Here we go!", "That is a knockout!")
# The "xN" count notation the fact list once used.
X_COUNT = re.compile(r"(?<![A-Za-z0-9])x\d", re.I)


# A stat sheet from the contract fixtures or the seed fighters.
def _sheet(name: str) -> StatSheet:
    path = CONTRACTS / name if name.startswith("stat-sheet") else SEED / name
    return StatSheet.model_validate(json.loads(path.read_text(encoding="utf-8")))


# A goose: the duck's sheet, renamed, with no weapons at all (as in the live run).
GOOSE = _sheet("duck.json").model_copy(update={"display_name": "Goose", "weapons": ["none"]})
HORSE = _sheet("horse.json")  # hooves and teeth, no claws


# A no-contest result shaped like the engine's (one END event with the reason as its hint).
def _no_contest(reach: bool) -> SimulationResult:
    factor = "habitat" if reach else "attack_force_n"
    hint = (
        "no contest: neither can reach the other"
        if reach
        else "no contest: nobody can hurt anybody"
    )
    explainer = "No contest: they can't reach each other." if reach else "No contest: no harm."
    return RESULT.model_copy(
        update={
            "win_prob": (0.0, 0.0),
            "draw_prob": 0.0,
            "win_prob_ci95": ((0.0, 0.0), (0.0, 0.0)),
            "mean_duration_s": 0.0,
            "outcome": "no_contest",
            "deciding_factor": factor,
            "deciding_factor_explainer": explainer,
            "representative_log": [FightEvent(t=0.0, type=EventType.END, side=0, text_hint=hint)],
        }
    )


# Facts for a rock-vs-sword style pair of objects (the toaster stands in for both).
def _object_facts(result: SimulationResult) -> NarrationFacts:
    toaster = _sheet("stat-sheet-toaster.json")
    sword = toaster.model_copy(update={"display_name": "Sword"})
    return build_facts([toaster.model_copy(update={"display_name": "Rock"}), sword], result)


# --- 1. No contest ---------------------------------------------------------------------------


@pytest.mark.parametrize("reach", [True, False], ids=["cannot-reach", "cannot-hurt"])
def test_a_no_contest_play_by_play_has_no_fight_hype(reach: bool) -> None:
    result = _no_contest(reach)
    facts = _object_facts(result)
    pbp = play_by_play_script(facts, result)
    texts = [ln.text for ln in pbp.lines]
    assert not any(hype in text for hype in HYPE for text in texts), texts
    calm = CANT_REACH_BEATS if reach else CANT_HURT_BEATS
    assert all(text in calm for text in texts[:-1]) and texts[-1] == NO_CONTEST_CLOSER
    assert check_script(pbp, facts, len(result.representative_log)) == []


@pytest.mark.parametrize("reach", [True, False], ids=["cannot-reach", "cannot-hurt"])
def test_a_no_contest_outro_matches_its_reason(reach: bool) -> None:
    result = _no_contest(reach)
    facts = _object_facts(result)
    _, _, outro = template_scripts(facts, result)
    text = " ".join(ln.text for ln in outro.lines)
    assert text.startswith("No contest!")
    assert ("never even met" in text) is reach
    assert ("cannot reach each other" in text) is reach
    assert ("cannot hurt each other" in text) is not reach
    assert check_script(outro, facts, len(result.representative_log)) == []


def test_an_empty_no_contest_log_still_gets_calm_lines_without_events() -> None:
    result = _no_contest(reach=False).model_copy(update={"representative_log": []})
    pbp = play_by_play_script(_object_facts(result), result)
    assert all(ln.at_event is None for ln in pbp.lines)
    assert not any(hype in ln.text for hype in HYPE for ln in pbp.lines)


# --- 2. Fact-list shorthand --------------------------------------------------------------------


@pytest.mark.parametrize("sample", samples(), ids=lambda s: s.key)
def test_the_fact_list_has_no_count_shorthand(sample: Sample) -> None:
    facts = build_facts(sample.sheets, sample.result, sample.fair, sample.counts)
    text = "\n".join(fact_lines(facts))
    assert not X_COUNT.search(text), text
    assert "none (" not in text


def test_the_fact_list_says_an_undecided_factor_in_plain_words() -> None:
    result = _no_contest(reach=False)
    text = "\n".join(fact_lines(_object_facts(result)))
    assert "deciding factor: no single factor decided it;" in text
    assert "none (no single factor decided it)" not in text


# A one-line-per-text script of the given kind, padded to a valid length.
def _script(kind: str, *texts: str, at_event: bool = False) -> Script:
    pad = ("The crowd waits.", "Still waiting.", "Here they come.")
    texts = (*texts, *pad[: max(0, 4 - len(texts))])
    lines = [
        ScriptLine(speaker="announcer", text=t, at_event=i if at_event else None)
        for i, t in enumerate(texts)
    ]
    return Script(kind=kind, lines=lines, fallback=False)  # type: ignore[arg-type]


COPIED = [
    "Warthog x1!",
    "In the red corner: Goose x1!",
    "Horse X1, ready to go!",
    "It came down to none (no single factor decided it).",
    "IT CAME DOWN TO NONE (NO SINGLE FACTOR DECIDED IT).",
    "The verdict: none ( no single factor decided it )",
]


@pytest.mark.parametrize("text", COPIED)
@pytest.mark.parametrize("kind", ["intro", "play_by_play", "outro"])
def test_a_copied_fact_list_line_is_rejected(kind: str, text: str) -> None:
    facts = build_facts([GOOSE, HORSE], RESULT)
    problems = check_script(_script(kind, text, at_event=kind == "play_by_play"), facts, 20)
    assert any(SHORTHAND_REJECTED in p for p in problems), problems


@pytest.mark.parametrize(
    "text", ["No single factor decided this one.", "None of that mattered.", "Six of them, folks!"]
)
def test_plain_words_pass_the_shorthand_check(text: str) -> None:
    facts = build_facts([GOOSE, HORSE], RESULT)
    assert check_script(_script("outro", text), facts, 0) == []


def test_a_model_intro_with_x1_falls_back_to_the_template() -> None:
    facts = build_facts([GOOSE, HORSE], RESULT)
    reply = {"lines": [{"speaker": "announcer", "text": t} for t in ("Goose x1!", "Horse x1!")]}
    reply["lines"] += [{"speaker": "announcer", "text": "Let's fight!"}] * 2
    with pytest.raises(ScriptRejected, match=SHORTHAND_REJECTED):
        read_reply("intro", json.dumps(reply), facts, 0)
    chat = ScriptedChat({"announcer_intro": [reply]})
    intro, _, _ = asyncio.run(write_scripts([GOOSE, HORSE], RESULT, chat=chat))
    assert intro.fallback is True
    assert not any(X_COUNT.search(ln.text) for ln in intro.lines)


# --- 3. Weapons --------------------------------------------------------------------------------


def test_facts_carry_weapons_without_none() -> None:
    goose, horse = build_facts([GOOSE, HORSE], RESULT).fighters
    assert goose.weapons == () and horse.weapons == ("hooves", "teeth")
    lines = fact_lines(build_facts([GOOSE, HORSE], RESULT))
    assert "  Goose weapons: no weapons at all" in lines
    assert "  Horse weapons: hooves, teeth" in lines


@pytest.mark.parametrize(
    "text", ["Goose, claws ready to strike!", "The goose rakes with its CLAWS.", "Talons out!"]
)
def test_a_weapon_no_fighter_has_is_rejected(text: str) -> None:
    facts = build_facts([GOOSE, HORSE], RESULT)
    problems = check_script(_script("play_by_play", text, at_event=True), facts, 20)
    assert any(NOT_THEIR_WEAPON in p for p in problems), problems


@pytest.mark.parametrize(
    "text",
    [
        "The horse kicks with its hooves!",  # the horse has hooves
        "The goose wanders into the thorns.",  # "thorns" is not "horns"
        "Goose has no weapons. None at all.",  # "none" is no weapon word
        "Goose pecks and flaps!",
    ],
)
def test_own_weapons_and_unrelated_words_pass(text: str) -> None:
    facts = build_facts([GOOSE, HORSE], RESULT)
    assert check_script(_script("play_by_play", text, at_event=True), facts, 20) == []


def test_a_model_play_by_play_that_invents_claws_falls_back() -> None:
    facts = build_facts([GOOSE, HORSE], RESULT)
    beats = ["Goose, claws ready to strike!", "Horse charges!", "Goose flaps!", "That's it!"]
    reply = {
        "lines": [{"speaker": "announcer", "text": t, "at_event": i} for i, t in enumerate(beats)]
    }
    with pytest.raises(ScriptRejected, match=NOT_THEIR_WEAPON):
        read_reply("play_by_play", json.dumps(reply), facts, len(RESULT.representative_log))
    chat = ScriptedChat({"play_by_play": [reply]})
    _, pbp, _ = asyncio.run(write_scripts([GOOSE, HORSE], RESULT, chat=chat))
    assert pbp.fallback is True
    assert not any("Goose, claws" in ln.text for ln in pbp.lines)


@pytest.mark.parametrize("sample", samples(), ids=lambda s: s.key)
def test_sample_templates_still_pass_every_check(sample: Sample) -> None:
    facts = build_facts(sample.sheets, sample.result, sample.fair, sample.counts)
    log_len = len(sample.result.representative_log)
    for script in template_scripts(facts, sample.result):
        assert check_script(script, facts, log_len) == [], script.kind
