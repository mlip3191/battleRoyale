"""What the user asked for: two sides, a terrain, and the intake verdict."""

import re
from typing import Literal

from pydantic import Field, field_validator

from app.models.base import Contract
from app.models.terrain import Terrain


class FighterRequest(Contract):
    """One side of the matchup, as understood from the user's words."""

    entity: str
    """Normalized name of the fighter, e.g. "grizzly bear"."""
    count: int = Field(1, ge=1, le=10_000)
    """How many of them fight on this side (1 to 10,000)."""
    variant: str | None = None
    """Which kind, e.g. "adult male" or "polar"; empty when not specified."""
    size_reference: str | None = None
    """Another entity this fighter is sized like ("horse-sized duck" -> "horse"). Only a name,
    never a number: code computes the scale factor from both stat sheets' mass_kg."""
    raw: str
    """The user's own words for this fighter."""

    # A size reference names an entity ("horse"); numbers are computed by code, never given here.
    @field_validator("size_reference")
    @classmethod
    def _size_reference_is_a_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value or not re.search(r"[A-Za-z]", value) or re.search(r"\d", value):
            raise ValueError("size_reference must be a non-empty entity name, never a number")
        return value


class Matchup(Contract):
    """A parsed battle request: exactly two sides on one terrain."""

    fighters: list[FighterRequest] = Field(min_length=2, max_length=2)
    """The two sides (the MVP supports exactly two)."""
    terrain: Terrain = Terrain.ARENA
    """Where they fight; the arena when the user didn't say."""
    raw_text: str
    """The user's full request, word for word."""
    assumptions: list[str] = []
    """Choices intake made for the user, e.g. "Assumed adult male grizzly"."""


class IntakeResult(Contract):
    """Intake's answer: a matchup, a clarifying question, or a block."""

    status: Literal["ok", "clarify", "blocked"]
    """ok = ready to research; clarify = ask the user first; blocked = refused."""
    matchup: Matchup | None = None
    """The parsed matchup when status is ok."""
    question: str | None = None
    """The clarifying question when status is clarify."""
    options: list[str] = []
    """Two to four suggested answers to the question."""
    pending_id: str | None = None
    """Id to send back with the user's answer to a clarifying question."""
    blocked_reason: (
        Literal[
            "real_person",
            "minor",
            "sexual",
            "hate",
            "self_harm",
            "copyrighted_character",
            "deity",
            "weapon",
            "out_of_scope",
            "nonsense",
            "other",
        ]
        | None
    ) = None
    """Why the request was refused. deity = named gods or religious figures; weapon = modern
    firearms, explosives, WMD; out_of_scope = abstract ideas, places, landforms,
    celestial bodies."""
    message: str | None = None
    """Friendly text shown to the user."""
