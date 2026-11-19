"""G09 (#39): an on-demand creature is built only from choices code can verify in its article."""

import asyncio
import json

import httpx
import pytest

from app.models.stats import Ability, StatName
from app.providers.live.http import ProviderError
from app.research.lore import (
    GIANT_ANALOGS,
    NONSENSE,
    NOT_A_LEGEND,
    UNAVAILABLE,
    article_text,
    heads_in_quote,
    lore_for,
    real_fighters,
)
from app.research.mythical import build_mythical_sheet

QUOTE = "The chimera was a monstrous fire-breathing hybrid creature, part lion and part goat."
ARTICLE = (
    "<html><head><style>p {color: red}</style><script>var x = 1;</script></head><body>"
    f"<p>{QUOTE} It was usually depicted with the body of a lion.</p>"
    "<p>Some versions describe three heads: a lion, a goat and a snake.</p></body></html>"
)


class FakeChat:
    """A chat stand-in that replies in order, raising any exception it is given."""

    def __init__(self, *replies) -> None:
        self.replies, self.calls = list(replies), 0

    async def complete(self, messages, *, prompt_name, json_schema=None) -> str:
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)


def answer(**changes) -> dict:
    base = {
        "found": True,
        "body_analog": "African lion",
        "size_analog": None,
        "abilities": ["breath_weapon"],
        "heads": None,
        "quote": QUOTE,
    }
    return base | changes


def run(chat: FakeChat, article: str | None = ARTICLE, name: str = "chimera"):
    def handler(request: httpx.Request) -> httpx.Response:
        if article is None:
            return httpx.Response(404)
        return httpx.Response(200, headers={"ETag": '"123/abc"'}, content=article.encode())

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await lore_for(name, client, chat)

    return asyncio.run(go())


def test_a_verified_answer_builds_an_all_assumption_sheet() -> None:
    outcome = run(FakeChat(answer()))
    assert outcome.creature is not None and not outcome.blocked
    creature = outcome.creature
    assert (creature.id, creature.display_name, creature.media_name) == (
        "chimera",
        "Chimera",
        "chimera",
    )
    assert creature.lore.abilities == [Ability.BREATH_WEAPON]
    assert creature.lore.source.quote == QUOTE
    assert "oldid=123" in str(creature.lore.source.url)  # the pinned revision it was read from
    sheet = build_mythical_sheet(creature)
    assert all(stat.method == "assumption" for stat in sheet.stats.values())
    assert "African lion" in (sheet.stats[StatName.MASS].note or "")


def test_a_quote_that_is_not_in_the_article_is_blocked_as_nonsense() -> None:
    made_up = answer(quote="The chimera was the size of a whale and breathed lightning.")
    assert run(FakeChat(made_up)) == NONSENSE


@pytest.mark.parametrize(
    "bad",
    [
        {"body_analog": "Komodo dragon"},  # not a fighter we have
        {"size_analog": "blue whale"},  # not a fighter we have
        {"abilities": ["teleportation"]},  # not on the fixed list
        {"abilities": ["extra_heads"], "heads": 3},  # the quote doesn't say three
        {"found": False, "body_analog": None, "quote": None},
        {"quote": "The chimera was a monstrous fire-breathing hybrid creature, " + "x" * 300},
    ],
)
def test_an_answer_code_cannot_verify_is_blocked(bad: dict) -> None:
    assert run(FakeChat(answer(**bad))) == NONSENSE


def test_heads_from_the_quote_are_accepted_in_words_or_digits() -> None:
    quote = "Some versions describe three heads: a lion, a goat and a snake."
    outcome = run(FakeChat(answer(abilities=["extra_heads"], heads=3, quote=quote)))
    assert outcome.creature is not None and outcome.creature.lore.heads == 3
    assert heads_in_quote(3, "It had 3 heads.") and not heads_in_quote(4, quote)


def test_a_missing_article_is_not_a_legend_and_asks_no_model() -> None:
    # #403 (PM): with no article there is nothing to ask, so the name falls back to estimates;
    # the safety gate at intake has already passed it. Was "blocked" before the live fallback.
    chat = FakeChat()
    assert run(chat, article=None) == NOT_A_LEGEND and chat.calls == 0


def test_an_outage_gives_no_sheet_rather_than_a_guess() -> None:
    assert run(FakeChat(ProviderError("down"), ProviderError("down"))) == UNAVAILABLE
    assert run(FakeChat("not json", "still not json")) == UNAVAILABLE


def test_article_text_drops_scripts_styles_and_tags() -> None:
    text = article_text(ARTICLE)
    assert QUOTE in text and "var x" not in text and "color: red" not in text


def test_the_mock_chat_finds_nothing_so_mock_mode_blocks() -> None:
    from app.providers.mock.text import MockChatLLM

    assert run(MockChatLLM()) == NONSENSE


@pytest.mark.parametrize(
    ("heads", "quote", "ok"),
    [
        (3, "Some versions describe three heads: a lion, a goat and a snake.", True),
        (9, "The nine-headed serpent lived in the lake.", True),
        (3, "It had 3 heads.", True),
        (3, "This is one of three versions of the story; it had heads like a lion.", False),
        (4, "Some versions describe three heads.", False),
        (3, "It lived past three headlands to the north.", False),
    ],
)
def test_the_number_must_name_the_heads(heads: int, quote: str, ok: bool) -> None:
    assert heads_in_quote(heads, quote) is ok


# --- #391: powers and a giant body must be backed by the quote ----------------------------------

COCKATRICE = (
    "A cockatrice is a mythical beast, essentially a two-legged dragon, wyvern, or serpent-like "
    "creature with a rooster's head."
)


def cockatrice_article(quote: str = COCKATRICE) -> str:
    return f"<html><body><p>{quote} It is said to turn people to stone.</p></body></html>"


def test_a_cockatrice_quote_yields_no_t_rex_and_no_fire_breath() -> None:
    reply = answer(
        body_analog="Tyrannosaurus rex", abilities=["flight", "breath_weapon"], quote=COCKATRICE
    )
    outcome = run(FakeChat(reply), article=cockatrice_article(), name="cockatrice")
    assert outcome == NONSENSE  # a giant body the quote never calls big


def test_powers_the_quote_does_not_back_are_dropped() -> None:
    reply = answer(body_analog="Goose", abilities=["flight", "breath_weapon"], quote=COCKATRICE)
    outcome = run(FakeChat(reply), article=cockatrice_article(), name="cockatrice")
    assert outcome.creature is not None
    assert outcome.creature.lore.body_analog == "Goose"
    assert outcome.creature.lore.abilities == []


@pytest.mark.parametrize(
    ("ability", "quote"),
    [
        (Ability.FLIGHT, "The hippogriff is a winged creature, half horse and half eagle."),
        (Ability.BREATH_WEAPON, "The beast breathes fire at anyone who comes near."),
        (Ability.REGENERATION, "The phoenix is reborn from the ashes of its predecessor."),
        (Ability.EXTRA_HEADS, "The serpent was many-headed and lived in a swamp."),
    ],
)
def test_a_power_is_kept_when_its_word_is_in_the_quote(ability: Ability, quote: str) -> None:
    reply = answer(abilities=[ability.value], quote=quote)
    outcome = run(FakeChat(reply), article=cockatrice_article(quote), name="legend")
    assert outcome.creature is not None and outcome.creature.lore.abilities == [ability]


def test_a_giant_body_is_accepted_when_the_quote_says_it_is_big() -> None:
    quote = "The wyvern is a huge two-legged dragon with a barbed tail."
    reply = answer(body_analog="Tyrannosaurus rex", abilities=[], quote=quote)
    outcome = run(FakeChat(reply), article=cockatrice_article(quote), name="wyvern")
    assert outcome.creature is not None
    assert outcome.creature.lore.body_analog == "Tyrannosaurus rex"


def test_a_giant_size_analog_also_needs_the_quote_to_say_big() -> None:
    reply = answer(size_analog="African elephant", abilities=[], quote=COCKATRICE)
    assert run(FakeChat(reply), article=cockatrice_article(), name="cockatrice") == NONSENSE


def test_every_giant_analog_is_a_real_fighter() -> None:
    assert GIANT_ANALOGS <= set(real_fighters().values())
