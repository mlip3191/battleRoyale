"""Small HTTP replies (ARCHITECTURE §6): battle created, showcase rows, fighter search rows."""

from app.models.base import Contract


class BattleCreated(Contract):
    """Reply to POST /api/battles (202): the id to follow the new battle with."""

    battle_id: str
    """Id of the battle that just started, e.g. "b-7f3k2q"."""


class ShowcaseBattle(Contract):
    """One row of GET /api/battles?showcase=true: a saved showcase battle."""

    battle_id: str
    """Id of the saved battle."""
    title: str
    """Matchup title shown on the home page, e.g. "Grizzly bear vs Gray wolf"."""


class FighterMatch(Contract):
    """One row of GET /api/fighters?q=: a fighter whose name matches the search text."""

    fighter_id: str
    """Stable fighter id, e.g. "grizzly-bear--adult-male"."""
    display_name: str
    """Name shown to the user."""
    cached: bool
    """True when a stat sheet is already saved, so the battle can skip research."""
