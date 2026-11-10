"""#27 criterion 3: a blocked input makes zero calls to research, image or audio providers.

Every non-chat provider in the registry (embedder, reranker, doc parser, structured model,
image, TTS, music) is swapped for a counting stand-in. One input per blocked reason then goes
through parse_matchup and check_matchup, and every counter must stay at 0. The pipeline (A05)
does not exist yet, so this proves intake and the safety gate never reach those providers; A05
must call check_matchup before research. Wikidata is the mock fixture (PROVIDER_MODE=mock) with
its cache in the test's temp data folder (tests/conftest.py).
"""

import json
from collections import Counter
from collections.abc import Callable
from typing import Any

import pytest

from app.intake.parser import parse_matchup
from app.models.matchup import FighterRequest, Matchup
from app.providers import registry
from app.providers.base import ChatMessage
from app.safety import check_matchup
from app.safety.classify import PROMPT_NAME as SAFETY_PROMPT
from app.safety.verdict import BLOCKED_REASONS

# Providers a blocked request must never reach; chat is the only one intake and safety use.
WATCHED = ["embedder", "reranker", "doc_parser", "structured", "image", "tts", "music"]


class Counted:
    """Wraps a provider: every method call is counted (and still answered by the mock)."""

    def __init__(self, name: str, inner: object, counts: Counter[str]) -> None:
        self._name, self._inner, self._counts = name, inner, counts

    def __getattr__(self, attr: str) -> Any:
        value = getattr(self._inner, attr)
        if not callable(value):
            return value

        def counted(*args: Any, **kwargs: Any) -> Any:
            self._counts[f"{self._name}.{attr}"] += 1
            return value(*args, **kwargs)

        return counted


# Swap each watched provider in the registry for a counting stand-in; returns the counters.
@pytest.fixture
def counts(monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    found: Counter[str] = Counter()
    for name in WATCHED:

        def factory(name: str = name, make: Callable[[], object] = registry.MOCKS[name]) -> object:
            found[name] += 1  # asking the registry for the provider counts too
            return Counted(name, make(), found)

        monkeypatch.setitem(registry.MOCKS, name, factory)
    return found


class Chat:
    """Stand-in chat model: parse replies by text; the classifier blocks texts by keyword."""

    def __init__(self, parse: dict[str, Any], verdicts: dict[str, str]) -> None:
        self.parse, self.verdicts = parse, verdicts

    async def complete(self, messages: list[ChatMessage], *, prompt_name: str, **_: Any) -> str:
        if prompt_name == SAFETY_PROMPT:
            text = messages[1]["content"].lower()
            hits = [reason for word, reason in self.verdicts.items() if word in text]
            return json.dumps({"verdict": hits[0] if hits else "allowed"})
        return json.dumps(self.parse)


# One input per blocked reason, each against a goose: (raw, entity) of the first side, and the
# word the classifier stand-in blocks (None when the code rules or Wikidata decide). PG wording.
OTHER_SIDE = ("a goose", "goose")
CASES: dict[str, tuple[tuple[str, str], str | None]] = {
    "real_person": (("Napoleon", "napoleon"), None),
    "minor": (("a toddler", "toddler"), None),
    "sexual": (("a flirty duck", "duck"), "flirty"),
    "hate": (("the French", "french"), None),
    "self_harm": (("a gloomy duck", "duck"), "gloomy"),
    "copyrighted_character": (("Robo-Tron", "robo-tron"), None),
    "deity": (("Zeus", "zeus"), None),
    "weapon": (("a nuclear bomb", "nuclear bomb"), None),
    "out_of_scope": (("the Moon", "moon"), None),
    "nonsense": (("asdf", "asdf"), "asdf"),
    "other": (("a scheming duck", "duck"), "scheming"),
}


def test_every_blocked_reason_has_a_case() -> None:
    assert set(CASES) == set(BLOCKED_REASONS)


def test_the_counting_stand_ins_are_live(counts: Counter[str]) -> None:
    # Guards against a vacuous pass: asking the registry for a watched provider is counted.
    registry.get_provider("tts")
    assert counts["tts"] == 1


@pytest.mark.parametrize("reason", sorted(CASES))
async def test_a_blocked_input_reaches_no_research_image_or_audio_provider(
    reason: str, counts: Counter[str]
) -> None:
    first, keyword = CASES[reason]
    sides = [first, OTHER_SIDE]
    text = f"{first[0]} vs {OTHER_SIDE[0]}"
    parse = {"fighters": [{"raw": r, "entity": e, "variant": None} for r, e in sides]}
    chat = Chat(parse, {keyword: reason} if keyword else {})

    result = await parse_matchup(text, chat=chat, safety_chat=chat)
    assert (result.status, result.blocked_reason) == ("blocked", reason)

    fighters = [FighterRequest(raw=r, entity=e) for r, e in sides]
    verdict = await check_matchup(Matchup(fighters=fighters, raw_text=text), chat=chat)
    assert verdict.reason == reason

    assert sum(counts.values()) == 0, dict(counts)
