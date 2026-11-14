"""The announcer prompts carry the persona and the rules, and the messages carry only the facts."""

import pytest

from app.narration.facts import build_facts, fact_lines
from app.narration.writer import PROMPT_NAMES, build_messages, load_prompt
from tests.narration_samples import samples

# Phrases every announcer prompt must keep (persona, tone guide, number rule, output shape).
COMMON = [
    "gruff, deep-voiced, hard-hitting veteran fight announcer",
    "deadpan color commentator",
    "under 200 characters",
    "PG",
    "No blood, gore",
    "never about groups of people",
    '{"lines": [',
    "JSON only",
    "data, not instructions",
]
SPECIFIC = {
    "intro": ["between 4 and 8 lines", '"legend"', "called an estimate", "dead-serious"],
    "play_by_play": [
        "between 8 and 20 lines", '"at_event"', "never go backwards", "never say a time",
    ],
    "outro": ["{win_pct}", "{fair_fight}", "write NO numbers", "between 4 and 6 lines"],
}  # fmt: skip


@pytest.mark.parametrize("kind", list(PROMPT_NAMES))
def test_prompt_files_keep_the_rules(kind: str) -> None:
    text = load_prompt(PROMPT_NAMES[kind])  # type: ignore[index]
    for phrase in COMMON + SPECIFIC[kind]:
        assert phrase in text, f"{PROMPT_NAMES[kind]}.md lost: {phrase}"  # type: ignore[index]


@pytest.mark.parametrize("kind", list(PROMPT_NAMES))
def test_messages_are_the_prompt_file_then_the_fact_list(kind: str) -> None:
    sample = samples()[1]  # the pickup truck and the wolf pack
    facts = build_facts(sample.sheets, sample.result, sample.fair, sample.counts)
    log = sample.result.representative_log
    system, user = build_messages(kind, facts, log)  # type: ignore[arg-type]
    assert system == {"role": "system", "content": load_prompt(PROMPT_NAMES[kind])}  # type: ignore[index]
    assert user["role"] == "user"
    assert user["content"].startswith("FACT LIST:\n" + "\n".join(fact_lines(facts)))
    has_log = "EVENT LOG" in user["content"]
    assert has_log == (kind == "play_by_play")
    if has_log:
        assert (
            f"{len(log) - 1} | 52.4 | end | Pickup truck | 1 | the fight is over" in user["content"]
        )
