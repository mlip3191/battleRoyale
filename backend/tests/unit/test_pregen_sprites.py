"""A08: pre-drawing every seed sprite and battlefield, the corner check, and thumbnails (#46)."""

from pathlib import Path

import numpy as np
import pytest

from app.media import png, pregen, style
from app.models.terrain import Terrain
from app.research.seed_fighters import load_seed_fighters
from tests.png_helpers import FakeImages

SEED_COUNT = 30


async def test_pregen_draws_and_passes_every_seed_fighter_and_terrain_in_mock_mode(
    tmp_path: Path,
) -> None:
    rows = await pregen.pregen(media_dir=tmp_path)
    sprites = [r for r in rows if r.kind == "sprite"]
    assert [r.item_id for r in sprites] == [f.id for f in load_seed_fighters()]
    assert len(sprites) == SEED_COUNT
    assert [r.item_id for r in rows if r.kind == "battlefield"] == [t.value for t in Terrain]
    assert all(r.problem is None for r in rows), pregen.report(rows)
    assert (tmp_path / "sprites" / f"pickup-truck-{style.STYLE_VERSION}.png").is_file()

    # Everything is cached now: a second run makes no provider call.
    fake = FakeImages()
    again = await pregen.pregen(provider=fake, media_dir=tmp_path)
    assert fake.calls == [] and all(r.problem is None for r in again)


def test_every_seed_fighter_has_a_safe_sprite_prompt() -> None:
    from app.media.images import sprite_prompt

    for fighter in load_seed_fighters():
        assert sprite_prompt(pregen.seed_sheet(fighter)) is not None, fighter.id


def test_the_corner_check_fails_an_opaque_png(tmp_path: Path) -> None:
    opaque = tmp_path / "opaque.png"
    opaque.write_bytes(png.encode(png.Image(np.full((8, 8, 4), 255, dtype=np.uint8))))
    assert pregen.check_sprite(opaque) == "corner pixels are not transparent"
    clear = tmp_path / "clear.png"
    clear.write_bytes(png.encode(png.Image(np.zeros((8, 8, 4), dtype=np.uint8))))
    assert pregen.check_sprite(clear) is None
    junk = tmp_path / "junk.png"
    junk.write_bytes(b"not a png")
    assert pregen.check_sprite(junk).startswith("not a readable PNG")  # type: ignore[union-attr]
    assert pregen.check_sprite(tmp_path / "missing.png") == "file missing"


def test_main_lists_failures_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A cached, opaque wolf sprite: the run reuses it and the check must catch it.
    bad = tmp_path / "sprites" / f"gray-wolf-{style.STYLE_VERSION}.png"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(png.encode(png.Image(np.full((8, 8, 4), 255, dtype=np.uint8))))
    assert pregen.main([], media_dir=tmp_path) == 1
    out = capsys.readouterr().out
    assert f"{SEED_COUNT + len(Terrain) - 1} passed, 1 failed" in out
    assert "Failures:\n  - sprite gray-wolf: corner pixels are not transparent" in out
    assert "http" not in out and "/media/" not in out


def test_main_passes_and_writes_thumbnails_and_a_contact_sheet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    thumbs = tmp_path / "thumbs"
    assert pregen.main(["--thumbs", str(thumbs)], media_dir=tmp_path / "media") == 0
    assert f"{SEED_COUNT + len(Terrain)} passed, 0 failed" in capsys.readouterr().out
    wolf = png.decode((thumbs / "sprite-gray-wolf.png").read_bytes())
    assert (wolf.width, wolf.height) == (pregen.SPRITE_THUMB, pregen.SPRITE_THUMB)
    assert png.corners_transparent(wolf)
    field = png.decode((thumbs / "battlefield-forest.png").read_bytes())
    assert field.width == pregen.BATTLEFIELD_THUMB_WIDTH
    sheet = png.decode((thumbs / "contact-sheet.png").read_bytes())
    cell = pregen.SPRITE_THUMB + pregen.CONTACT_GAP
    rows = -(-SEED_COUNT // pregen.CONTACT_COLUMNS)
    assert (sheet.width, sheet.height) == (
        pregen.CONTACT_COLUMNS * cell + pregen.CONTACT_GAP,
        rows * cell + pregen.CONTACT_GAP,
    )
    assert (sheet.pixels[..., 3] == 255).all()
