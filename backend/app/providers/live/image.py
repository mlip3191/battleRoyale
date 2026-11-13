"""Live ImageGen: /v1/images/generations and /v1/images/edits on the course image endpoint.

Every call sends the style lock from app/media/style.py (fixed seed and negative prompt), so the
same prompt and size always give the same picture. Generate is a JSON request; edit is
multipart/form-data with the PNG in the "image" part (docs/providers.md).
"""

import base64
import binascii
from typing import TYPE_CHECKING, Any

import httpx

from app.config import Settings
from app.media.style import NEGATIVE_PROMPT, SEED, size_text
from app.providers.live.http import ProviderError, get_json, post_json, post_multipart

if TYPE_CHECKING:
    from app.providers.registry import ServiceConfig

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class LiveImageGen:
    """Draws and edits PNGs with the locked seed and negative prompt."""

    def __init__(
        self, config: "ServiceConfig", settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        self.config = config
        self.timeout_s = settings.provider_timeout_s
        self.client = client
        self._model = config.model

    # Return PNG bytes for prompt at size (width, height).
    async def generate(self, prompt: str, *, size: tuple[int, int] = (512, 512)) -> bytes:
        payload: dict[str, Any] = {"model": await self._model_name(), "prompt": prompt}
        payload |= _locked(size)
        reply = await post_json(
            provider="image",
            base_url=self.config.base_url,
            path="/v1/images/generations",
            api_key=self.config.api_key.get_secret_value(),
            payload=payload,
            timeout_s=self.timeout_s,
            client=self.client,
        )
        return _png_from(reply)

    # Return PNG bytes of image changed as prompt describes (multipart upload).
    async def edit(self, image: bytes, prompt: str, *, size: tuple[int, int] = (512, 512)) -> bytes:
        fields = {"model": await self._model_name(), "prompt": prompt}
        fields |= {key: str(value) for key, value in _locked(size).items()}
        reply = await post_multipart(
            provider="image",
            base_url=self.config.base_url,
            path="/v1/images/edits",
            api_key=self.config.api_key.get_secret_value(),
            fields=fields,
            files={"image": ("image.png", image, "image/png")},
            timeout_s=self.timeout_s,
            client=self.client,
        )
        return _png_from(reply)

    # The image endpoint has no model setting, so ask it once and remember the answer.
    async def _model_name(self) -> str:
        if not self._model:
            reply = await get_json(
                provider="image",
                base_url=self.config.base_url,
                path="/v1/models",
                api_key=self.config.api_key.get_secret_value(),
                timeout_s=self.timeout_s,
                client=self.client,
            )
            try:
                self._model = reply["data"][0]["id"]
            except (KeyError, IndexError, TypeError) as error:
                raise ProviderError("Live 'image' listed no model.") from error
        return self._model


# The request fields every call sends unchanged (the style lock), apart from the size.
def _locked(size: tuple[int, int]) -> dict[str, Any]:
    return {
        "size": size_text(size),
        "n": 1,
        "seed": SEED,
        "negative_prompt": NEGATIVE_PROMPT,
        "output_format": "png",
        "response_format": "b64_json",
    }


# The first image of a reply, as PNG bytes.
def _png_from(reply: Any) -> bytes:
    try:
        data = base64.b64decode(reply["data"][0]["b64_json"], validate=True)
    except (KeyError, IndexError, TypeError, binascii.Error) as error:
        raise ProviderError("Live 'image' reply had no data[0].b64_json image.") from error
    if not data.startswith(PNG_SIGNATURE):
        raise ProviderError("Live 'image' reply was not a PNG.")
    return data
