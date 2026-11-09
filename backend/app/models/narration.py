"""Broadcast scripts read by the announcers."""

from typing import Literal

from app.models.base import Contract


class ScriptLine(Contract):
    """One line spoken by an announcer."""

    speaker: Literal["announcer", "color_commentator"]
    """Who says it."""
    text: str
    """What they say; it may only contain numbers from the stat sheets or results."""
    at_event: int | None = None
    """Index into representative_log, to sync captions with the fight."""


class Script(Contract):
    """A block of the broadcast: intro, play-by-play, or outro."""

    kind: Literal["intro", "play_by_play", "outro"]
    """Which part of the broadcast it is."""
    lines: list[ScriptLine]
    """The lines in order."""
    fallback: bool = False
    """True when a template was used because the model was unavailable."""
