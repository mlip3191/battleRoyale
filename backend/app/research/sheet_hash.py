"""Stable hash of a fighter's stats, used in the sheet cache key and the simulation seed."""

import hashlib
import json
from collections.abc import Mapping

from app.models.stats import StatName, StatValue


# Hash the stats as canonical JSON so the same stats always give the same hash.
def compute_sheet_hash(stats: Mapping[StatName, StatValue]) -> str:
    payload = {str(name): stat.model_dump(mode="json") for name, stat in stats.items()}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
