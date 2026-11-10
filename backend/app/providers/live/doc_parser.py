"""Live DocParser: turns fetched HTML into plain text on the course document parsing endpoint."""

import re
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from app.config import Settings
from app.providers.live.http import ProviderError, get_json, post_json

if TYPE_CHECKING:
    from app.providers.registry import ServiceConfig

PROMPT_PATH = Path(__file__).parents[3] / "prompts" / "doc-parse-html.md"
# Converting a long page piece takes far longer than a normal call, so it has its own limit.
PARSE_TIMEOUT_S = 120.0
PIECE_CHARS = 12_000
MAX_TOKENS = 6_000
PLAIN_TYPES = {"text/plain", "application/json", "application/xml"}
DROPPED_BLOCKS = re.compile(r"<(script|style)\b.*?</\1>|<!--.*?-->", re.DOTALL | re.IGNORECASE)
TAG_ATTRIBUTES = re.compile(r"<(/?[a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")


# Remove scripts, styles, comments, and tag attributes, which hold no article text.
def strip_markup(html: str) -> str:
    return TAG_ATTRIBUTES.sub(r"<\1>", DROPPED_BLOCKS.sub("", html))


# Split text into pieces of at most limit characters, ending on a tag where possible.
def split_pieces(text: str, limit: int = PIECE_CHARS) -> list[str]:
    pieces: list[str] = []
    while len(text) > limit:
        cut = text.rfind(">", 0, limit) + 1 or limit
        pieces.append(text[:cut])
        text = text[cut:]
    return [*pieces, text] if text else pieces


class LiveDocParser:
    """Sends HTML through the course parser piece by piece; plain text skips parsing."""

    def __init__(
        self, config: "ServiceConfig", settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:  # settings is unused here, but the registry passes it to every live adapter
        self.config = config
        self.client = client
        self._model = config.model
        self._instruction = PROMPT_PATH.read_text(encoding="utf-8").strip()

    # Return the document's plain text.
    async def parse(self, data: bytes, mime: str) -> str:
        kind = mime.split(";")[0].strip().lower()
        if kind in PLAIN_TYPES:
            return data.decode("utf-8", errors="replace")
        if kind != "text/html":
            raise ProviderError(f"Live 'doc_parser' cannot read {kind} documents yet.")
        pieces = split_pieces(strip_markup(data.decode("utf-8", errors="replace")))
        return "\n".join([await self._parse_piece(piece) for piece in pieces])

    # Convert one piece, refusing a cut-off reply so no text is silently lost.
    async def _parse_piece(self, piece: str) -> str:
        document = piece.replace("</document>", "")  # the page cannot close the data block
        content = f"{self._instruction}\n\n<document>\n{document}\n</document>"
        reply = await post_json(
            provider="doc_parser",
            base_url=self.config.base_url,
            path="/v1/chat/completions",
            api_key=self.config.api_key.get_secret_value(),
            payload={
                "model": await self._model_name(),
                "messages": [{"role": "user", "content": content}],
                "temperature": 0,
                "max_tokens": MAX_TOKENS,
            },
            timeout_s=PARSE_TIMEOUT_S,
            client=self.client,
        )
        try:
            choice = reply["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("Live 'doc_parser' reply had no message content.") from error
        if choice.get("finish_reason") == "length":
            raise ProviderError("Live 'doc_parser' reply was cut off at the token limit.")
        if not isinstance(text, str):
            raise ProviderError("Live 'doc_parser' reply content was not text.")
        return text

    # The parser has no model setting, so ask the endpoint once and remember the answer.
    async def _model_name(self) -> str:
        if not self._model:
            reply = await get_json(
                provider="doc_parser",
                base_url=self.config.base_url,
                path="/v1/models",
                api_key=self.config.api_key.get_secret_value(),
                timeout_s=PARSE_TIMEOUT_S,
                client=self.client,
            )
            try:
                self._model = reply["data"][0]["id"]
            except (KeyError, IndexError, TypeError) as error:
                raise ProviderError("Live 'doc_parser' listed no model.") from error
        return self._model
