"""A battle as stored and sent to the front end, with the progress of each pipeline stage."""

from datetime import datetime
from typing import Literal

from app.models.base import Contract
from app.models.matchup import Matchup
from app.models.media import Asset
from app.models.narration import Script
from app.models.simulation import ChallengerSuggestion, FairFight, SimulationResult
from app.models.stats import StatSheet


class StageStatus(Contract):
    """Progress of one pipeline stage."""

    stage: Literal[
        "intake",
        "research",
        "simulate",
        "summary",
        "challenger",
        "script",
        "audio",
        "music",
        "images",
    ]
    """Which stage."""
    status: Literal["pending", "running", "done", "failed", "fallback"]
    """Where it is; fallback means a stand-in was used and the battle continues."""
    detail: str | None = None
    """Short user-facing note, e.g. which fighter is being researched."""


class BattleRecord(Contract):
    """Everything about one battle; filled in stage by stage while it runs."""

    battle_id: str
    """Id used in /battle/<id> links."""
    created_at: datetime
    """When the battle was requested."""
    matchup: Matchup
    """The parsed request."""
    stat_sheets: list[StatSheet] = []
    """One stat sheet per side, once research is done."""
    result: SimulationResult | None = None
    """The simulation verdict, once it is done."""
    fair_fight: FairFight | None = None
    """The fair-fight count, once it is done."""
    challenger: ChallengerSuggestion | None = None
    """The next challenger suggestion, once it is done."""
    scripts: list[Script] = []
    """Broadcast scripts, once written."""
    assets: list[Asset] = []
    """Generated media, once made."""
    stages: list[StageStatus]
    """Progress of every stage."""
    status: Literal["running", "done", "failed"]
    """Overall state of the battle."""
