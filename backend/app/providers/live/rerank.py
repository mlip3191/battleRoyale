"""Live Reranker: /v1/rerank on the course reranking endpoint."""

from typing import TYPE_CHECKING

import httpx

from app.config import Settings
from app.providers.live.http import ProviderError, get_json, post_json

if TYPE_CHECKING:
    from app.providers.registry import ServiceConfig


class LiveReranker:
    """Scores how well each passage answers a query, in the passages' own order."""

    def __init__(
        self, config: "ServiceConfig", settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        self.config = config
        self.timeout_s = settings.provider_timeout_s
        self.client = client
        self._model = config.model

    # Return one relevance score per passage (higher is better), in input order.
    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        reply = await post_json(
            provider="reranker",
            base_url=self.config.base_url,
            path="/v1/rerank",
            api_key=self.config.api_key.get_secret_value(),
            payload={"model": await self._model_name(), "query": query, "documents": passages},
            timeout_s=self.timeout_s,
            client=self.client,
        )
        try:
            scores = {row["index"]: float(row["relevance_score"]) for row in reply["results"]}
        except (KeyError, TypeError, ValueError) as error:
            raise ProviderError(
                "Live 'reranker' reply had no results[].relevance_score."
            ) from error
        if sorted(scores) != list(range(len(passages))):
            raise ProviderError("Live 'reranker' reply did not score every passage once.")
        return [scores[index] for index in range(len(passages))]

    # The reranker has no model setting, so ask the endpoint once and remember the answer.
    async def _model_name(self) -> str:
        if not self._model:
            reply = await get_json(
                provider="reranker",
                base_url=self.config.base_url,
                path="/v1/models",
                api_key=self.config.api_key.get_secret_value(),
                timeout_s=self.timeout_s,
                client=self.client,
            )
            try:
                self._model = reply["data"][0]["id"]
            except (KeyError, IndexError, TypeError) as error:
                raise ProviderError("Live 'reranker' listed no model.") from error
        return self._model
