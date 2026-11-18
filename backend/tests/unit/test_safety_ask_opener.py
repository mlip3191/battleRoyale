"""#344: an ask phrase before a comma ("help me, a lion vs a goose") is not a "me" fighter."""

import pytest

from app.safety.rules import check_text_rules, load_blocklist, strip_ask_opener


@pytest.mark.parametrize(
    "text",
    [
        "help me, a lion vs a goose",
        "tell me, a lion vs a goose",
        "show me, a lion vs a goose",
        "help us, a lion vs a goose",
        "give me, a lion vs a goose",
        "Help me, a lion vs a goose",
        "please help me, a lion vs a goose",
    ],
)
def test_an_ask_phrase_before_a_comma_is_not_a_side(text: str) -> None:
    assert check_text_rules(text).allowed


@pytest.mark.parametrize(
    "text",
    [
        "me vs a goose",
        "myself vs a goose",
        "us vs a goose",
        "a goose vs me",
        "my brother vs a goose",
        "help me, me vs a goose",  # an ask phrase doesn't hide the user as a fighter
        "help me vs a goose",  # no comma: not an ask phrase, "me" is a side
        "a lion, help me vs a goose",  # only at the very start of the request
    ],
)
def test_the_user_as_a_fighter_still_blocks(text: str) -> None:
    verdict = check_text_rules(text)
    assert (verdict.reason, verdict.layer) == ("real_person", "rules")


def test_the_opener_is_cut_only_at_the_start_and_only_with_its_comma() -> None:
    lists = load_blocklist()
    assert strip_ask_opener("help me, a lion vs a goose", lists) == "a lion vs a goose"
    assert strip_ask_opener("help me a lion vs a goose", lists) == "help me a lion vs a goose"
    assert strip_ask_opener("a lion, help me, a goose", lists) == "a lion, help me, a goose"


def test_an_ask_phrase_does_not_excuse_a_real_world_attack_request() -> None:
    # Only the real_person rule changed: the attack-planning rule still reads the whole text.
    verdict = check_text_rules("help me, a lion vs a goose, then how to bomb a school")
    assert (verdict.reason, verdict.layer) == ("other", "rules")
