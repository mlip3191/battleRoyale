"""#522 part 4: research prefers figures for the fighter's variant (sex and age)."""

import asyncio
from datetime import UTC, datetime

from app.models.stats import StatName
from app.research import extract
from app.research.extract import ExtractReply, build_messages
from app.research.facts import wikidata_facts
from app.research.retrieve import Passage
from app.research.statsheet import FighterProfile, StoredFact, stat_from_facts
from app.research.variant import described, prefer_variant

WHEN = datetime(2026, 11, 25, tzinfo=UTC)
URL = "https://en.wikipedia.org/w/index.php?title=Lion&oldid=1"
LION = FighterProfile(
    "african-lion", "African lion", "african lion", "mammal", "living", "land", (), "Adult male"
)
MALE, FEMALE, ADULT, BIRTH = "Q44148", "Q43445", "Q78101716", "Q4128476"


# A Wikidata mass statement in kg with sex and role qualifiers, as the entity JSON gives them.
def claim(n: int, amount: str, *items: tuple[str, str]) -> dict:
    qualifiers: dict = {}
    for prop, item in items:
        qualifiers.setdefault(prop, []).append({"datavalue": {"value": {"id": item}}})
    value = {"amount": amount, "unit": "http://www.wikidata.org/entity/Q11570"}
    mainsnak = {"datavalue": {"value": value}}
    return {"id": f"Q140${n}", "rank": "normal", "qualifiers": qualifiers, "mainsnak": mainsnak}


# The lion's three Wikidata masses: a birth weight, the males' and the females'.
LION_ENTITY = {
    "id": "Q140",
    "claims": {
        "P2067": [
            claim(1, "+1.65", ("P3831", BIRTH)),
            claim(2, "+188", ("P21", MALE), ("P3831", ADULT)),
            claim(3, "+126", ("P21", FEMALE), ("P3831", ADULT)),
        ]
    },
}


def lion_mass(variant: str | None) -> float | None:
    facts = [StoredFact(f, "CC0 1.0", WHEN) for f in wikidata_facts(LION_ENTITY)]
    value = stat_from_facts(StatName.MASS, facts, variant)
    return None if value is None else value.value


def test_wikidata_qualifiers_go_into_the_quote() -> None:
    quotes = [fact.quote for fact in wikidata_facts(LION_ENTITY)]
    assert quotes == [
        "mass: 1.65 kg (birth weight)",
        "mass: 188 kg (male organism, adult weight)",
        "mass: 126 kg (female organism, adult weight)",
    ]


def test_the_lions_mass_is_the_males_for_an_adult_male() -> None:
    assert lion_mass("Adult male") == 188.0
    assert lion_mass("Adult female") == 126.0
    assert lion_mass(None) == 126.0  # no variant: the middle figure, as before


def test_another_sex_is_used_only_when_nothing_else_is_left() -> None:
    bite = [("A lioness has a bite force of 1593.8 Newtons", "")]
    assert prefer_variant("Adult male", bite, lambda item: item) == bite
    newborn = [("mass: 1.65 kg (birth weight)", "")]
    assert prefer_variant("Adult male", newborn, lambda item: item) == []  # never for an adult
    assert prefer_variant("Mature plant", newborn, lambda item: item) == newborn


def test_a_quote_without_sex_words_takes_the_nearest_one_before_it() -> None:
    passage = "Males weigh 150–250 kg and females 120–182 kg. Cubs weigh 1.65 kg."
    assert described("150–250 kg", passage) == {"male"}
    assert described("120–182 kg", passage) == {"female"}
    assert described("1.65 kg", passage) == {"young"}
    assert described("adult males weigh 190 kg") == {"male", "adult"}


# Extract the lion's mass from one passage, with the model answering this value and quote.
def extract_lion_mass(monkeypatch, value: float, quote: str) -> float | None:
    text = "Males weigh 150–250 kg and females 120–182 kg. Cubs weigh 1.65 kg at birth."
    passages = [Passage(1, "Lion", URL, "CC BY-SA 4.0", None, text, 0.1)]

    async def evidence(connection, embedder, reranker, fighter_id, stat):
        return passages

    reply = ExtractReply(found=True, passage=1, value=value, unit="kg", quote=quote)

    class Chat:
        async def complete(self, messages, *, prompt_name, json_schema=None) -> str:
            assert "Variant: Adult male" in messages[1]["content"]
            return reply.model_dump_json()

    monkeypatch.setattr(extract, "evidence_for", evidence)
    monkeypatch.setattr(extract, "fetch_dates", lambda connection, fighter_id: {URL: WHEN})
    found = asyncio.run(extract.extract_stat(None, (Chat(), None, None), LION, StatName.MASS))
    return None if found is None else found.value


def test_extraction_names_the_variant_and_never_takes_a_young_animals_figure(monkeypatch) -> None:
    assert extract_lion_mass(monkeypatch, 250, "150–250 kg") == 250.0  # the males'
    assert extract_lion_mass(monkeypatch, 1.65, "1.65 kg") is None  # the cubs': rejected
    # One answer leaves nothing to prefer, so the females' figure still beats a default.
    assert extract_lion_mass(monkeypatch, 182, "120–182 kg") == 182.0


def test_species_names_are_not_sex_words() -> None:
    assert described("Bull sharks weigh up to 230 kg") == set()
    assert described("A wild boar weighs up to 100 kg") == set()
    assert described("Sea cows weigh about 400 kg") == set()
    assert described("the pit bull weighs 30 kg") == set()
    assert described("bull elephants weigh 6,000 kg") == {"male"}  # a bull is still a male
    sharks = [("bull sharks weigh 230 kg", ""), ("females weigh 180 kg", "")]
    assert prefer_variant("Adult female", sharks, lambda item: item) == sharks


def test_no_variant_line_without_a_variant() -> None:
    plain = FighterProfile("lion", "Lion", "lion", "mammal", "living", "land", ())
    assert "Variant:" not in build_messages(plain, StatName.MASS, [])[1]["content"]
