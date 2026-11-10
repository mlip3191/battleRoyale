"""Live Embedder: OpenAI-compatible /v1/embeddings on the course embeddings endpoint."""

from typing import TYPE_CHECKING

import httpx

from app.config import Settings
from app.providers.live.http import ProviderError, post_json

if TYPE_CHECKING:
    from app.providers.registry import ServiceConfig

BATCH_SIZE = 64


class LiveEmbedder:
    """Embeds texts in batches and returns one vector per text, in the input order."""

    def __init__(
        self, config: "ServiceConfig", settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        self.config = config
        self.timeout_s = settings.provider_timeout_s
        self.client = client

    # Embed every text, one batch at a time.
    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            vectors += await self._embed_batch(texts[start : start + BATCH_SIZE])
        if len({len(vector) for vector in vectors}) > 1:
            raise ProviderError("Live 'embedder' returned vectors of different lengths.")
        return vectors

    # Embed one batch and put the vectors back in input order.
    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        reply = await post_json(
            provider="embedder",
            base_url=self.config.base_url,
            path="/v1/embeddings",
            api_key=self.config.api_key.get_secret_value(),
            payload={"model": self.config.model, "input": batch},
            timeout_s=self.timeout_s,
            client=self.client,
        )
        try:
            rows = sorted(reply["data"], key=lambda row: row["index"])
            indexes = [row["index"] for row in rows]
            vectors = [row["embedding"] for row in rows]
        except (KeyError, TypeError) as error:
            raise ProviderError("Live 'embedder' reply had no data[].embedding.") from error
        if len(vectors) != len(batch):
            raise ProviderError("Live 'embedder' reply had the wrong number of vectors.")
        if indexes != list(range(len(batch))):
            raise ProviderError("Live 'embedder' reply had unexpected indexes.")
        return vectors
