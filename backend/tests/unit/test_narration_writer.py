"""The LLM announcer writer: checked scripts, the number guard, one retry, and template fallback."""

import json
import socket
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from app.models.narration import Script
from app.models.simulation import SimulationResult
from app.narration import writer
from app.narration.facts import NarrationFacts, build_facts
from app.narration.templates import MAX_BEATS, MAX_LINE, MIN_BEATS, intro_script, template_scripts
from app.narration.writer import (
    ScriptRejected,
    check_script,
    fill_placeholders,
    outro_placeholders,
    read_reply,
    reply_schema,
    unsupported_numbers,
    write_scripts,
)
from app.providers.mock import MockChatLLM
from tests.narration_samples import Sample, ScriptedChat, sample_chat, samples

SAMPLES = {s.key: s for s in samples()}
KEYS = list(SAMPLES)
GRIZZLY = "grizzly-vs-gorilla"
GRIFFIN = "griffin-vs-horse"
PROMPTS = ("announcer_intro", "play_by_play", "outro")


# Block name lookups, outgoing connections, and httpx sends, and fail the test if anything tried
# (the writer swallows errors from the model, so a refusal alone could go unnoticed). Plain
# sockets stay allowed: on Windows the asyncio event loop needs a local socket pair to start.
@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    attempts: list[str] = []

    def refuse(*args: object, **kwargs: object) -> None:
        attempts.append(repr(args)[:80])
        raise AssertionError("the narration writer must not touch the network")

    async def refuse_async(*args: object, **kwargs: object) -> None:
        refuse(*args)

    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse_async)
    yield
    assert attempts == [], "a network call was attempted"


# Facts for a sample, built the way the writer builds them.
def _facts(sample: Sample, result: SimulationResult | None = None) -> NarrationFacts:
    return build_facts(sample.sheets, result or sample.result, sample.fair, sample.counts)


# The sample's templates, for comparing with a fallback.
def _templates(sample: Sample, result: SimulationResult | None = None) -> list[Script]:
    return template_scripts(_facts(sample, result), result or sample.result)


# Run the writer on a sample with a given fake model.
async def _write(sample: Sample, chat: Any, result: SimulationResult | None = None) -> list[Script]:
    return await write_scripts(
        sample.sheets, result or sample.result, sample.fair, chat=chat, counts=sample.counts
    )


# A copy of a sample reply with line n's text replaced.
def _with_line(sample: Sample, prompt: str, n: int, text: str) -> dict[str, Any]:
    lines = [dict(line) for line in sample.replies[prompt]["lines"]]
    lines[n]["text"] = text
    return {"lines": lines}


# A fake model that answers one prompt with `replies` (in order) and the others validly.
def _chat_with(sample: Sample, prompt: str, *replies: Any) -> ScriptedChat:
    chat = sample_chat(sample)
    chat.replies[prompt] = list(replies)
    return chat


# --- a. Every script validates; every at_event exists ----------------------------------------


@pytest.mark.parametrize("key", KEYS)
async def test_llm_scripts_validate_and_point_at_real_events(key: str) -> None:
    sample = SAMPLES[key]
    chat = sample_chat(sample)
    scripts = await _write(sample, chat)
    assert [s.kind for s in scripts] == ["intro", "play_by_play", "outro"]
    log_len = len(sample.result.representative_log)
    for script in scripts:
        assert Script.model_validate(script.model_dump()) == script
        assert script.fallback is False
        assert check_script(script, _facts(sample), log_len) == []
    events = [line.at_event for line in scripts[1].lines]
    assert all(e is not None and 0 <= e < log_len for e in events)
    assert events == sorted(events)
    assert [chat.count(p) for p in PROMPTS] == [1, 1, 1]


@pytest.mark.parametrize("key", KEYS)
def test_template_scripts_pass_the_writer_checks(key: str) -> None:
    sample = SAMPLES[key]
    for script in _templates(sample):
        log_len = len(sample.result.representative_log)
        assert check_script(script, _facts(sample), log_len) == [], script.kind


@pytest.mark.parametrize(
    "events",
    [
        [0, 1, 2, 3, 4, 5, 6, 99],  # past the end of the log
        [0, 1, 2, 3, 4, 5, 6, -1],  # negative
        [0, 1, 2, 5, 4, 5, 6, 7],  # goes backwards
        [0, 1, 2, 3, 4, 5, 6, None],  # missing
    ],
)
def test_bad_at_event_is_rejected(events: list[int | None]) -> None:
    sample = SAMPLES[GRIZZLY]
    lines = [{"speaker": "announcer", "text": "Here we go!", "at_event": e} for e in events]
    reply = json.dumps({"lines": lines})
    with pytest.raises(ScriptRejected, match="at_event"):
        read_reply("play_by_play", reply, _facts(sample), len(sample.result.representative_log))


async def test_short_log_may_repeat_events_like_the_template() -> None:
    sample = SAMPLES[GRIZZLY]
    short = sample.result.model_copy(
        update={"representative_log": sample.result.representative_log[:3]}
    )
    beats = [0, 0, 1, 1, 1, 2, 2, 2]
    lines = [{"speaker": "announcer", "text": "Here we go!", "at_event": e} for e in beats]
    chat = _chat_with(sample, "play_by_play", {"lines": lines})
    _, pbp, _ = await _write(sample, chat, short)
    assert pbp.fallback is False and [line.at_event for line in pbp.lines] == beats


async def test_empty_log_uses_the_template_without_asking() -> None:
    sample = SAMPLES[GRIZZLY]
    empty = sample.result.model_copy(update={"representative_log": []})
    chat = sample_chat(sample)
    _, pbp, _ = await _write(sample, chat, empty)
    assert pbp.fallback is True and pbp == _templates(sample, empty)[1]
    assert chat.count("play_by_play") == 0
    assert len(pbp.lines) >= MIN_BEATS and all(line.at_event is None for line in pbp.lines)


# --- b. The number guard on the writer path --------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "The Grizzly bear tips the scales at 412 kilograms.",  # invented digit
        "That is four hundred kilograms of bear.",  # number word
        "The Grizzly bear takes this one 73% of the time.",  # percentage
        "Our odds desk has it at eight to one.",  # ratio
    ],
)
async def test_guard_rejects_invented_numbers_then_falls_back(bad: str) -> None:
    sample = SAMPLES[GRIZZLY]
    assert unsupported_numbers(bad, _facts(sample)), "the guard must flag this line"
    chat = _chat_with(sample, "announcer_intro", _with_line(sample, "announcer_intro", 2, bad))
    intro, pbp, outro = await _write(sample, chat)
    assert intro.fallback is True and intro == _templates(sample)[0]
    assert chat.count("announcer_intro") == 2  # the one regeneration, then the template
    assert pbp.fallback is False and outro.fallback is False  # the others are unaffected


@pytest.mark.parametrize(
    "hidden",
    [
        "ｎｉｎｅ hits landed for the Grizzly bear.",  # full-width "nine"
        "ni\u200bne hits landed for the Grizzly bear.",  # zero-width space inside "nine"
        "ni\u00adne hits landed for the Grizzly bear.",  # soft hyphen inside "nine"
    ],
)
async def test_guard_reads_normalized_text(hidden: str) -> None:
    sample = SAMPLES[GRIZZLY]
    plain = "nine hits landed for the Grizzly bear."  # 9 is not backed (5 is, for this battle)
    assert unsupported_numbers(plain, _facts(sample)), "the guard must flag the plain line"
    reply = json.dumps(_with_line(sample, "announcer_intro", 2, hidden))
    with pytest.raises(ScriptRejected, match="'nine'"):  # the guard saw the normalized word
        read_reply("intro", reply, _facts(sample), 13)
    chat = _chat_with(sample, "announcer_intro", _with_line(sample, "announcer_intro", 2, hidden))
    intro, _, _ = await _write(sample, chat)
    assert intro.fallback is True and intro == _templates(sample)[0]
    assert chat.count("announcer_intro") == 2


async def test_guard_rejects_an_invented_number_in_play_by_play() -> None:
    sample = SAMPLES[GRIZZLY]
    bad = _with_line(sample, "play_by_play", 4, "Gorilla lands a punch with 9000 newtons!")
    chat = _chat_with(sample, "play_by_play", bad)
    _, pbp, _ = await _write(sample, chat)
    assert pbp.fallback is True and chat.count("play_by_play") == 2


async def test_guard_rejects_a_number_the_outro_writes_itself() -> None:
    sample = SAMPLES[GRIZZLY]
    bad = _with_line(sample, "outro", 1, "The {winner} won 90% of the time.")
    chat = _chat_with(sample, "outro", bad)
    _, _, outro = await _write(sample, chat)
    assert outro.fallback is True and chat.count("outro") == 2


async def test_numbers_from_the_inputs_pass() -> None:
    sample = SAMPLES[GRIZZLY]
    intro, _, _ = await _write(sample, sample_chat(sample))
    text = " ".join(line.text for line in intro.lines)
    for said in ("389 kilograms", "858 pounds", "140 kilograms", "12 meters per second"):
        assert said in text
    assert intro.fallback is False


def test_a_name_is_never_read_as_a_number() -> None:
    sample = SAMPLES[GRIZZLY]
    data = sample.sheets[1].model_dump(mode="json") | {"display_name": "Three-toed sloth"}
    sheets = (sample.sheets[0], type(sample.sheets[1]).model_validate(data))
    facts = build_facts(sheets, sample.result, sample.fair, sample.counts)
    assert unsupported_numbers("The Three-toed sloth closes in!", facts) == []
    assert unsupported_numbers("Seven sloths close in!", facts)


# --- c. A failing model gives templates, with no network -------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timed out"),
        httpx.ConnectError("refused"),
        LookupError("no mock fixture"),
        RuntimeError("anything else"),
    ],
)
async def test_failing_llm_returns_templates_without_network(error: Exception) -> None:
    sample = SAMPLES[GRIZZLY]
    chat = ScriptedChat({p: [error] for p in PROMPTS})
    scripts = await _write(sample, chat)
    assert all(s.fallback is True for s in scripts)
    assert scripts == _templates(sample)
    assert [chat.count(p) for p in PROMPTS] == [1, 1, 1]  # an outage is not retried here


async def test_each_script_falls_back_on_its_own() -> None:
    sample = SAMPLES[GRIZZLY]
    chat = _chat_with(sample, "outro", TimeoutError("slow"))
    intro, pbp, outro = await _write(sample, chat)
    assert (intro.fallback, pbp.fallback, outro.fallback) == (False, False, True)


async def test_no_provider_at_all_returns_templates(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(name: str) -> None:
        raise RuntimeError("Live 'chat' provider needs settings")

    monkeypatch.setattr(writer, "get_provider", broken)
    sample = SAMPLES[GRIZZLY]
    scripts = await write_scripts(sample.sheets, sample.result, sample.fair, counts=sample.counts)
    assert scripts == _templates(sample)


async def test_mock_mode_with_missing_fixtures_falls_back(tmp_path: Any) -> None:
    sample = SAMPLES[GRIZZLY]
    scripts = await _write(sample, MockChatLLM(fixture_dir=tmp_path))
    assert scripts == _templates(sample)


# Mock mode: intro and outro come from the committed mock defaults; the play-by-play fixture has
# no default (canned beats can't follow a real log), so it is the template, synced to real events.
@pytest.mark.parametrize("key", KEYS)
async def test_mock_mode_defaults_never_crash(key: str) -> None:
    sample = SAMPLES[key]  # chat=None: the registry's MockChatLLM with the committed fixtures
    scripts = await write_scripts(sample.sheets, sample.result, sample.fair, counts=sample.counts)
    log_len = len(sample.result.representative_log)
    assert [s.kind for s in scripts] == ["intro", "play_by_play", "outro"]
    for script in scripts:
        assert check_script(script, _facts(sample), log_len) == []
    intro, pbp, outro = scripts
    assert intro.fallback is False and outro.fallback is False
    template_pbp = _templates(sample)[1]
    assert pbp.fallback is True and pbp == template_pbp
    assert [line.at_event for line in pbp.lines] == [line.at_event for line in template_pbp.lines]


# --- d. Lengths and counts, on both paths ----------------------------------------------------


@pytest.mark.parametrize("path", ["llm", "fallback"])
@pytest.mark.parametrize("key", KEYS)
async def test_lengths_and_counts(key: str, path: str) -> None:
    sample = SAMPLES[key]
    chat = sample_chat(sample) if path == "llm" else ScriptedChat({})
    intro, pbp, outro = await _write(sample, chat)
    assert {intro.fallback, pbp.fallback, outro.fallback} == {path == "fallback"}
    assert 4 <= len(intro.lines) <= 8
    assert MIN_BEATS <= len(pbp.lines) <= MAX_BEATS
    assert 4 <= len(outro.lines) <= 6
    for script in (intro, pbp, outro):
        assert all(0 < len(line.text) <= MAX_LINE for line in script.lines)


@pytest.mark.parametrize(
    ("prompt", "keep"),
    [("announcer_intro", 3), ("play_by_play", MIN_BEATS - 1), ("outro", 3)],
)
async def test_too_few_lines_is_rejected(prompt: str, keep: int) -> None:
    sample = SAMPLES[GRIZZLY]
    lines = sample.replies[prompt]["lines"]
    if prompt == "outro":  # keep every required placeholder, so only the count is wrong
        lines = [{"speaker": "announcer", "text": "{winner}, {win_pct}, {deciding_factor}."}]
        lines += [{"speaker": "announcer", "text": "{fair_fight}"}] * (keep - 1)
    chat = _chat_with(sample, prompt, {"lines": lines[:keep]})
    scripts = await _write(sample, chat)
    assert scripts[PROMPTS.index(prompt)].fallback is True and chat.count(prompt) == 2


async def test_too_many_lines_is_rejected() -> None:
    sample = SAMPLES[GRIZZLY]
    lines = sample.replies["announcer_intro"]["lines"]
    chat = _chat_with(sample, "announcer_intro", {"lines": lines + lines[:3]})  # nine lines
    intro, _, _ = await _write(sample, chat)
    assert intro.fallback is True


async def test_too_many_beats_is_rejected() -> None:
    sample = SAMPLES[GRIZZLY]
    line = {"speaker": "announcer", "text": "Here we go!", "at_event": 0}
    chat = _chat_with(sample, "play_by_play", {"lines": [line] * (MAX_BEATS + 1)})
    _, pbp, _ = await _write(sample, chat)
    assert pbp.fallback is True


async def test_a_line_over_the_limit_is_rejected() -> None:
    sample = SAMPLES[GRIZZLY]
    long = "The Grizzly bear is " + "very " * 40 + "large."
    assert len(long) > MAX_LINE
    chat = _chat_with(sample, "announcer_intro", _with_line(sample, "announcer_intro", 0, long))
    intro, _, _ = await _write(sample, chat)
    assert intro.fallback is True


def test_line_limit_counts_filled_placeholders() -> None:
    sample = SAMPLES[GRIZZLY]
    text = "{fair_fight} " + "And that, folks, is what we call a fair fight. " * 3
    lines = [{"speaker": "announcer", "text": t} for t in ("{winner} {win_pct}", text)]
    lines += [{"speaker": "announcer", "text": "{deciding_factor}"}] * 2
    reply = json.dumps({"lines": lines})
    assert len(text) < MAX_LINE  # short as written, too long once {fair_fight} is filled in
    with pytest.raises(ScriptRejected, match="characters"):
        read_reply("outro", reply, _facts(sample), 13)


# --- e. Prompts get the display_name, never the raw text -------------------------------------


async def test_prompts_get_display_name_not_raw_text() -> None:
    raw = "my neighbor's angry goose lol"
    sample = SAMPLES[GRIZZLY]
    data = sample.sheets[1].model_dump(mode="json")
    data |= {"fighter_id": "canada-goose", "display_name": "Canada goose"}
    sheets = (sample.sheets[0], type(sample.sheets[1]).model_validate(data))
    chat = ScriptedChat({p: ["not json", "still not json"] for p in PROMPTS})  # forces a retry
    await write_scripts(sheets, sample.result, sample.fair, chat=chat, counts=sample.counts)
    assert len(chat.calls) == 6
    for _, messages, _ in chat.calls:
        text = "\n".join(m["content"] for m in messages)
        assert "Canada goose" in messages[1]["content"]
        assert "Grizzly bear" in messages[1]["content"]
        assert raw not in text and "neighbor" not in text


# --- f. Regenerate once ---------------------------------------------------------------------


@pytest.mark.parametrize("prompt", PROMPTS)
async def test_invalid_then_valid_uses_the_second_reply(prompt: str) -> None:
    sample = SAMPLES[GRIZZLY]
    chat = _chat_with(sample, prompt, "not json at all", sample.replies[prompt])
    scripts = await _write(sample, chat)
    assert scripts[PROMPTS.index(prompt)].fallback is False
    assert chat.count(prompt) == 2
    retry = [m for name, m, _ in chat.calls if name == prompt][1]
    assert retry[-2] == {"role": "assistant", "content": "not json at all"}
    assert "rejected" in retry[-1]["content"] and "JSON" in retry[-1]["content"]


@pytest.mark.parametrize("prompt", PROMPTS)
async def test_invalid_twice_falls_back(prompt: str) -> None:
    sample = SAMPLES[GRIZZLY]
    chat = _chat_with(sample, prompt, {"lines": []}, '{"lines": "nope"}')
    scripts = await _write(sample, chat)
    i = PROMPTS.index(prompt)
    assert scripts[i].fallback is True and scripts[i] == _templates(sample)[i]
    assert chat.count(prompt) == 2


async def test_json_schema_mode_is_used() -> None:
    sample = SAMPLES[GRIZZLY]
    chat = sample_chat(sample)
    await _write(sample, chat)
    schemas = {name: schema for name, _, schema in chat.calls}
    pbp = schemas["play_by_play"]
    assert pbp == reply_schema("play_by_play", 13)
    item = pbp["properties"]["lines"]["items"]  # type: ignore[index]
    assert item["required"] == ["speaker", "text", "at_event"]
    assert item["properties"]["at_event"]["maximum"] == 12
    assert "at_event" not in schemas["announcer_intro"]["properties"]["lines"]["items"]["required"]  # type: ignore[index]


# --- g. Outro placeholders are filled by code ------------------------------------------------


async def test_outro_placeholders_are_filled_with_real_numbers() -> None:
    sample = SAMPLES[GRIZZLY]
    facts = _facts(sample)
    _, _, outro = await _write(sample, sample_chat(sample))
    text = "\n".join(line.text for line in outro.lines)
    assert outro.fallback is False
    assert f"Grizzly bear took it {facts.win_pct[0]}% of the time across 1,000" in text
    assert "The deciding factor tonight: sheer mass." in text
    assert "About 3 gorillas make it a coin flip, winning 50% of the time." in text
    assert "{" not in text and "}" not in text


@pytest.mark.parametrize(
    "bad",
    [
        "{winner} drew a crowd of {crowd_size}!",  # unknown placeholder
        "{winner} won {win_pct of the time.",  # leftover brace
        "{winner} wins! { }",  # stray braces
    ],
)
async def test_bad_placeholders_trigger_retry_then_fallback(bad: str) -> None:
    sample = SAMPLES[GRIZZLY]
    chat = _chat_with(sample, "outro", _with_line(sample, "outro", 0, bad))
    _, _, outro = await _write(sample, chat)
    assert outro.fallback is True and chat.count("outro") == 2


async def test_unknown_placeholder_then_valid_reply() -> None:
    sample = SAMPLES[GRIZZLY]
    bad = _with_line(sample, "outro", 0, "Your winner, by {margin}: the {winner}!")
    chat = _chat_with(sample, "outro", bad, sample.replies["outro"])
    _, _, outro = await _write(sample, chat)
    assert outro.fallback is False and chat.count("outro") == 2


async def test_outro_missing_a_required_placeholder_is_rejected() -> None:
    sample = SAMPLES[GRIZZLY]
    bad = _with_line(sample, "outro", 1, "The {winner} took it. Every time. Basically.")
    chat = _chat_with(sample, "outro", bad)
    _, _, outro = await _write(sample, chat)
    assert outro.fallback is True


async def test_draw_outro_uses_draw_pct_and_has_no_winner() -> None:
    sample = SAMPLES[GRIZZLY]
    draw = sample.result.model_copy(update={"outcome": "draw"})
    assert "winner" not in outro_placeholders(_facts(sample, draw))
    lines = [
        {"speaker": "announcer", "text": "It's a draw! Nobody takes the belt tonight!"},
        {"speaker": "color_commentator", "text": "{draw_pct} of simulated fights ended even."},
        {"speaker": "announcer", "text": "The deciding factor: {deciding_factor}."},
        {"speaker": "color_commentator", "text": "{fair_fight}"},
    ]
    chat = _chat_with(sample, "outro", sample.replies["outro"], {"lines": lines})
    _, _, outro = await _write(sample, chat, draw)
    assert outro.fallback is False and chat.count("outro") == 2  # {winner} is unknown in a draw
    assert outro.lines[1].text == "5% of simulated fights ended even."


# Lopsided results (win probabilities, draw, CI bounds) and the small percents the outro fills in.
LOPSIDED = [
    ((0.94, 0.054), 0.006, ((0.925, 0.955), (0.041, 0.067)), ("5%", "1%")),
    ((0.93, 0.067), 0.003, ((0.914, 0.946), (0.052, 0.082)), ("7%", "0%")),
]


@pytest.mark.parametrize(("win", "draw", "ci", "small"), LOPSIDED)
async def test_lopsided_outro_keeps_small_percents(
    win: tuple[float, float],
    draw: float,
    ci: tuple[tuple[float, float], tuple[float, float]],
    small: tuple[str, str],
) -> None:
    sample = SAMPLES[GRIZZLY]
    update = {"win_prob": win, "draw_prob": draw, "win_prob_ci95": ci, "outcome": "win_0"}
    result = sample.result.model_copy(update=update)
    facts = _facts(sample, result)
    values = outro_placeholders(facts)
    assert (values["blue_win_pct"], values["draw_pct"]) == small
    for name in ("red_win_pct", "blue_win_pct", "draw_pct"):
        assert unsupported_numbers(values[name], facts) == [], name
    lines = [
        {"speaker": "announcer", "text": "Your winner, in a landslide: the {winner}!"},
        {"speaker": "color_commentator", "text": "The {winner} took it {win_pct} of the time."},
        {"speaker": "announcer", "text": "The Gorilla won {blue_win_pct}. Draws: {draw_pct}."},
        {"speaker": "color_commentator", "text": "The deciding factor: {deciding_factor}."},
        {"speaker": "announcer", "text": "{fair_fight}"},
    ]
    chat = _chat_with(sample, "outro", {"lines": lines})
    _, _, outro = await _write(sample, chat, result)
    assert outro.fallback is False
    assert chat.count("outro") == 1  # accepted first time, no retry
    assert outro.lines[2].text == f"The Gorilla won {small[0]}. Draws: {small[1]}."


def test_fill_placeholders_keeps_one_percent_sign() -> None:
    values = {"win_pct": "71%", "winner": "Grizzly bear"}
    assert fill_placeholders("{winner}: {win_pct}%!", values) == "Grizzly bear: 71%!"
    assert fill_placeholders("{win_pct} percent", values) == "71%"
    with pytest.raises(ScriptRejected, match="crowd"):
        fill_placeholders("{crowd}", values)


# --- h. Mythical stats come from legend ------------------------------------------------------


async def test_mythical_intro_says_legend_on_both_paths() -> None:
    sample = SAMPLES[GRIFFIN]
    intro, _, _ = await _write(sample, sample_chat(sample))
    assert intro.fallback is False
    assert "legend" in " ".join(line.text for line in intro.lines).lower()
    template = intro_script(_facts(sample))
    assert template.fallback is True
    assert "legend" in " ".join(line.text for line in template.lines).lower()


async def test_mythical_intro_without_legend_is_rejected() -> None:
    sample = SAMPLES[GRIFFIN]
    plain = [
        line | {"text": line["text"].replace("according to legend: ", "").replace("Legend", "It")}
        for line in sample.replies["announcer_intro"]["lines"]
    ]
    plain = [line | {"text": line["text"].replace("Legends", "Those")} for line in plain]
    assert not any("legend" in line["text"].lower() for line in plain)
    chat = _chat_with(sample, "announcer_intro", {"lines": plain})
    intro, _, _ = await _write(sample, chat)
    assert intro.fallback is True and chat.count("announcer_intro") == 2
    assert "legend" in " ".join(line.text for line in intro.lines).lower()
