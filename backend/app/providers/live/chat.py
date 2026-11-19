"""Live ChatLLM: OpenAI-compatible /v1/chat/completions on the course chat endpoint."""

import logging
from typing import TYPE_CHECKING, Any

import httpx

from app.config import Settings
from app.providers.base import ChatMessage
from app.providers.live.http import RETRIES, ProviderError, post_json

if TYPE_CHECKING:
    from app.providers.registry import ServiceConfig

logger = logging.getLogger(__name__)
THINKING_SWITCH = "chat_template_kwargs"
# Statuses a server gives for a request field it doesn't accept.
REFUSED_FIELD = {400, 422}


class LiveChatLLM:
    """Calls the course chat model; json_schema turns on schema-constrained output.

    timeout_s and retries default to the shared provider settings; intake passes shorter ones.
    thinking=False asks the model to answer without its hidden reasoning step (the script writer
    uses it: the step was 85-95% of a script reply and took 15-47 s against an 8 s limit, #363)."""

    def __init__(
        self,
        config: "ServiceConfig",
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        *,
        timeout_s: float | None = None,
        retries: int = RETRIES,
        thinking: bool = True,
    ) -> None:
        self.config = config
        self.timeout_s = settings.provider_timeout_s if timeout_s is None else timeout_s
        self.retries = retries
        self.client = client
        self.thinking = thinking

    # Send the messages and return the reply text.
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        prompt_name: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {"model": self.config.model, "messages": messages}
        if not self.thinking:
            # The served model's chat template switch; a template without it ignores the key.
            payload[THINKING_SWITCH] = {"enable_thinking": False}
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": prompt_name, "schema": json_schema},
            }
        try:
            reply = await self._post(payload)
        except ProviderError as error:
            if THINKING_SWITCH not in payload or error.status not in REFUSED_FIELD:
                raise
            # A served model whose server refuses the switch: ask once more without it, so a
            # model swap can't silence the commentary (#398 review).
            logger.warning("chat: the thinking switch was refused (%s); retrying without it", error)
            payload.pop(THINKING_SWITCH)
            reply = await self._post(payload)
        try:
            content = reply["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("Live 'chat' reply had no choices[0].message.content.") from error
        if not isinstance(content, str):
            raise ProviderError("Live 'chat' reply content was not text.")
        return content

    # One POST to the chat endpoint, with the shared timeout and retries.
    async def _post(self, payload: dict[str, Any]) -> Any:
        return await post_json(
            provider="chat",
            base_url=self.config.base_url,
            path="/v1/chat/completions",
            api_key=self.config.api_key.get_secret_value(),
            payload=payload,
            timeout_s=self.timeout_s,
            client=self.client,
            retries=self.retries,
        )
