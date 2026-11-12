"""A small PNG helper (no Pillow): decode, encode, key out a flat background, check corners.

Decodes non-interlaced 8-bit PNGs of colour type 2 (RGB) and 6 (RGBA), all five row filters,
which covers what the image endpoint and the mock return. Images are always handed around as
RGBA numpy arrays of shape (height, width, 4). Encoding writes compressed RGBA PNGs.
"""

import struct
import zlib
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_PIXELS = 4096 * 4096  # refuse anything bigger, so a bad reply can't eat the memory
CHANNELS = {2: 3, 6: 4}  # colour type -> bytes per pixel at bit depth 8
# How far (largest channel difference, 0-255) a pixel may be from the sampled key colour and
# still count as background. The hand test's magenta varied by about 20 per channel; the dark
# outline around a sprite is far outside this, so the fill stops there.
KEY_TOLERANCE = 64

Pixels = NDArray[np.uint8]


class PngError(ValueError):
    """The bytes are not a PNG this helper can read."""


@dataclass(frozen=True)
class Image:
    """An RGBA image: pixels has shape (height, width, 4)."""

    pixels: Pixels

    @property
    def width(self) -> int:
        return int(self.pixels.shape[1])

    @property
    def height(self) -> int:
        return int(self.pixels.shape[0])


# Split a PNG into its chunks, checking each CRC.
def _chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(SIGNATURE):
        raise PngError("not a PNG (bad signature)")
    found, pos = [], len(SIGNATURE)
    while pos + 12 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        if pos + 12 + length > len(data):
            raise PngError("PNG ends inside a chunk")
        kind = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length : pos + 12 + length])
        if zlib.crc32(kind + body) != crc:
            raise PngError(f"damaged {kind!r} chunk")
        found.append((kind, body))
        pos += 12 + length
        if kind == b"IEND":
            return found
    raise PngError("PNG ends before IEND")


# Decode PNG bytes into an RGBA image.
def decode(data: bytes) -> Image:
    chunks = _chunks(data)
    if not chunks or chunks[0][0] != b"IHDR" or len(chunks[0][1]) != 13:
        raise PngError("PNG has no header")
    width, height, depth, colour, compression, method, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1]
    )
    if depth != 8 or colour not in CHANNELS or compression or method or interlace:
        raise PngError(
            f"unsupported PNG (depth {depth}, colour type {colour}, interlace {interlace})"
        )
    if not 0 < width * height <= MAX_PIXELS:
        raise PngError(f"unsupported PNG size {width}x{height}")
    channels = CHANNELS[colour]
    stride = width * channels
    expected = height * (stride + 1)
    compressed = b"".join(body for kind, body in chunks if kind == b"IDAT")
    try:
        raw = zlib.decompressobj().decompress(compressed, expected)
    except zlib.error as error:
        raise PngError("PNG image data is damaged") from error
    if len(raw) < expected:
        raise PngError("PNG image data is too short")
    rows = np.frombuffer(raw, dtype=np.uint8).reshape(height, stride + 1)
    flat = _unfilter(rows, width, channels)
    pixels = flat.reshape(height, width, channels)
    if channels == 3:
        alpha = np.full((height, width, 1), 255, dtype=np.uint8)
        pixels = np.concatenate([pixels, alpha], axis=2)
    return Image(np.ascontiguousarray(pixels))


# Undo the per-row filters (PNG spec section 9): None, Sub, Up, Average, Paeth.
def _unfilter(rows: Pixels, width: int, bpp: int) -> Pixels:
    height, stride = rows.shape[0], rows.shape[1] - 1
    out = np.zeros((height, stride), dtype=np.uint8)
    prior = np.zeros(stride, dtype=np.uint8)
    for y in range(height):
        kind, line = int(rows[y, 0]), rows[y, 1:]
        if kind == 0:
            current = line.copy()
        elif kind == 1:  # Sub: running sum along each channel, wrapping at 256
            current = line.reshape(width, bpp).cumsum(axis=0, dtype=np.uint8).reshape(stride)
        elif kind == 2:  # Up
            current = line + prior
        elif kind in (3, 4):
            current = _unfilter_slow(kind, line, prior, bpp)
        else:
            raise PngError(f"unknown PNG filter type {kind}")
        out[y] = current
        prior = current
    return out


# Average and Paeth depend on the byte just decoded, so they go one byte at a time.
def _unfilter_slow(kind: int, line: Pixels, prior: Pixels, bpp: int) -> Pixels:
    raw, up = line.tolist(), prior.tolist()
    current = bytearray(len(raw))
    for i, value in enumerate(raw):
        left = current[i - bpp] if i >= bpp else 0
        if kind == 3:
            current[i] = (value + ((left + up[i]) >> 1)) & 255
            continue
        upper_left = up[i - bpp] if i >= bpp else 0
        estimate = left + up[i] - upper_left
        to_left, to_up, to_corner = (
            abs(estimate - left),
            abs(estimate - up[i]),
            abs(estimate - upper_left),
        )
        if to_left <= to_up and to_left <= to_corner:
            nearest = left
        elif to_up <= to_corner:
            nearest = up[i]
        else:
            nearest = upper_left
        current[i] = (value + nearest) & 255
    return np.frombuffer(bytes(current), dtype=np.uint8)


# One PNG chunk: length, type, data, CRC.
def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


# Encode an RGBA image as a compressed PNG (filter None on every row).
def encode(image: Image) -> bytes:
    pixels = np.ascontiguousarray(image.pixels, dtype=np.uint8)
    height, width = pixels.shape[:2]
    rows = np.zeros((height, width * 4 + 1), dtype=np.uint8)
    rows[:, 1:] = pixels.reshape(height, width * 4)
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(rows.tobytes(), 9))
        + _chunk(b"IEND", b"")
    )


# True when all four corner pixels are fully transparent.
def corners_transparent(image: Image) -> bool:
    alpha = image.pixels[..., 3]
    return all(int(alpha[y, x]) == 0 for y in (0, -1) for x in (0, -1))


# Make the flat background around a sprite transparent.
# The key colour is the median of the opaque border pixels. A flood fill starts at every border
# pixel and spreads (4-connected) through pixels within `tolerance` of the key colour, or already
# transparent; the sprite's dark outline stops it, so key-coloured parts inside the sprite stay.
def key_background(image: Image, tolerance: int = KEY_TOLERANCE) -> Image:
    pixels = image.pixels.copy()
    rgb, alpha = pixels[..., :3].astype(np.int16), pixels[..., 3]
    border = np.zeros(alpha.shape, dtype=bool)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    background = alpha == 0
    opaque_edge = border & ~background
    if opaque_edge.any():
        key = np.median(rgb[opaque_edge], axis=0)
        background |= np.abs(rgb - key).max(axis=2) <= tolerance
    pixels[_flood(border & background, background)] = 0
    return Image(pixels)


# Grow `start` through `allowed` (4-connected) until it stops changing.
def _flood(start: NDArray[np.bool_], allowed: NDArray[np.bool_]) -> NDArray[np.bool_]:
    reached = start.copy()
    while True:
        grown = reached.copy()
        grown[1:, :] |= reached[:-1, :]
        grown[:-1, :] |= reached[1:, :]
        grown[:, 1:] |= reached[:, :-1]
        grown[:, :-1] |= reached[:, 1:]
        grown &= allowed
        if np.array_equal(grown, reached):
            return reached
        reached = grown


# Nearest-neighbour resize (keeps pixel art crisp), for thumbnails.
def resize_nearest(image: Image, width: int, height: int) -> Image:
    ys = np.arange(height) * image.height // height
    xs = np.arange(width) * image.width // width
    return Image(np.ascontiguousarray(image.pixels[ys][:, xs]))


# Paint an RGBA image over a solid colour; the result is fully opaque.
def flatten(image: Image, colour: tuple[int, int, int]) -> Image:
    rgb = image.pixels[..., :3].astype(np.float32)
    alpha = image.pixels[..., 3:4].astype(np.float32) / 255.0
    mixed = rgb * alpha + np.array(colour, dtype=np.float32) * (1.0 - alpha)
    out = np.empty_like(image.pixels)
    out[..., :3] = np.round(mixed).astype(np.uint8)
    out[..., 3] = 255
    return Image(out)
