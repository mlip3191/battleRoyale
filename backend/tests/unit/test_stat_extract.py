"""G04 part 2: a model-copied number counts only when code finds it in a verified quote."""

import asyncio
import json
import logging
from datetime import UTC, datetime

import pytest

from app.models.stats import ASSUMABLE_STATS, StatName
from app.providers.live.http import ProviderError
from app.providers.mock.text import MockChatLLM
from app.research import extract
from app.research.evidence_check import number_has_unit_in_quote
from app.research.extract import (
    ExtractReply,
    ask_model,
    build_messages,
    stats_to_extract,
    verified_value,
)
from app.research.facts import Fact
from app.research.retrieve import Passage
from app.research.statsheet import FighterProfile, StoredFact, build_stat_sheet

WHEN = datetime(2026, 11, 12, tzinfo=UTC)
URL = "https://en.wikipedia.org/w/index.php?title=Cat&oldid=1"
CAT = FighterProfile("house-cat", "House cat", "house cat", "mammal", "living", "land", ("claws",))
DOZER = FighterProfile(
    "bulldozer", "Bulldozer", "bulldozer", "vehicle", "machine", "land", ("ramming", "crushing")
)
PASSAGES = [
    Passage(1, "Cat", URL, "CC BY-SA 4.0", "Size", "Cats are popular pets.", 0.1),
    Passage(
        2,
        "Cat",
        URL,
        "CC BY-SA 4.0",
        "Size",
        "Adult domestic cats typically weigh 4–5 kg (8.8–11.0 lb). They run at up to "
        "48 km/h and stand about 1.5 ft tall.",
        0.2,
    ),
]


# A model answer pointing at passage 2.
def answer(value: float, unit: str, quote: str, passage: int = 2) -> ExtractReply:
    return ExtractReply(found=True, passage=passage, value=value, unit=unit, quote=quote)


def check(stat: StatName, reply: ExtractReply):
    return verified_value(stat, reply, PASSAGES, {URL: WHEN})


def test_a_verified_quote_is_accepted_as_extracted() -> None:
    value = check(StatName.MASS, answer(5, "kg", "Adult domestic cats typically weigh 4–5 kg"))
    assert value is not None
    assert (value.value, value.method, value.is_estimate) == (5.0, "extracted", False)
    assert (value.low, value.high) == (3.75, 6.25)
    assert value.source is not None and value.source.retrieved_at == WHEN
    assert value.source.title == "Cat" and value.source.license == "CC BY-SA 4.0"


@pytest.mark.parametrize(
    ("stat", "number", "unit", "quote", "expected"),
    [
        (StatName.MASS, 11.0, "lb", "(8.8–11.0 lb)", 4.98952),
        (StatName.SPEED, 48, "km/h", "They run at up to 48 km/h", 13.3333),
        (StatName.SIZE, 1.5, "ft", "stand about 1.5 ft tall", 0.4572),
    ],
)
def test_units_convert_lb_km_h_and_ft(stat, number, unit, quote, expected) -> None:
    value = check(stat, answer(number, unit, quote))
    assert value is not None and value.value == pytest.approx(expected, rel=1e-5)


def test_a_number_not_in_the_quote_is_rejected(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        assert (
            check(StatName.MASS, answer(6, "kg", "Adult domestic cats typically weigh 4–5 kg"))
            is None
        )
    assert "number not in quote" in caplog.text


def test_a_quote_not_in_the_passage_is_rejected() -> None:
    assert check(StatName.MASS, answer(7, "kg", "Cats weigh 7 kg")) is None


def test_a_quote_from_another_passage_is_rejected() -> None:
    quote = "Adult domestic cats typically weigh 4–5 kg"
    assert check(StatName.MASS, answer(5, "kg", quote, passage=1)) is None
    assert check(StatName.MASS, answer(5, "kg", quote, passage=3)) is None


def test_not_found_and_missing_fields_give_nothing() -> None:
    assert check(StatName.MASS, ExtractReply(found=False)) is None
    assert check(StatName.MASS, ExtractReply(found=True, passage=2, value=5)) is None


def test_an_unknown_unit_is_rejected() -> None:
    assert check(StatName.MASS, answer(5, "stone", "typically weigh 4–5 kg")) is None


def test_a_value_outside_the_sanity_bounds_is_rejected(caplog) -> None:
    passages = [Passage(1, "Cat", URL, "CC BY-SA 4.0", None, "It runs at 5000 km/h.", 0.1)]
    reply = answer(5000, "km/h", "It runs at 5000 km/h.", passage=1)
    with caplog.at_level(logging.WARNING):
        assert verified_value(StatName.SPEED, reply, passages, {URL: WHEN}) is None
    assert "outside" in caplog.text


class FakeChat:
    """A chat stand-in: replies in order, raising any exception it is given."""

    def __init__(self, *replies) -> None:
        self.replies = list(replies)
        self.calls = 0

    async def complete(self, messages, *, prompt_name, json_schema=None) -> str:
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_the_model_is_retried_once_then_gives_up() -> None:
    good = json.dumps({"found": False})
    retried = FakeChat("not json", good)
    assert asyncio.run(ask_model(retried, CAT, StatName.MASS, PASSAGES)) == ExtractReply(
        found=False
    )
    down = FakeChat(ProviderError("down"), ProviderError("down"))
    assert asyncio.run(ask_model(down, CAT, StatName.MASS, PASSAGES)) is None
    assert down.calls == 2


def test_the_mock_chat_finds_nothing() -> None:
    assert asyncio.run(ask_model(MockChatLLM(), CAT, StatName.MASS, PASSAGES)) == ExtractReply(
        found=False
    )


def test_passages_are_numbered_inside_the_data_block() -> None:
    user = build_messages(CAT, StatName.MASS, PASSAGES)[1]["content"]
    assert user.startswith("<<<USER_INPUT>>>") and user.endswith("<<<END_USER_INPUT>>>")
    assert "Stat: mass_kg" in user and "[2] Cat / Size" in user


def test_behavioral_ram_and_already_filled_stats_are_not_extracted() -> None:
    cat_stats = stats_to_extract(CAT, {StatName.MASS})
    assert StatName.MASS not in cat_stats and not set(cat_stats) & ASSUMABLE_STATS
    assert len(cat_stats) == 6
    dozer_stats = stats_to_extract(DOZER, set())
    assert StatName.ATTACK_FORCE not in dozer_stats and StatName.ATTACK_RATE not in dozer_stats


def test_the_sheet_uses_facts_then_extraction_then_defaults(monkeypatch) -> None:
    fact = StoredFact(
        Fact("wikidata", "P2067", 4.0, "kg", "https://www.wikidata.org/wiki/Q146"), "CC0 1.0", WHEN
    )
    asked: list[StatName] = []

    async def fake_extract(connection, providers, profile, stat):
        asked.append(stat)
        return (
            check(stat, answer(48, "km/h", "They run at up to 48 km/h"))
            if stat == (StatName.SPEED)
            else None
        )

    monkeypatch.setattr(extract, "load_facts", lambda connection, fighter_id: [fact])
    monkeypatch.setattr(extract, "extract_stat", fake_extract)
    sheet = asyncio.run(extract.build_sheet_with_evidence(None, (None, None, None), CAT))
    assert StatName.MASS not in asked
    assert sheet.stats[StatName.MASS].value == 4.0
    assert sheet.stats[StatName.SPEED].method == "extracted"
    assert sheet.stats[StatName.ENDURANCE].method == "category_default"
    assert sheet == build_stat_sheet(
        CAT, [fact], lambda _p, s: sheet.stats[s] if s == StatName.SPEED else None
    )


def test_extract_stat_checks_the_model_against_the_evidence(monkeypatch) -> None:
    async def evidence(connection, embedder, reranker, fighter_id, stat):
        return PASSAGES

    monkeypatch.setattr(extract, "evidence_for", evidence)
    monkeypatch.setattr(extract, "fetch_dates", lambda connection, fighter_id: {URL: WHEN})
    honest = FakeChat(json.dumps(answer(5, "kg", "typically weigh 4–5 kg").model_dump()))
    value = asyncio.run(extract.extract_stat(None, (honest, None, None), CAT, StatName.MASS))
    assert value is not None and value.value == 5.0
    invented = FakeChat(json.dumps(answer(9, "kg", "typically weigh 9 kg").model_dump()))
    assert (
        asyncio.run(extract.extract_stat(None, (invented, None, None), CAT, StatName.MASS)) is None
    )


def test_an_evidence_outage_extracts_nothing(monkeypatch) -> None:
    async def outage(connection, embedder, reranker, fighter_id, stat):
        raise ProviderError("embedder down")

    monkeypatch.setattr(extract, "evidence_for", outage)
    chat = FakeChat()
    assert asyncio.run(extract.extract_stat(None, (chat, None, None), CAT, StatName.MASS)) is None
    assert chat.calls == 0


def test_the_unit_must_follow_the_number_in_the_quote(caplog) -> None:
    quote = "Adult domestic cats typically weigh 4–5 kg (8.8–11.0 lb)."
    with caplog.at_level(logging.WARNING):
        assert check(StatName.MASS, answer(8.8, "kg", quote)) is None  # 8.8 is in lb
    assert "after the number" in caplog.text
    low_end = check(StatName.MASS, answer(4, "kg", quote))  # "4–5 kg": the range's unit
    assert low_end is not None and low_end.value == 4.0
    assert (
        check(
            StatName.SPEED,
            answer(1.5, "km/h", "They run at up to 48 km/h and stand about 1.5 ft tall"),
        )
        is None
    )


@pytest.mark.parametrize(
    ("number", "unit", "quote", "ok"),
    [
        (13, "minutes", "for up to 13 minutes", True),
        (13, "minute", "for up to 13 minutes", True),
        (5, "kg", "weighs 4 to 5 kg", True),
        (4, "kg", "weighs 4 to 5 kg", True),
        (1593.8, "Newtons", "a bite force of 1593.8 Newtons (162.5 kgf)", True),
        (162.5, "N", "a bite force of 1593.8 Newtons (162.5 kgf)", False),
        (5, "m", "about 5 mm long", False),
        (5, "", "about 5 kg", False),
    ],
)
def test_number_has_unit_in_quote(number, unit, quote, ok) -> None:
    assert number_has_unit_in_quote(number, unit, quote) is ok


@pytest.mark.parametrize(
    ("passage", "value", "quote"),
    [
        ("It weighs 15 kg.", 5, "5 kg"),
        ("It weighs 0.5 kg.", 5, "5 kg"),
        ("It weighs 1,200 kg.", 200, "200 kg"),
        ("It holds on for 5 seconds.", 5, "5 s"),
    ],
)
def test_a_quote_cut_out_of_a_bigger_number_or_word_is_rejected(passage, value, quote) -> None:
    passages = [Passage(1, "Cat", URL, "CC BY-SA 4.0", None, passage, 0.1)]
    stat = StatName.ENDURANCE if quote.endswith(" s") else StatName.MASS
    reply = answer(value, quote.split(" ")[1], quote, passage=1)
    assert verified_value(stat, reply, passages, {URL: WHEN}) is None


@pytest.mark.parametrize(
    ("number", "unit", "quote"),
    [
        (5, "m", "it swims at 5 m/s"),
        (5, "kg", "a load of 5 kg/m"),
        (5, "in", "about 5 in the wild"),
        (5, "mm", "about 5 Mm across"),
    ],
)
def test_a_unit_running_into_another_is_rejected(number, unit, quote) -> None:
    assert not number_has_unit_in_quote(number, unit, quote)


def test_real_units_still_match_after_tightening() -> None:
    assert number_has_unit_in_quote(12, "in", "about 12 in (30 cm) long")
    assert number_has_unit_in_quote(5, "kg", "weighs 4–5 kg.")
    assert number_has_unit_in_quote(5, "m/s", "runs at 5 m/s")
    assert number_has_unit_in_quote(13, "Minutes", "for up to 13 minutes")


def test_unexpected_errors_extract_nothing(monkeypatch) -> None:
    async def evidence(connection, embedder, reranker, fighter_id, stat):
        return PASSAGES

    monkeypatch.setattr(extract, "evidence_for", evidence)
    not_json = FakeChat(ValueError("200 reply that isn't JSON"))
    assert (
        asyncio.run(extract.extract_stat(None, (not_json, None, None), CAT, StatName.MASS)) is None
    )

    async def broken(connection, embedder, reranker, fighter_id, stat):
        raise ValueError("embedder reply isn't JSON")

    monkeypatch.setattr(extract, "evidence_for", broken)
    assert (
        asyncio.run(extract.extract_stat(None, (FakeChat(), None, None), CAT, StatName.MASS))
        is None
    )


def test_a_page_with_no_fetch_date_or_a_huge_quote_is_rejected() -> None:
    quote = "typically weigh 4–5 kg"
    assert verified_value(StatName.MASS, answer(5, "kg", quote), PASSAGES, {}) is None
    long_passage = "x " * 200 + quote
    passages = [Passage(1, "Cat", URL, "CC BY-SA 4.0", None, long_passage, 0.1)]
    reply = answer(5, "kg", long_passage, passage=1)
    assert verified_value(StatName.MASS, reply, passages, {URL: WHEN}) is None
