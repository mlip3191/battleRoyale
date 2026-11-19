"""#280: mock-mode media is kept apart from live media, and an empty file is never a cache hit.

Every test uses stand-in providers (no network). "Live" here only means settings say
PROVIDER_MODE=live; the provider passed in is still a stand-in.
"""

import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, use_settings
from app.main import create_app
from app.media import audio, files, images, style
from app.models.matchup import Matchup
from app.models.media import Asset
from app.models.narration import Script, ScriptLine
from app.models.stats import StatSheet
from app.models.terrain import Terrain
from app.providers.mock.audio import MockMusicGen, MockTTS
from app.research.seed_fighters import find_seed_sheet
from tests.conftest import mock_settings
from tests.png_helpers import FakeImages

MediaMaker = Callable[[Any, Path], Awaitable[Asset | None]]


class CountingTTS(MockTTS):
    """The mock TTS, counting the lines it speaks."""

    def __init__(self) -> None:
        self.calls = 0

    async def speak(self, text: str, voice_id: str) -> bytes:
        self.calls += 1
        return await super().speak(text, voice_id)


class CountingMusic(MockMusicGen):
    """The mock music generator, counting the tracks it composes."""

    def __init__(self) -> None:
        self.calls = 0

    async def compose(self, prompt: str, seconds: float) -> bytes:
        self.calls += 1
        return await super().compose(prompt, seconds)


def wolf() -> StatSheet:
    found = find_seed_sheet("gray wolf")
    assert found is not None
    return found


def matchup() -> Matchup:
    fighters = [{"entity": "gray wolf", "raw": "gray wolf"}] * 2
    return Matchup.model_validate({"fighters": fighters, "raw_text": "gray wolf vs gray wolf"})


def intro() -> Script:
    lines = [ScriptLine(speaker="announcer", text="Welcome to the arena!")]
    return Script.model_validate({"kind": "intro", "lines": lines})


def live_settings(data_dir: Path) -> Settings:
    return Settings(_env_file=None, provider_mode="live", data_dir=data_dir)


# --- one maker per kind of media: (provider, media_dir) -> asset ----------------------------------


async def sprite(provider: Any, media_dir: Path) -> Asset | None:
    return await images.make_sprite(wolf(), provider=provider, media_dir=media_dir)


async def battlefield(provider: Any, media_dir: Path) -> Asset | None:
    return await images.make_battlefield(Terrain.FOREST, provider=provider, media_dir=media_dir)


async def narration(provider: Any, media_dir: Path) -> Asset | None:
    made = await audio.make_audio([intro()], provider=provider, media_dir=media_dir)
    return made[0] if made else None


async def music(provider: Any, media_dir: Path) -> Asset | None:
    return await audio.make_music(matchup(), None, [wolf()], provider=provider, media_dir=media_dir)


# Each kind of media with a fresh stand-in provider and a way to count its calls.
MAKERS: dict[str, tuple[MediaMaker, Callable[[], Any], Callable[[Any], int]]] = {
    "sprite": (sprite, FakeImages, lambda p: len(p.calls)),
    "battlefield": (battlefield, FakeImages, lambda p: len(p.calls)),
    "narration": (narration, CountingTTS, lambda p: p.calls),
    "music": (music, CountingMusic, lambda p: p.calls),
}


# The file an asset's url points at, under the media folder.
def file_of(asset: Asset, media_dir: Path) -> Path:
    assert asset.url.startswith("/media/")
    return media_dir / asset.url.removeprefix("/media/")


@pytest.mark.parametrize("kind", list(MAKERS))
async def test_media_cached_in_mock_mode_is_not_reused_in_live_mode(
    tmp_path: Path, kind: str
) -> None:
    make, new_provider, calls = MAKERS[kind]
    use_settings(mock_settings(data_dir=tmp_path))
    mock_asset = await make(new_provider(), tmp_path)
    assert mock_asset is not None and file_of(mock_asset, tmp_path).is_file()

    use_settings(live_settings(tmp_path))
    live_provider = new_provider()
    live_asset = await make(live_provider, tmp_path)
    assert calls(live_provider) > 0  # the mock file was not served as live
    assert mock_asset.url.startswith("/media/mock/")
    assert live_asset is not None and not live_asset.url.startswith("/media/mock/")
    assert live_asset.asset_id == mock_asset.asset_id  # same request, only the folder differs
    assert file_of(live_asset, tmp_path).is_file()

    # Each mode now reuses its own file without calling the provider again.
    again = new_provider()
    assert await make(again, tmp_path) == live_asset and calls(again) == 0
    use_settings(mock_settings(data_dir=tmp_path))
    assert await make(again, tmp_path) == mock_asset and calls(again) == 0


async def test_live_files_keep_their_usual_urls(tmp_path: Path) -> None:
    use_settings(live_settings(tmp_path))
    asset = await sprite(FakeImages(), tmp_path)
    assert asset is not None
    assert asset.url == f"/media/sprites/gray-wolf-{style.STYLE_VERSION}.png"
    assert (tmp_path / "sprites" / f"gray-wolf-{style.STYLE_VERSION}.png").is_file()


@pytest.mark.parametrize("mode", ["mock", "live"])
@pytest.mark.parametrize("kind", list(MAKERS))
async def test_an_empty_cached_file_is_a_miss_and_is_made_again(
    tmp_path: Path, kind: str, mode: str
) -> None:
    make, new_provider, calls = MAKERS[kind]
    use_settings(mock_settings(data_dir=tmp_path) if mode == "mock" else live_settings(tmp_path))
    first = await make(new_provider(), tmp_path)
    assert first is not None
    file = file_of(first, tmp_path)
    file.write_bytes(b"")  # an empty (damaged) file left in the cache

    provider = new_provider()
    again = await make(provider, tmp_path)
    assert calls(provider) > 0 and again == first
    assert file.stat().st_size > 0


def test_save_waits_out_a_brief_open_handle_on_the_old_file(tmp_path: Path) -> None:
    # #381: on Windows, replacing a file that another process has open (an antivirus scan,
    # the search indexer, a browser still downloading it) fails with PermissionError.
    file = tmp_path / "sprite.png"
    file.write_bytes(b"old")
    handle = file.open("rb")
    releaser = threading.Timer(0.2, handle.close)
    releaser.start()
    try:
        files.save(file, b"new")
    finally:
        releaser.join()
        handle.close()
    assert file.read_bytes() == b"new"
    assert [p.name for p in tmp_path.iterdir()] == ["sprite.png"]  # no temp file left behind


def test_save_still_fails_when_the_file_stays_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A file held for good fails after the retries, so the caller falls back as before.
    def locked(source: object, target: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(files.os, "replace", locked)
    monkeypatch.setattr(files.time, "sleep", lambda _s: None)
    file = tmp_path / "sprite.png"
    with pytest.raises(PermissionError):
        files.save(file, b"new")
    assert list(tmp_path.iterdir()) == []


def test_is_cached_needs_a_non_empty_regular_file(tmp_path: Path) -> None:
    full = tmp_path / "full.png"
    full.write_bytes(b"x")
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    folder = tmp_path / "folder.png"
    folder.mkdir()
    assert files.is_cached(full)
    assert not files.is_cached(empty)
    assert not files.is_cached(folder)
    assert not files.is_cached(tmp_path / "missing.png")


def test_cache_path_puts_only_mock_files_in_the_mock_folder() -> None:
    name = Path("audio") / "music-0123.wav"
    assert files.cache_path(name, "live") == name
    assert files.cache_path(name, "mock") == Path("mock") / "audio" / "music-0123.wav"


async def test_a_mock_file_is_served_at_its_url(tmp_path: Path) -> None:
    settings = mock_settings(data_dir=tmp_path)
    use_settings(settings)
    media_dir = tmp_path / "media"
    asset = await sprite(FakeImages(), media_dir)
    assert asset is not None
    client = TestClient(create_app(settings, frontend_dist=tmp_path / "missing"))
    response = client.get(asset.url)
    assert response.status_code == 200
    assert response.content == file_of(asset, media_dir).read_bytes()
