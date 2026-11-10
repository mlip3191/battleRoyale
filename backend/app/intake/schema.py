"""What the chat model sends back when it reads a matchup (intake only, not a shared contract).

The model only proposes a structure. Code in rules.py decides counts, names, size references,
and terrain, so these fields are deliberately lenient: a wrong type (say, a number where a
name belongs) is overridden by code instead of failing validation.
"""

from pydantic import BaseModel, ConfigDict


class ParsedFighter(BaseModel):
    """One side as the model read it."""

    model_config = ConfigDict(extra="ignore", use_attribute_docstrings=True)

    entity: str
    """The fighter's name, e.g. "grizzly bear"; code lowercases and singularizes it."""
    count: int | float | str | None = None
    """The model's guess at how many; ignored, because code reads the count from raw."""
    variant: str | None = None
    """Which kind, e.g. "polar" or "adult male"; empty when the user didn't say."""
    size_reference: str | int | float | None = None
    """What it is sized like ("horse-sized duck" -> "horse"); code re-reads it from raw."""
    raw: str
    """The user's exact words for this side, e.g. "100 duck-sized horses"."""


class Clarification(BaseModel):
    """The one question the model wants to ask the user."""

    model_config = ConfigDict(extra="ignore", use_attribute_docstrings=True)

    question: str
    """A short, friendly question."""
    options: list[str] = []
    """Suggested answers; code keeps the list between 2 and 4."""


class ParsedMatchup(BaseModel):
    """The model's whole reply for one matchup."""

    model_config = ConfigDict(extra="ignore", use_attribute_docstrings=True)

    fighters: list[ParsedFighter]
    """Every side the model found (code rejects anything but two). Required, so a bare `{}`
    reply fails structured output instead of passing as an empty matchup."""
    terrain: str | None = None
    """The user's words for the battlefield, e.g. "the snow"; code maps it to a Terrain."""
    needs_clarification: Clarification | None = None
    """Set when a fighter is too vague to research."""
    assumptions: list[str] = []
    """Choices the model made for the user, shown to them as assumptions."""
