"""Fighter sprites and battlefields (A08, pipeline step 6).

Prompts are built in code only: a sprite's from the stat sheet's media_name (checked by
app/safety/media_names.py) plus plain-word lore phrases mapped from the lore abilities enum, and
a battlefield's from the terrain enum. Never from display_name, the article title, the variant,
or anything the user typed. Every request uses the style lock in app/media/style.py.

A sprite is drawn, then edited onto a flat magenta background, which code keys out to real
transparency (app/media/png.py). Files are cached under <data_dir>/media/ per fighter_id (or
terrain) and STYLE_VERSION, so each is drawn once; a cache hit makes no provider call. Any
failure gives an Asset with fallback=True and url="" (the front end draws a placeholder) and
nothing is cached.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.config import get_settings
from app.media import png, style
from app.models.matchup import Matchup
from app.models.media import Asset
from app.models.stats import Ability, StatSheet
from app.models.terrain import Terrain
from app.providers.base import ImageGen
from app.providers.registry import get_provider
from app.safety.media_names import safe_media_name

logger = logging.getLogger(__name__)

ITEM_TIMEOUT_S = 50.0  # per picture, inside the images stage's 60 s budget
FIGHTER_ID = re.compile(r"[a-z0-9]+(?:-{1,2}[a-z0-9]+)*")  # "grizzly-bear", "bear--cub"

# Plain-word scenes for each terrain (the battlefield prompt's only variable part).
TERRAIN_SCENES: dict[Terrain, str] = {
    Terrain.ARENA: "a dusty round fighting arena with stone walls",
    Terrain.OPEN_FIELD: "an open grassy field under a blue sky",
    Terrain.FOREST: "a forest clearing between tall trees",
    Terrain.WATER: "open sea water with small waves",
    Terrain.SHORELINE: "a sandy beach where land meets the sea",
    Terrain.URBAN: "an empty city street with buildings",
    Terrain.MOUNTAIN: "a rocky mountain slope",
}
# What each legendary power looks like, in plain words, in a fixed order. Regeneration has no
# look, so it adds nothing; extra heads says how many when the sheet knows.
LORE_PHRASES: dict[Ability, str] = {
    Ability.FLIGHT: "with wings",
    Ability.BREATH_WEAPON: "breathing fire",
}


@dataclass(frozen=True)
class ImageRequest:
    """Everything that decides one picture: where it is cached and the full locked request."""

    kind: Literal["sprite", "battlefield"]
    asset_id: str
    path: Path
    """File path under the media folder, e.g. sprites/gray-wolf-v1.png."""
    prompt: str | None
    """None when no safe prompt can be built; such a picture is never requested."""
    size: tuple[int, int]
    edit_prompt: str | None = None

    # sha256 of the full locked request (prompt and every fixed parameter).
    @property
    def prompt_hash(self) -> str:
        if self.prompt is None:
            return ""
        request = {
            "style_version": style.STYLE_VERSION,
            "prompt": self.prompt,
            "edit_prompt": self.edit_prompt,
            "size": style.size_text(self.size),
            "seed": style.SEED,
            "negative_prompt": style.NEGATIVE_PROMPT,
        }
        text = json.dumps(request, sort_keys=True)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    # The asset for this picture: the cached file, or a placeholder when it failed.
    def asset(self, *, fallback: bool = False) -> Asset:
        url = "" if fallback else f"/media/{self.path.as_posix()}"
        return Asset(
            asset_id=self.asset_id,
            kind=self.kind,
            url=url,
            prompt_hash=self.prompt_hash,
            fallback=fallback,
        )


# The words describing a fighter: its safe media_name plus lore phrases, or None if unsafe.
def sprite_subject(sheet: StatSheet) -> str | None:
    name = safe_media_name(sheet.media_name)
    if name is None:
        return None
    phrases = []
    if sheet.lore is not None:
        abilities = set(sheet.lore.abilities)
        phrases = [phrase for power, phrase in LORE_PHRASES.items() if power in abilities]
        if Ability.EXTRA_HEADS in abilities:
            heads = sheet.lore.heads
            phrases.append(f"with {heads} heads" if heads else "with several heads")
    return ", ".join([name, *phrases]) if phrases else name


# The full sprite prompt from the style template, or None if the sheet's name is unsafe.
def sprite_prompt(sheet: StatSheet) -> str | None:
    subject = sprite_subject(sheet)
    if subject is None:
        return None
    article = "an" if subject[0] in "aeiou" else "a"
    return style.SPRITE_TEMPLATE.format(article=article, subject=subject)


# The battlefield prompt for a terrain, built from the enum only.
def battlefield_prompt(terrain: Terrain) -> str:
    return style.BATTLEFIELD_TEMPLATE.format(scene=TERRAIN_SCENES[Terrain(terrain)])


def sprite_request(sheet: StatSheet) -> ImageRequest:
    safe_id = FIGHTER_ID.fullmatch(sheet.fighter_id) is not None
    name = f"{sheet.fighter_id}-{style.STYLE_VERSION}"
    return ImageRequest(
        kind="sprite",
        asset_id=f"sprite-{name}",
        path=Path("sprites") / f"{name}.png",
        prompt=sprite_prompt(sheet) if safe_id else None,
        size=style.SPRITE_SIZE,
        edit_prompt=style.BACKGROUND_EDIT_PROMPT,
    )


def battlefield_request(terrain: Terrain) -> ImageRequest:
    name = f"{Terrain(terrain).value}-{style.STYLE_VERSION}"
    return ImageRequest(
        kind="battlefield",
        asset_id=f"battlefield-{name}",
        path=Path("battlefields") / f"{name}.png",
        prompt=battlefield_prompt(terrain),
        size=style.BATTLEFIELD_SIZE,
    )


# The folder generated media lives in.
def media_root() -> Path:
    return get_settings().data_dir / "media"


# A fighter's sprite: drawn, background removed, cached per fighter_id + STYLE_VERSION.
async def make_sprite(
    sheet: StatSheet,
    *,
    provider: ImageGen | None = None,
    media_dir: Path | None = None,
    force: bool = False,
) -> Asset:
    request = sprite_request(sheet)

    async def draw(images: ImageGen) -> bytes:
        assert request.prompt is not None and request.edit_prompt is not None
        drawn = await images.generate(request.prompt, size=request.size)
        keyed = await images.edit(drawn, request.edit_prompt, size=request.size)
        return await asyncio.to_thread(cut_out, keyed)

    return await _make(request, draw, provider, media_dir, force)


# A terrain's battlefield (no background removal), cached per terrain + STYLE_VERSION.
async def make_battlefield(
    terrain: Terrain,
    *,
    provider: ImageGen | None = None,
    media_dir: Path | None = None,
    force: bool = False,
) -> Asset:
    request = battlefield_request(terrain)

    async def draw(images: ImageGen) -> bytes:
        assert request.prompt is not None
        drawn = await images.generate(request.prompt, size=request.size)
        return await asyncio.to_thread(_recompress, drawn)

    return await _make(request, draw, provider, media_dir, force)


# One sprite per fighter (a mirror match draws it once) plus the battlefield; never raises.
async def make_images(
    matchup: Matchup,
    sheets: Sequence[StatSheet],
    *,
    provider: ImageGen | None = None,
    media_dir: Path | None = None,
    timeout_s: float = ITEM_TIMEOUT_S,
) -> list[Asset]:
    if provider is None:
        try:
            provider = get_provider("image")
        except Exception as error:  # live settings missing: cached files can still be used
            logger.warning("image provider unavailable (%s)", type(error).__name__)
    unique: dict[str, StatSheet] = {}
    for sheet in sheets:
        unique.setdefault(sheet.fighter_id, sheet)
    jobs: list[tuple[ImageRequest, Awaitable[Asset]]] = [
        (sprite_request(s), make_sprite(s, provider=provider, media_dir=media_dir))
        for s in unique.values()
    ]
    jobs.append(
        (
            battlefield_request(matchup.terrain),
            make_battlefield(matchup.terrain, provider=provider, media_dir=media_dir),
        )
    )
    return list(await asyncio.gather(*(_bounded(req, job, timeout_s) for req, job in jobs)))


# Run one picture within its time limit; anything going wrong gives its placeholder.
async def _bounded(request: ImageRequest, job: Awaitable[Asset], timeout_s: float) -> Asset:
    try:
        return await asyncio.wait_for(job, timeout_s)
    except Exception as error:
        logger.warning("image %s fell back (%s)", request.asset_id, type(error).__name__)
        return request.asset(fallback=True)


# The cached file if there is one, else draw it, save it, and return its asset.
async def _make(
    request: ImageRequest,
    draw: Callable[[ImageGen], Awaitable[bytes]],
    provider: ImageGen | None,
    media_dir: Path | None,
    force: bool,
) -> Asset:
    if request.prompt is None:
        logger.warning("image %s not drawn: its name is not safe for a prompt", request.asset_id)
        return request.asset(fallback=True)
    file = (media_dir or media_root()) / request.path
    if not force and file.is_file():
        return request.asset()
    try:
        data = await draw(provider or get_provider("image"))
        await asyncio.to_thread(_save, file, data)
    except Exception as error:
        logger.warning("image %s fell back (%s)", request.asset_id, type(error).__name__)
        return request.asset(fallback=True)
    return request.asset()


# Key out the flat background of an edited sprite; refuse a result that isn't a clean cut-out.
def cut_out(data: bytes) -> bytes:
    image = png.key_background(png.decode(data))
    if not png.corners_transparent(image):
        raise png.PngError("background was not removed at the corners")
    if not (image.pixels[..., 3] > 0).any():
        raise png.PngError("nothing was left after removing the background")
    return png.encode(image)


# Check a battlefield is a readable PNG and store it compressed.
def _recompress(data: bytes) -> bytes:
    return png.encode(png.decode(data))


# Write a file all at once, so a reader never sees half of it.
def _save(file: Path, data: bytes) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    partial = file.with_name(f".{file.name}.{uuid.uuid4().hex}.tmp")
    partial.write_bytes(data)
    os.replace(partial, file)
