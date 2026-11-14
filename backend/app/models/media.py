"""Generated media files: sprites, battlefield, narration audio, and music."""

from typing import Literal

from app.models.base import Contract


class Asset(Contract):
    """One generated media file served from /media."""

    asset_id: str
    """Stable id of the file."""
    kind: Literal["sprite", "battlefield", "narration_audio", "music"]
    """What the file is."""
    url: str
    """Where the front end loads it, e.g. "/media/sprites/grizzly-bear.png"."""
    prompt_hash: str
    """Hash of the prompt that made it, used for caching."""
    fallback: bool = False
    """True when a stock file was used because generation failed."""
    script_kind: Literal["intro", "play_by_play", "outro"] | None = None
    """For narration_audio: which Script it reads. None for every other kind."""
