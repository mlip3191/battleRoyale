"""G09 (#39): an on-demand creature is built only from choices code can verify in its article."""

import asyncio
import json

import httpx
import pytest

from app.models.stats import Ability, StatName
from app.providers.live.http import ProviderError
from app.research.lore import NONSENSE, UNAVAILABLE, article_text, heads_in_quote, lore_for
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


def test_a_missing_article_is_nonsense_and_asks_no_model() -> None:
    chat = FakeChat()
    assert run(chat, article=None) == NONSENSE and chat.calls == 0


def test_an_outage_gives_no_sheet_rather_than_a_guess() -> None:
    assert run(FakeChat(ProviderError("down"), ProviderError("down"))) == UNAVAILABLE
    assert run(FakeChat("not json", "still not json")) == UNAVAILABLE


def test_article_text_drops_scripts_styles_and_tags() -> None:
    text = article_text(ARTICLE)
    assert QUOTE in text and "var x" not in text and "color: red" not in text


def test_the_mock_chat_finds_nothing_so_mock_mode_blocks() -> None:
    from app.providers.mock.text import MockChatLLM

    assert run(MockChatLLM()) == NONSENSE
