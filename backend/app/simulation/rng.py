"""Seeds: the same battle always gets the same random numbers."""

import hashlib
import random

from app.models.matchup import Matchup
from app.simulation.constants import ENGINE_VERSION


def make_seed(matchup: Matchup, sheet_hash_0: str, sheet_hash_1: str) -> int:
    """Stable 63-bit seed from the normalized matchup, both sheet hashes, and ENGINE_VERSION."""
    parts = [f"engine={ENGINE_VERSION}", f"terrain={matchup.terrain.value}"]
    for fighter in matchup.fighters:
        parts.append(
            "|".join(
                [
                    fighter.entity.strip().lower(),
                    str(fighter.count),
                    (fighter.variant or "").strip().lower(),
                    (fighter.size_reference or "").strip().lower(),
                ]
            )
        )
    parts += [sheet_hash_0, sheet_hash_1]
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") >> 1


def run_rng(seed: int, run_index: int) -> random.Random:
    """The generator for one run; independent of how many runs happen before it."""
    digest = hashlib.sha256(f"{seed}:{run_index}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))
