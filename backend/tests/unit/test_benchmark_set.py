"""The benchmark matchup set must keep its agreed shape (G07)."""

import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from app.models.terrain import Terrain

ROOT = Path(__file__).parents[3]
BENCHMARK_DIR = ROOT / "data" / "benchmark"
# Reads the seed table in docs/research.md, so update this if that table changes shape.
SLUG_ROW = re.compile(r"^\| \d+ \| `([a-z-]+)` \|", re.MULTILINE)
MACHINES_AND_OBJECTS = {
    "main-battle-tank",
    "bulldozer",
    "pickup-truck",
    "toaster",
    "saguaro-cactus",
}


# Read one matchup file.
def load(name: str) -> list[dict[str, Any]]:
    text = (BENCHMARK_DIR / name).read_text(encoding="utf-8")
    return yaml.safe_load(text)["matchups"]


# Names of the fighters on both sides of an entry.
def fighters_of(entry: dict[str, Any]) -> set[str]:
    return {fighter["entity"] for fighter in entry["fighters"]}


TUNING = load("matchups.yaml")
HELD_OUT = load("heldout.yaml")
ALL = TUNING + HELD_OUT


def test_group_sizes() -> None:
    assert Counter(e["group"] for e in ALL) == {"obvious": 15, "documented": 10, "count": 5}


def test_held_out_mixes_all_groups() -> None:
    assert Counter(e["group"] for e in HELD_OUT) == {"obvious": 5, "documented": 3, "count": 2}
    assert len(TUNING) == 20


def test_ids_are_unique() -> None:
    ids = [e["id"] for e in ALL]
    assert len(ids) == len(set(ids))


def test_enough_obvious_cases_use_an_object_or_machine() -> None:
    obvious = [e for e in ALL if e["group"] == "obvious"]
    assert sum(bool(fighters_of(e) & MACHINES_AND_OBJECTS) for e in obvious) >= 3


def test_fighters_come_from_the_seed_list() -> None:
    seed = set(SLUG_ROW.findall((ROOT / "docs" / "research.md").read_text(encoding="utf-8")))
    assert len(seed) == 30
    for entry in ALL:
        assert fighters_of(entry) <= seed, entry["id"]


def test_entries_are_complete() -> None:
    for entry in ALL:
        assert len(entry["fighters"]) == 2, entry["id"]
        for fighter in entry["fighters"]:
            count = fighter["count"]
            assert isinstance(count, int) and 1 <= count <= 10_000, entry["id"]
            assert fighter["variant"] is None, entry["id"]  # default variant: plain slug
        if entry["group"] == "count":
            assert [f["count"] for f in entry["fighters"]] == [1, 1], entry["id"]
        assert entry["terrain"] in set(Terrain), entry["id"]
        assert entry["expected_winner"] in {"0", "1", "draw"}, entry["id"]
        assert entry["confidence"] in {"high", "medium"}, entry["id"]


def test_sources_match_the_group() -> None:
    for entry in ALL:
        if entry["group"] == "documented":
            assert entry["source"].startswith("https://"), entry["id"]
            assert entry["quote"].strip(), entry["id"]
        else:
            assert re.match(r"obvious: \S", entry["source"]), entry["id"]


def test_only_count_cases_have_a_fair_range() -> None:
    for entry in ALL:
        fair = entry.get("expected_fair_count")
        if entry["group"] == "count":
            assert fair is not None and 1 <= fair[0] <= fair[1], entry["id"]
        else:
            assert fair is None, entry["id"]
