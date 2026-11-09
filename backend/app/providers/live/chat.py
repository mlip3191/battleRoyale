"""Live ChatLLM: OpenAI-compatible /v1/chat/completions on the course chat endpoint."""

from typing import TYPE_CHECKING, Any

import httpx

from app.config import Settings
from app.providers.base import ChatMessage
from app.providers.live.http import ProviderError, post_json

if TYPE_CHECKING:
    from app.providers.registry import ServiceConfig


class LiveChatLLM:
    """Calls the course chat model; json_schema turns on schema-constrained output."""

    def __init__(
        self, config: "ServiceConfig", settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        self.config = config
        self.timeout_s = settings.provider_timeout_s
        self.client = client

    # Send the messages and return the reply text.
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        prompt_name: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {"model": self.config.model, "messages": messages}
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": prompt_name, "schema": json_schema},
            }
        reply = await post_json(
            provider="chat",
            base_url=self.config.base_url,
            path="/v1/chat/completions",
            api_key=self.config.api_key.get_secret_value(),
            payload=payload,
            timeout_s=self.timeout_s,
            client=self.client,
        )
        try:
            content = reply["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("Live 'chat' reply had no choices[0].message.content.") from error
        if not isinstance(content, str):
            raise ProviderError("Live 'chat' reply content was not text.")
        return content
