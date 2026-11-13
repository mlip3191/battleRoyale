"""Pre-draw and check every seed sprite and battlefield (A08); backend/scripts/pregen_sprites.py
is the command-line wrapper.

Pictures are cached per fighter_id (or terrain) and style version, so a second run draws nothing
new. Each sprite must be a PNG whose four corner pixels are transparent. Reports show only ids,
timings, sizes, and PASS/FAIL: never a URL, host, or key.
"""

import argparse
import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.media import images, png, style
from app.models.media import Asset
from app.models.stats import StatSheet
from app.models.terrain import Terrain
from app.providers.base import ImageGen
from app.providers.registry import ProviderConfigError, get_provider
from app.research.seed_fighters import (
    SEED_SHEETS_DIR,
    SeedFighter,
    find_seed_sheet,
    load_seed_fighters,
)
from app.research.statsheet import build_stat_sheet, profile_from_seed

SPRITE_THUMB = 128
BATTLEFIELD_THUMB_WIDTH = 192
CONTACT_COLUMNS = 6
CONTACT_GAP = 8
CONTACT_BACKGROUND = (238, 238, 238)


@dataclass(frozen=True)
class Row:
    """One picture's outcome for the table."""

    kind: str
    item_id: str
    seconds: float
    size_bytes: int
    problem: str | None
    """Why it failed; None means PASS."""
    path: Path | None


# A seed fighter's sheet: the hand-verified one if it exists, else built the way the app does
# (G04 build_stat_sheet, whose media_name is the display name in lowercase).
def seed_sheet(fighter: SeedFighter, sheets_dir: Path = SEED_SHEETS_DIR) -> StatSheet:
    return find_seed_sheet(fighter.id, sheets_dir=sheets_dir) or build_stat_sheet(
        profile_from_seed(fighter)
    )


# Why a picture file is unreadable, or None when it is a PNG this app can read.
def _read(path: Path) -> tuple[png.Image | None, str | None]:
    try:
        return png.decode(path.read_bytes()), None
    except OSError:
        return None, "file missing"
    except png.PngError as error:
        return None, f"not a readable PNG ({error})"


# Why a sprite file fails the check, or None when it is a PNG with four transparent corners.
def check_sprite(path: Path) -> str | None:
    image, problem = _read(path)
    if image is not None and not png.corners_transparent(image):
        return "corner pixels are not transparent"
    return problem


# Why a battlefield file fails the check (it must be a readable PNG), or None.
def check_battlefield(path: Path) -> str | None:
    return _read(path)[1]


# Draw (or reuse) one picture and check its file.
async def _one(
    kind: str,
    item_id: str,
    make: Callable[[], Awaitable[Asset]],
    check: Callable[[Path], str | None],
    media_dir: Path,
) -> Row:
    started = time.perf_counter()
    asset = await make()
    seconds = time.perf_counter() - started
    if asset.fallback:
        return Row(kind, item_id, seconds, 0, "generation failed (placeholder)", None)
    path = media_dir / asset.url.removeprefix("/media/")
    size = path.stat().st_size if path.is_file() else 0
    return Row(kind, item_id, seconds, size, check(path), path)


# Draw every seed sprite and every battlefield, one at a time, and check each file.
async def pregen(
    *,
    provider: ImageGen | None = None,
    media_dir: Path | None = None,
    force: bool = False,
    fighters: list[SeedFighter] | None = None,
) -> list[Row]:
    folder = media_dir or images.media_root()
    rows: list[Row] = []
    for fighter in load_seed_fighters() if fighters is None else fighters:
        try:
            sheet = seed_sheet(fighter)
        except ValueError as error:
            rows.append(Row("sprite", fighter.id, 0.0, 0, f"no stat sheet ({error})", None))
            continue

        def sprite(sheet: StatSheet = sheet) -> Awaitable[Asset]:
            return images.make_sprite(sheet, provider=provider, media_dir=folder, force=force)

        rows.append(await _one("sprite", fighter.id, sprite, check_sprite, folder))
    for terrain in Terrain:

        def field(terrain: Terrain = terrain) -> Awaitable[Asset]:
            return images.make_battlefield(
                terrain, provider=provider, media_dir=folder, force=force
            )

        rows.append(await _one("battlefield", terrain.value, field, check_battlefield, folder))
    return rows


# The PASS/FAIL table, then a list of failures.
def report(rows: list[Row]) -> str:
    lines = [f"{'kind':<12} {'id':<22} {'seconds':>8} {'KB':>7}  result"]
    for row in rows:
        result = "PASS" if row.problem is None else f"FAIL: {row.problem}"
        kb = f"{row.size_bytes / 1024:.1f}"
        lines.append(f"{row.kind:<12} {row.item_id:<22} {row.seconds:>8.1f} {kb:>7}  {result}")
    failures = [row for row in rows if row.problem is not None]
    lines.append(f"\n{len(rows) - len(failures)} passed, {len(failures)} failed")
    if failures:
        lines.append("Failures:")
        lines += [f"  - {row.kind} {row.item_id}: {row.problem}" for row in failures]
    return "\n".join(lines)


# Small thumbnails of every passing picture, plus one contact sheet of all the sprites.
def write_thumbs(rows: list[Row], out_dir: Path) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    sprites: list[png.Image] = []
    for row in rows:
        if row.problem is not None or row.path is None:
            continue
        image = png.decode(row.path.read_bytes())
        if row.kind == "sprite":
            thumb = png.resize_nearest(image, SPRITE_THUMB, SPRITE_THUMB)
            sprites.append(thumb)
        else:
            height = max(1, round(BATTLEFIELD_THUMB_WIDTH * image.height / image.width))
            thumb = png.resize_nearest(image, BATTLEFIELD_THUMB_WIDTH, height)
        (out_dir / f"{row.kind}-{row.item_id}.png").write_bytes(png.encode(thumb))
    if not sprites:
        return None
    path = out_dir / "contact-sheet.png"
    path.write_bytes(png.encode(contact_sheet(sprites)))
    return path


# The command: draw and check everything, print the table, and return 1 on any failure.
def main(argv: list[str] | None = None, *, media_dir: Path | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pregen_sprites.py",
        description="Draw and check a sprite for every seed fighter and every battlefield.",
    )
    parser.add_argument("--force", action="store_true", help="redraw even when cached")
    parser.add_argument("--thumbs", type=Path, help="write thumbnails and a contact sheet here")
    args = parser.parse_args(argv)
    settings = get_settings()
    print(f"Provider mode: {settings.provider_mode}; style {style.STYLE_VERSION}")
    try:
        provider = get_provider("image", settings)
    except ProviderConfigError as error:  # its message names settings, never values
        print(f"Image provider unavailable: {error}")
        return 1
    rows = asyncio.run(pregen(provider=provider, media_dir=media_dir, force=args.force))
    print(report(rows))
    if args.thumbs:
        sheet = write_thumbs(rows, args.thumbs)
        print(f"Thumbnails written to {args.thumbs}" + (f" ({sheet.name})" if sheet else ""))
    return 1 if any(row.problem is not None for row in rows) else 0


# Sprite thumbnails (all the same size) in a grid on a light background.
def contact_sheet(thumbs: list[png.Image]) -> png.Image:
    rows = -(-len(thumbs) // CONTACT_COLUMNS)
    columns = min(CONTACT_COLUMNS, len(thumbs))
    cell = SPRITE_THUMB + CONTACT_GAP
    canvas = np.empty((rows * cell + CONTACT_GAP, columns * cell + CONTACT_GAP, 4), np.uint8)
    canvas[..., :3] = CONTACT_BACKGROUND
    canvas[..., 3] = 255
    for index, thumb in enumerate(thumbs):
        top = CONTACT_GAP + (index // CONTACT_COLUMNS) * cell
        left = CONTACT_GAP + (index % CONTACT_COLUMNS) * cell
        flat = png.flatten(thumb, CONTACT_BACKGROUND)
        canvas[top : top + thumb.height, left : left + thumb.width] = flat.pixels
    return png.Image(canvas)
