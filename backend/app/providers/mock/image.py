"""Mock image provider: a small colored silhouette PNG, built without image libraries."""

import hashlib
import struct
import zlib

MOCK_IMAGE_SIZE = 64


# One PNG chunk: length, type, data, CRC.
def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


# A filled circle in color on a transparent square, as RGBA PNG bytes.
def silhouette_png(color: tuple[int, int, int], size: int = MOCK_IMAGE_SIZE) -> bytes:
    center = (size - 1) / 2
    radius_sq = (size * 0.4) ** 2
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # PNG filter type "none" for this row
        for x in range(size):
            inside = (x - center) ** 2 + (y - center) ** 2 <= radius_sq
            rows.extend((*color, 255) if inside else (0, 0, 0, 0))
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(rows)))
        + _png_chunk(b"IEND", b"")
    )


# The prompt decides the color, so the same prompt always gives the same image.
def _color_for(prompt: str) -> tuple[int, int, int]:
    digest = hashlib.sha256(prompt.encode("utf-8")).digest()
    return digest[0], digest[1], digest[2]


class MockImageGen:
    """Silhouette PNGs colored by the prompt."""

    async def generate(self, prompt: str) -> bytes:
        return silhouette_png(_color_for(prompt))

    async def edit(self, image: bytes, prompt: str) -> bytes:
        return silhouette_png(_color_for(f"edit:{prompt}"))
