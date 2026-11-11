"""Find the best few evidence passages for one fighter and one stat."""

import logging
import sqlite3
from dataclasses import dataclass

import httpx
import sqlite_vec

from app.models.stats import ASSUMABLE_STATS, StatName
from app.providers.base import Embedder, Reranker
from app.providers.live.http import ProviderError

logger = logging.getLogger(__name__)

TOP_N = 5
CANDIDATES = 20

# A search phrase per physical stat, worded the way articles usually state it.
STAT_QUERIES: dict[StatName, str] = {
    StatName.MASS: "adult body mass weight kg lb weighs",
    StatName.SIZE: "body length height at the shoulder cm m long tall",
    StatName.SPEED: "top running swimming flying speed km/h mph fast",
    StatName.ATTACK_FORCE: "bite force strike kick strength newtons",
    StatName.ATTACK_RATE: "attacks per second strikes bites rate of attack",
    StatName.REACH: "reach length of horns tusks claws weapon arm",
    StatName.ENDURANCE: "stamina endurance how long can sustain minutes hours",
}


@dataclass(frozen=True)
class Passage:
    """One piece of evidence and the document it came from."""

    chunk_id: int
    doc_title: str
    url: str
    license: str
    heading: str | None
    text: str
    distance: float


# The fighter's passages closest to the query, nearest first.
async def retrieve(
    connection: sqlite3.Connection,
    embedder: Embedder,
    fighter_id: str,
    query: str,
    k: int = CANDIDATES,
) -> list[Passage]:
    vector = sqlite_vec.serialize_float32((await embedder.embed([query]))[0])
    rows = connection.execute(
        "SELECT c.chunk_id, d.title, d.url, d.license, c.heading, c.text, "
        "vec_distance_cosine(v.embedding, ?) AS distance "
        "FROM chunks AS c JOIN documents AS d ON d.doc_id = c.doc_id "
        "JOIN chunks_vec AS v ON v.chunk_id = c.chunk_id "
        "WHERE d.fighter_id = ? ORDER BY distance, c.chunk_id LIMIT ?",
        (vector, fighter_id, k),
    ).fetchall()
    return [Passage(*row) for row in rows]


# Reorder passages by relevance; if the reranker fails, keep vector order and log a note.
async def rerank(
    reranker: Reranker, query: str, passages: list[Passage], top_n: int = TOP_N
) -> list[Passage]:
    if not passages:
        return []
    try:
        scores = await reranker.rerank(query, [passage.text for passage in passages])
        if len(scores) != len(passages):
            raise ProviderError("reranker returned the wrong number of scores")
    except (ProviderError, httpx.HTTPError, ValueError) as error:  # ValueError: reply not JSON
        logger.warning("Reranker unavailable (%s); kept vector order.", type(error).__name__)
        return passages[:top_n]
    order = sorted(range(len(passages)), key=lambda i: (-scores[i], i))
    return [passages[i] for i in order[:top_n]]


# The best few passages for one physical stat of one fighter.
async def evidence_for(
    connection: sqlite3.Connection,
    embedder: Embedder,
    reranker: Reranker,
    fighter_id: str,
    stat: StatName,
) -> list[Passage]:
    if stat in ASSUMABLE_STATS:
        raise ValueError(f"{stat} is a behavioral stat; it is never extracted from evidence")
    query = STAT_QUERIES[stat]
    candidates = await retrieve(connection, embedder, fighter_id, query)
    return await rerank(reranker, query, candidates)
