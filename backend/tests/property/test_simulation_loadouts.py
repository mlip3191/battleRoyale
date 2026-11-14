"""Loadouts (#283): each is one choice that leans a way and costs something, and stays honest."""

import json
from itertools import permutations, product
from pathlib import Path

import pytest
import yaml

from app.models.stats import SAFE_NAME, StatName, StatSheet
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import run
from app.simulation.loadouts import all_loadouts, apply_loadout, at_tier, loadout
from tests.property.sim_helpers import make_sheet, matchup_of

SEED = Path(__file__).resolve().parents[3] / "data" / "seed" / "fighters"
CHANGED = (StatName.ATTACK_FORCE, StatName.ATTACK_RATE, StatName.SPEED, StatName.ARMOR)
FIGHTERS = ["gray-wolf", "grizzly-bear", "horse", "roman-legionary", "main-battle-tank"]


def seed(name: str) -> StatSheet:
    return StatSheet.model_validate(json.loads((SEED / f"{name}.json").read_text("utf-8")))


def value(sheet: StatSheet, name: StatName) -> float:
    return sheet.stats[name].value


def test_there_are_four_loadouts_and_an_unknown_one_names_the_known_ones():
    assert [item.id for item in all_loadouts()] == ["attack", "defense", "speed", "balanced"]
    with pytest.raises(KeyError, match="attack"):
        loadout("bazooka")


def test_each_loadout_leans_its_way_and_costs_something_elsewhere():
    wolf = seed("gray-wolf")
    for item in all_loadouts():
        changed = apply_loadout(wolf, item)
        gains = [n for n in CHANGED if value(changed, n) > value(wolf, n)]
        losses = [n for n in CHANGED if value(changed, n) < value(wolf, n)]
        assert gains and losses, item.id  # a trade-off, never a free upgrade
    attack = apply_loadout(wolf, loadout("attack"))
    assert value(attack, StatName.ATTACK_FORCE) > value(wolf, StatName.ATTACK_FORCE)
    assert value(attack, StatName.ATTACK_RATE) < value(wolf, StatName.ATTACK_RATE)
    defense = apply_loadout(wolf, loadout("defense"))
    assert value(defense, StatName.ARMOR) > value(wolf, StatName.ARMOR)
    assert value(defense, StatName.SPEED) < value(wolf, StatName.SPEED)
    speed = apply_loadout(wolf, loadout("speed"))
    assert value(speed, StatName.SPEED) > value(wolf, StatName.SPEED)
    assert value(speed, StatName.ARMOR) < value(wolf, StatName.ARMOR)


def test_no_loadout_is_better_than_another_in_every_changed_stat():
    """A property of the data, for every fighter: nothing dominates, so the choice is real."""
    for name in FIGHTERS:
        sheet = seed(name)
        applied = {item.id: apply_loadout(sheet, item) for item in all_loadouts()}
        for a, b in permutations(applied, 2):
            at_least = [value(applied[a], n) >= value(applied[b], n) for n in CHANGED]
            strictly = [value(applied[a], n) > value(applied[b], n) for n in CHANGED]
            assert not (all(at_least) and any(strictly)), (name, a, "dominates", b)


def test_only_the_four_stats_change_and_every_change_is_labeled_not_sourced():
    wolf = seed("gray-wolf")
    for item in all_loadouts():
        changed = apply_loadout(wolf, item)
        for stat in StatName:
            if stat not in CHANGED:
                assert changed.stats[stat] == wolf.stats[stat], (item.id, stat)
                continue
            new, old = changed.stats[stat], wolf.stats[stat]
            assert new.source is None
            assert item.label in (new.note or "") and "assumption" in (new.note or "")
            if old.is_estimate:
                assert new.is_estimate and new.method == old.method  # an estimate stays one
            elif stat != StatName.ARMOR:
                assert new.method == "derived" and not new.is_estimate
        assert changed.stats[StatName.ARMOR].method == "assumption"
        assert changed.display_name == f"{wolf.display_name} with {item.label}"
        assert changed.media_name == wolf.media_name  # prompts never see the loadout


def test_the_sheet_hash_changes_with_the_loadout_and_is_stable():
    wolf = seed("gray-wolf")
    hashes = {apply_loadout(wolf, item).sheet_hash for item in all_loadouts()}
    assert len(hashes) == 4 and wolf.sheet_hash not in hashes
    again = {apply_loadout(wolf, item).sheet_hash for item in all_loadouts()}
    assert hashes == again  # deterministic: it is what a cache key is built from


def test_armor_stays_between_zero_and_one():
    tough = make_sheet("knight", armor_0_1=0.95)
    bare = make_sheet("monk", armor_0_1=0.02)
    for item in all_loadouts():
        for sheet in (tough, bare):
            armor = apply_loadout(sheet, item).stats[StatName.ARMOR]
            assert 0.0 <= armor.value <= 1.0
            assert armor.low is not None and armor.high is not None
            assert 0.0 <= armor.low <= armor.value <= armor.high <= 1.0


def test_an_inert_object_has_no_loadout():
    cactus = make_sheet("cactus", body="inert", weapons=["spines"], top_speed_mps=0)
    assert apply_loadout(cactus, loadout("attack")) is cactus


def test_the_choice_changes_the_fight_in_the_expected_direction():
    """3 wolves v a grizzly: slowing the wolves hurts them; extra hitting power does not."""
    wolf, bear = seed("gray-wolf"), seed("grizzly-bear")

    def share(sheet: StatSheet) -> float:
        match = matchup_of(3, 1, terrain=Terrain.OPEN_FIELD)
        return run(match, [sheet, bear], runs=300, explain=False).win_prob[0]

    base = share(wolf)
    assert share(apply_loadout(wolf, loadout("speed"))) < base - 0.05
    assert share(apply_loadout(wolf, loadout("attack"))) > base - 0.03
    assert share(apply_loadout(wolf, loadout("attack"))) > share(
        apply_loadout(wolf, loadout("speed"))
    )


def test_the_numbers_are_assumptions_listed_in_the_constants_file():
    assert set(c.LOADOUTS) == {"attack", "defense", "speed", "balanced"}
    for data in c.LOADOUTS.values():
        assert set(data) == {"label", "force_mul", "rate_mul", "speed_mul", "armor_add"}


# --- tiers: a tier-up deepens the trade-off (#283 prework) ---------------------------------------

ITEMS = Path(__file__).resolve().parents[3] / "data" / "loadouts" / "items.yaml"
TIERS = (1, 2, 3)


def stats_of(item):
    return (item.force_mul, item.rate_mul, item.speed_mul, 1.0 + item.armor_add)


def test_a_higher_tier_is_a_bigger_commitment_not_a_strictly_better_set():
    for item in all_loadouts():
        for low, high in permutations(TIERS, 2):
            if high < low:
                continue
            a, b = stats_of(at_tier(item, low)), stats_of(at_tier(item, high))
            if low == high:
                continue
            assert any(x > y for x, y in zip(b, a, strict=True)), (
                item.id,
                "gains nothing",
                low,
                high,
            )
            assert any(x < y for x, y in zip(b, a, strict=True)), (
                item.id,
                "costs nothing more",
                low,
                high,
            )


def test_no_loadout_at_any_tier_is_at_least_as_good_as_another_in_every_stat():
    every = [
        (item.id, tier, stats_of(at_tier(item, tier))) for item in all_loadouts() for tier in TIERS
    ]
    for (a_id, a_tier, a), (b_id, b_tier, b) in permutations(every, 2):
        if a_id == b_id:
            continue  # the same loadout at two tiers is covered by the test above
        dominated = all(x >= y for x, y in zip(a, b, strict=True)) and any(
            x > y for x, y in zip(a, b, strict=True)
        )
        assert not dominated, (a_id, a_tier, "dominates", b_id, b_tier)


def test_tier_one_is_the_base_table_and_an_unknown_tier_is_refused():
    for item in all_loadouts():
        assert at_tier(item, 1).force_mul == item.force_mul
    with pytest.raises(ValueError, match="tier"):
        at_tier(loadout("attack"), 4)


def test_a_tiered_sheet_says_its_tier_and_changes_the_hash():
    wolf = seed("gray-wolf")
    base = apply_loadout(wolf, loadout("attack"))
    tiered = apply_loadout(wolf, loadout("attack"), tier=3)
    assert tiered.sheet_hash != base.sheet_hash
    assert "tier 3" in (tiered.stats[StatName.ATTACK_FORCE].note or "")
    assert value(tiered, StatName.ATTACK_FORCE) > value(base, StatName.ATTACK_FORCE)
    assert value(tiered, StatName.ATTACK_RATE) < value(base, StatName.ATTACK_RATE)


def test_armor_still_stays_between_zero_and_one_at_every_tier():
    for item, tier, armor in product(all_loadouts(), TIERS, (0.0, 0.05, 0.9, 1.0)):
        sheet = make_sheet("x", armor_0_1=armor)
        got = apply_loadout(sheet, item, tier=tier).stats[StatName.ARMOR]
        assert 0.0 <= got.value <= 1.0


def test_the_item_list_has_three_pre_modern_items_per_loadout_and_no_sourced_numbers_yet():
    data = yaml.safe_load(ITEMS.read_text("utf-8"))
    assert set(data) == set(c.LOADOUTS)
    banned = ("gun", "rifle", "pistol", "musket", "cannon", "bomb", "grenade", "explosive", "tnt")
    for lean, items in data.items():
        assert [item["tier"] for item in items] == [1, 2, 3], lean
        assert [item["unlocks_after_round"] for item in items] == [0, 1, 2], lean
        for item in items:
            assert SAFE_NAME.fullmatch(item["name"]), item["name"]
            assert item["era"] in {"prehistoric", "ancient", "medieval"}, item["id"]
            assert item["kind"] in {"weapon", "armor", "gear"}
            assert item["research"], item["id"]  # what a teammate must source first
            assert not any(word in item["name"].lower() for word in banned), item["name"]
            assert not any(key in item for key in ("mass_kg", "force_n", "damage")), item["id"]
    ids = [item["id"] for items in data.values() for item in items]
    assert len(ids) == len(set(ids)) == 12
