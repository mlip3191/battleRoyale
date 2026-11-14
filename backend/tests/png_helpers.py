"""Test helpers: write PNGs independently of app/media/png.py, with any row filter, and build
the kind of sprite the live image endpoint returns after the background edit, plus a
recording fake image provider."""

import struct
import zlib

import numpy as np

from app.media import png
from app.providers.live.http import ProviderError
from app.providers.mock.image import silhouette_png

SIGNATURE = b"\x89PNG\r\n\x1a\n"
KEY_MAGENTA = (215, 42, 145)  # about what the live edit paints (hand test: 205-225, 35-50, 130-160)
OUTLINE = (20, 20, 20)


def chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


# Apply one PNG row filter (spec section 9) to a row, given the row above.
def _filter_row(kind: int, line: list[int], prior: list[int], bpp: int) -> list[int]:
    out = []
    for i, x in enumerate(line):
        a = line[i - bpp] if i >= bpp else 0
        b = prior[i]
        c = prior[i - bpp] if i >= bpp else 0
        if kind == 0:
            predicted = 0
        elif kind == 1:
            predicted = a
        elif kind == 2:
            predicted = b
        elif kind == 3:
            predicted = (a + b) >> 1
        else:
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            predicted = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
        out.append((x - predicted) & 255)
    return out


# A PNG of pixels (height, width, 3 or 4), cycling through the given row filters.
def write_png(
    pixels: np.ndarray,
    filters: tuple[int, ...] = (0,),
    *,
    depth: int = 8,
    colour: int | None = None,
    interlace: int = 0,
    idat_parts: int = 1,
) -> bytes:
    height, width, channels = pixels.shape
    colour = colour if colour is not None else {3: 2, 4: 6}[channels]
    raw = bytearray()
    prior = [0] * (width * channels)
    for y in range(height):
        line = [int(v) for v in pixels[y].reshape(-1)]
        kind = filters[y % len(filters)]
        raw.append(kind)
        raw.extend(_filter_row(kind, line, prior, channels))
        prior = line
    data = zlib.compress(bytes(raw))
    step = -(-len(data) // idat_parts)
    idats = b"".join(chunk(b"IDAT", data[i : i + step]) for i in range(0, len(data), step))
    header = struct.pack(">IIBBBBB", width, height, depth, colour, 0, 0, interlace)
    return SIGNATURE + chunk(b"IHDR", header) + idats + chunk(b"IEND", b"")


# An RGB "edited sprite": noisy flat magenta background, a dark-outlined square in the middle
# whose inside is also magenta (the outline must stop the fill) with a green patch.
def keyed_sprite_pixels(size: int = 40, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.integers(-12, 13, size=(size, size, 3))
    pixels = np.clip(np.array(KEY_MAGENTA) + noise, 0, 255).astype(np.uint8)
    low, high = size // 4, size - size // 4
    pixels[low:high, low:high] = OUTLINE
    pixels[low + 2 : high - 2, low + 2 : high - 2] = KEY_MAGENTA
    middle = size // 2
    pixels[middle - 2 : middle + 2, middle - 2 : middle + 2] = (40, 200, 60)
    return pixels


def keyed_sprite_png(size: int = 40, seed: int = 7) -> bytes:
    return write_png(keyed_sprite_pixels(size, seed), filters=(0, 1, 2, 3, 4))


# What the fake provider "draws": an opaque RGB picture, like the live model returns.
DRAWN = write_png(png.decode(silhouette_png((90, 60, 30))).pixels[..., :3])


class FakeImages:
    """Records every call; returns a drawn picture, then an edit on flat magenta."""

    def __init__(self, *, fail: bool = False, edited: bytes | None = None) -> None:
        self.calls: list[tuple[str, str, tuple[int, int]]] = []
        self.fail = fail
        self.edited = edited

    async def generate(self, prompt: str, *, size: tuple[int, int] = (512, 512)) -> bytes:
        self.calls.append(("generate", prompt, size))
        if self.fail:
            raise ProviderError("Live 'image' call to /v1/images/generations failed: HTTP 503.")
        return DRAWN

    async def edit(self, image: bytes, prompt: str, *, size: tuple[int, int] = (512, 512)) -> bytes:
        self.calls.append(("edit", prompt, size))
        return self.edited if self.edited is not None else keyed_sprite_png()
