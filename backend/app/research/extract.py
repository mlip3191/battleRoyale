"""G04 part 2: the chat model copies a stat's number and quote from evidence; code checks it.

The model never sets a number (CLAUDE.md §6). It points at a quote in one of the passages;
code accepts the value only if the quote is in that passage word for word, the number is in
the quote, the unit converts, and the result is within the sanity bounds. Anything else, and
any provider failure, means "nothing extracted", so the sheet falls back to the next level.
"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, ValidationError

from app.intake.llm_io import CALL_ERRORS, data_block
from app.models.stats import Confidence, Source, StatName, StatSheet, StatValue
from app.providers.base import ChatLLM, ChatMessage, Embedder, Reranker
from app.research.defaults import PHYSICAL_ORDER
from app.research.evidence_check import evidence_is_valid, number_has_unit_in_quote
from app.research.ranges import range_for, within_sanity_bounds
from app.research.retrieve import Passage, evidence_for
from app.research.statsheet import (
    RAM_WEAPONS,
    FighterProfile,
    build_stat_sheet,
    load_facts,
    stat_from_facts,
)
from app.research.units import STAT_UNITS, UnitError, to_stat_unit

logger = logging.getLogger(__name__)

PROMPT_NAME = "stat_extract"
PROMPT_PATH = Path(__file__).parents[2] / "prompts" / f"{PROMPT_NAME}.md"
ATTEMPTS = 2
# A quote longer than this holds too many numbers to pin one down; it is rejected.
MAX_QUOTE_CHARS = 300
# At most this many stats are extracted at once, so one sheet can't flood the providers.
PARALLEL_STATS = 3
# Hosts of the approved text sources in docs/research.md (Wikipedia, Wikidata, and the
# Hugging Face datasets); a passage from anywhere else is never quoted.
APPROVED_HOSTS = frozenset({"en.wikipedia.org", "www.wikidata.org", "huggingface.co"})
# Mega and giga symbols ("Mm", "Mg", "Gm") would be read as milli by the lowercase unit table.
LARGE_PREFIXES = ("M", "G")
# Stats a ramming machine always gets from the ram formula, so they are never extracted.
RAM_DERIVED = (StatName.ATTACK_FORCE, StatName.ATTACK_RATE)


class ExtractReply(BaseModel):
    """The model's answer: where the number is, or found false."""

    model_config = ConfigDict(extra="ignore", use_attribute_docstrings=True)

    found: bool
    """True when a passage states the stat in digits."""
    passage: int | None = None
    """Number of the passage the quote comes from, starting at 1."""
    value: float | None = None
    """The number exactly as the quote writes it, in the quote's unit."""
    unit: str | None = None
    """The unit as the quote writes it."""
    quote: str | None = None
    """The sentence holding the number, copied word for word."""


# The prompt template, read fresh so edits apply without a restart.
def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


# System prompt plus the fighter, the stat, and the numbered passages as one data block.
def build_messages(
    profile: FighterProfile, stat: StatName, passages: list[Passage]
) -> list[ChatMessage]:
    numbered = "\n\n".join(
        f"[{i}] {p.doc_title}{f' / {p.heading}' if p.heading else ''}\n{p.text}"
        for i, p in enumerate(passages, start=1)
    )
    request = f"Fighter: {profile.display_name}\nStat: {stat.value}\n\n{numbered}"
    return [
        {"role": "system", "content": load_prompt()},
        {"role": "user", "content": data_block(request)},
    ]


# Reply text -> an answer, or None when the reply isn't usable JSON.
def read_reply(reply: str) -> ExtractReply | None:
    text = reply.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        return ExtractReply.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError):
        return None


# Ask the model, trying twice when the call fails or the reply isn't JSON.
async def ask_model(
    chat: ChatLLM, profile: FighterProfile, stat: StatName, passages: list[Passage]
) -> ExtractReply | None:
    messages = build_messages(profile, stat, passages)
    schema = ExtractReply.model_json_schema()
    for _ in range(ATTEMPTS):
        try:
            reply = await chat.complete(messages, prompt_name=PROMPT_NAME, json_schema=schema)
        except CALL_ERRORS as error:
            logger.warning("Extraction call failed for %s (%s).", stat.value, type(error).__name__)
            continue
        answer = read_reply(reply)
        if answer is not None:
            return answer
    return None


# The model's answer as a stat value, or None when code can't verify it.
def verified_value(
    stat: StatName,
    answer: ExtractReply,
    passages: list[Passage],
    retrieved: dict[str, datetime],
) -> StatValue | None:
    if not answer.found:
        return None
    if answer.value is None or not answer.unit or not answer.quote or answer.passage is None:
        logger.warning("Rejected %s: the answer is missing a field.", stat.value)
        return None
    if not 1 <= answer.passage <= len(passages):
        logger.warning("Rejected %s: passage %s doesn't exist.", stat.value, answer.passage)
        return None
    if len(answer.quote) > MAX_QUOTE_CHARS:
        logger.warning("Rejected %s: the quote is over %s characters.", stat.value, MAX_QUOTE_CHARS)
        return None
    passage = passages[answer.passage - 1]
    if urlparse(passage.url).hostname not in APPROVED_HOSTS:
        logger.warning("Rejected %s: its page isn't from an approved source.", stat.value)
        return None
    if len(answer.unit) <= 3 and answer.unit.startswith(LARGE_PREFIXES) and len(answer.unit) > 1:
        logger.warning("Rejected %s: unit %r has a mega or giga prefix.", stat.value, answer.unit)
        return None
    if passage.url not in retrieved:
        logger.warning("Rejected %s: no fetch date stored for its page.", stat.value)
        return None
    if not evidence_is_valid(answer.value, answer.quote, passage.text):
        logger.warning("Rejected %s: number not in quote, or quote not in passage.", stat.value)
        return None
    if not number_has_unit_in_quote(answer.value, answer.unit, answer.quote):
        logger.warning(
            "Rejected %s: the quote doesn't give %r after the number.", stat.value, answer.unit
        )
        return None
    try:
        value = to_stat_unit(answer.value, answer.unit, stat)
    except UnitError:
        logger.warning("Rejected %s: unit %r doesn't convert.", stat.value, answer.unit)
        return None
    if not within_sanity_bounds(stat, value):
        return None
    low, high = range_for(stat, value, Confidence.MEDIUM)
    return StatValue(
        value=_sig(value),
        unit=STAT_UNITS[stat],
        source=Source(
            title=passage.doc_title,
            url=passage.url,
            quote=answer.quote,
            retrieved_at=retrieved[passage.url],
            license=passage.license,
        ),
        confidence=Confidence.MEDIUM,
        is_estimate=False,
        method="extracted",
        low=_sig(low),
        high=_sig(high),
        note=f"Copied by the chat model from the quote ({answer.value:g} {answer.unit}) and "
        f"checked by code, converted to {STAT_UNITS[stat]}. Range is the standard +/-25%.",
    )


# Keep `sig` significant figures, as the rest of the builder does.
def _sig(x: float, sig: int = 6) -> float:
    return float(f"{x:.{sig}g}")


# When each document was fetched, by URL, so the source date is the page's, not today's.
def fetch_dates(connection: sqlite3.Connection, fighter_id: str) -> dict[str, datetime]:
    rows = connection.execute(
        "SELECT url, retrieved_at FROM documents WHERE fighter_id = ?", (fighter_id,)
    ).fetchall()
    return {url: datetime.fromisoformat(when) for url, when in rows}


# One stat from the evidence, or None when nothing verifiable was found.
async def extract_stat(
    connection: sqlite3.Connection,
    providers: tuple[ChatLLM, Embedder, Reranker],
    profile: FighterProfile,
    stat: StatName,
) -> StatValue | None:
    chat, embedder, reranker = providers
    # Anything unexpected (a reply that isn't JSON, a bad stored URL or date, no knowledge base
    # yet) means nothing extracted for this stat, never a failed sheet.
    try:
        passages = await evidence_for(connection, embedder, reranker, profile.fighter_id, stat)
        if not passages:
            return None
        answer = await ask_model(chat, profile, stat, passages)
        if answer is None:
            return None
        return verified_value(stat, answer, passages, fetch_dates(connection, profile.fighter_id))
    except (*CALL_ERRORS, ValueError, sqlite3.Error) as error:
        logger.warning("Nothing extracted for %s (%s).", stat.value, type(error).__name__)
        return None


# The physical stats worth asking the model about: not filled by a stored fact, and not one a
# ramming machine gets from the ram formula.
def stats_to_extract(profile: FighterProfile, filled: set[StatName]) -> list[StatName]:
    rams = bool(RAM_WEAPONS & set(profile.weapons))
    return [
        stat for stat in PHYSICAL_ORDER if stat not in filled and not (rams and stat in RAM_DERIVED)
    ]


# A full sheet using stored facts and model extraction, then the builder's later levels.
async def build_sheet_with_evidence(
    connection: sqlite3.Connection,
    providers: tuple[ChatLLM, Embedder, Reranker],
    profile: FighterProfile,
) -> StatSheet:
    facts = load_facts(connection, profile.fighter_id)
    filled = {stat for stat in PHYSICAL_ORDER if stat_from_facts(stat, facts) is not None}
    wanted = stats_to_extract(profile, filled)
    limit = asyncio.Semaphore(PARALLEL_STATS)

    async def one(stat: StatName) -> StatValue | None:
        async with limit:
            return await extract_stat(connection, providers, profile, stat)

    values = await asyncio.gather(*(one(stat) for stat in wanted))
    extracted = {stat: value for stat, value in zip(wanted, values, strict=True) if value}
    return build_stat_sheet(profile, facts, lambda _profile, stat: extracted.get(stat))
