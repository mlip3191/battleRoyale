"""A08: the stdlib PNG helper decodes every filter, encodes compressed RGBA, keys out a flat
background, and checks corners."""

import numpy as np
import pytest

from app.media import png
from app.media.images import cut_out
from app.providers.mock.image import silhouette_png
from tests.png_helpers import OUTLINE, chunk, keyed_sprite_pixels, keyed_sprite_png, write_png


def random_pixels(height: int, width: int, channels: int, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(height, width, channels), dtype=np.uint8)


@pytest.mark.parametrize("channels", [3, 4])
@pytest.mark.parametrize("kind", [0, 1, 2, 3, 4])
def test_decodes_every_filter_type_for_rgb_and_rgba(channels: int, kind: int) -> None:
    pixels = random_pixels(6, 9, channels, seed=kind)
    image = png.decode(write_png(pixels, filters=(kind,)))
    assert (image.width, image.height) == (9, 6)
    assert np.array_equal(image.pixels[..., :channels], pixels)
    if channels == 3:
        assert (image.pixels[..., 3] == 255).all()


def test_decodes_mixed_filters_split_across_several_idat_chunks() -> None:
    pixels = random_pixels(11, 7, 3)
    image = png.decode(write_png(pixels, filters=(4, 3, 2, 1, 0), idat_parts=3))
    assert np.array_equal(image.pixels[..., :3], pixels)


def test_encode_round_trips_and_compresses() -> None:
    pixels = np.zeros((64, 64, 4), dtype=np.uint8)
    pixels[16:48, 16:48] = (200, 30, 30, 255)
    data = png.encode(png.Image(pixels))
    assert data.startswith(png.SIGNATURE)
    assert np.array_equal(png.decode(data).pixels, pixels)
    assert len(data) < pixels.nbytes // 10


@pytest.mark.parametrize(
    "data",
    [
        b"GIF89a not a png",
        write_png(random_pixels(2, 2, 3))[:-20],  # cut short
        write_png(random_pixels(2, 2, 3), depth=16),
        write_png(random_pixels(2, 2, 3), colour=3),  # palette
        write_png(random_pixels(2, 2, 3), interlace=1),
        write_png(random_pixels(2, 2, 3), filters=(9,)),  # unknown filter
    ],
)
def test_rejects_pngs_it_cannot_read(data: bytes) -> None:
    with pytest.raises(png.PngError):
        png.decode(data)


def test_rejects_a_damaged_chunk() -> None:
    good = write_png(random_pixels(2, 2, 3))
    damaged = good[:20] + bytes([good[20] ^ 0xFF]) + good[21:]
    with pytest.raises(png.PngError, match="damaged"):
        png.decode(damaged)
    without_header = png.SIGNATURE + chunk(b"tEXt", b"hello") + good[33:]
    with pytest.raises(png.PngError, match="no header"):
        png.decode(without_header)


def test_corner_check() -> None:
    assert png.corners_transparent(png.decode(silhouette_png((10, 20, 30))))
    opaque = png.decode(write_png(random_pixels(4, 4, 3)))
    assert not png.corners_transparent(opaque)
    one_corner = np.zeros((4, 4, 4), dtype=np.uint8)
    one_corner[-1, -1, 3] = 255
    assert not png.corners_transparent(png.Image(one_corner))


def test_key_background_makes_a_flat_magenta_border_transparent_and_keeps_the_sprite() -> None:
    size = 40
    keyed = png.key_background(png.decode(keyed_sprite_png(size)))
    alpha = keyed.pixels[..., 3]
    assert png.corners_transparent(keyed)
    low, high = size // 4, size - size // 4
    outside = np.ones((size, size), dtype=bool)
    outside[low:high, low:high] = False
    assert (alpha[outside] == 0).all()
    assert (keyed.pixels[outside][:, :3] == 0).all()  # no magenta left to bleed when scaled
    assert (alpha[low:high, low:high] == 255).all()  # outline, magenta inside, and green kept
    assert tuple(keyed.pixels[low, low, :3]) == OUTLINE


def test_cut_out_turns_the_edited_rgb_sprite_into_a_clean_rgba_png() -> None:
    result = png.decode(cut_out(keyed_sprite_png()))
    assert png.corners_transparent(result)
    assert result.pixels[20, 20, 3] == 255


def test_cut_out_refuses_a_picture_whose_corners_stay_opaque() -> None:
    pixels = keyed_sprite_pixels()
    for (y, x), colour in zip(
        [(0, 0), (0, -1), (-1, 0), (-1, -1)],
        [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 0, 0)],
        strict=True,
    ):
        pixels[y, x] = colour
    with pytest.raises(png.PngError, match="corners"):
        cut_out(write_png(pixels))


def test_key_background_leaves_an_already_transparent_background_alone() -> None:
    image = png.decode(silhouette_png((5, 5, 5)))  # near-black: must not be keyed out
    keyed = png.key_background(image)
    assert np.array_equal(keyed.pixels[..., 3], image.pixels[..., 3])


def test_resize_nearest_and_flatten() -> None:
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    pixels[:2, :2] = (255, 0, 0, 255)
    small = png.resize_nearest(png.Image(pixels), 2, 2)
    assert small.pixels.shape == (2, 2, 4)
    assert tuple(small.pixels[0, 0]) == (255, 0, 0, 255) and small.pixels[1, 1, 3] == 0
    flat = png.flatten(small, (238, 238, 238))
    assert tuple(flat.pixels[1, 1]) == (238, 238, 238, 255)
    assert tuple(flat.pixels[0, 0]) == (255, 0, 0, 255)
