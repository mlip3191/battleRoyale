"""Loadouts (#283): each is one choice that leans a way and costs something, and stays honest."""

import json
from itertools import permutations, product
from pathlib import Path
from typing import get_args

import pytest
import yaml

from app.models.stats import SAFE_NAME, StatName, StatSheet
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.engine import run
from app.simulation.loadouts import (
    add_or_upgrade,
    all_loadouts,
    apply_kit,
    apply_loadout,
    archetype_of,
    at_tier,
    available_choices,
    item_name,
    kit_effect,
    kit_load,
    kit_points,
    loadout,
    primary_of,
    primary_scores,
)
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
        assert changed.display_name == f"{wolf.display_name} with {item_name('mammal', item.id, 1)}"
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
        assert set(data) == {"label", "force_mul", "rate_mul", "speed_mul", "armor_mul"}


# --- tiers: a tier-up deepens the trade-off (#283 prework) ---------------------------------------

ITEMS = Path(__file__).resolve().parents[3] / "data" / "loadouts" / "items.yaml"
TIERS = (1, 2, 3, 4, 5)


def stats_of(item):
    return (item.force_mul, item.rate_mul, item.speed_mul, item.armor_mul)


def test_a_higher_tier_is_a_bigger_commitment_not_a_strictly_better_set():
    for item in all_loadouts():
        for low, high in permutations(TIERS, 2):
            if high < low:
                continue
            a = stats_of(kit_effect({item.id: low}))
            b = stats_of(kit_effect({item.id: high}))
            gains = any(x > y for x, y in zip(b, a, strict=True))
            costs = any(x < y for x, y in zip(b, a, strict=True))
            assert gains and costs, (item.id, low, high)


def test_no_loadout_at_any_tier_is_at_least_as_good_as_another_in_every_stat():
    every = [
        (item.id, tier, stats_of(kit_effect({item.id: tier})))
        for item in all_loadouts()
        for tier in TIERS
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
        at_tier(loadout("attack"), 6)


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


def test_every_kind_of_fighter_has_five_safe_natural_or_pre_modern_items_per_loadout():
    data = yaml.safe_load(ITEMS.read_text("utf-8"))
    assert set(data) == set(c.LOADOUT_ARCHETYPES)
    banned = ("gun", "rifle", "pistol", "musket", "cannon", "bomb", "grenade", "explosive", "tnt")
    names = []
    for archetype, entry in data.items():
        assert set(entry["items"]) == set(c.LOADOUTS), archetype
        assert entry["research"], archetype
        assert entry["covers"] or entry.get("covers_weapons"), archetype
        for lean, items in entry["items"].items():
            assert len(items) == 5 and len(set(items)) == 5, (archetype, lean)
            for name in items:
                assert SAFE_NAME.fullmatch(name), name
                assert not any(word in name.lower() for word in banned), name
                names.append(name)
    assert len(names) == 9 * 4 * 5


def test_the_archetypes_cover_every_sheet_category_that_can_fight():
    data = yaml.safe_load(ITEMS.read_text("utf-8"))
    covered = [category for entry in data.values() for category in entry["covers"]]
    assert len(covered) == len(set(covered))  # each category belongs to one archetype
    every = set(get_args(StatSheet.model_fields["category"].annotation))
    assert every - set(covered) == {"plant", "object"}  # no loadouts for things that cannot fight


def test_the_archetype_comes_from_the_sheet_and_decides_the_items():
    assert archetype_of(seed("gray-wolf")) == "mammal"
    assert archetype_of(seed("horse")) == "hoofed"
    assert archetype_of(seed("african-elephant")) == "hoofed"
    assert archetype_of(seed("roman-legionary")) == "warrior"
    assert archetype_of(seed("main-battle-tank")) == "machine"
    assert archetype_of(seed("saltwater-crocodile")) == "reptile"
    assert archetype_of(make_sheet("eagle", category="bird")) == "bird"
    assert archetype_of(make_sheet("ant", category="insect")) == "insect"
    assert archetype_of(make_sheet("shark", category="fish")) == "aquatic"
    assert item_name("mammal", "attack", 3) == "razor claws"
    assert item_name("hoofed", "attack", 2) == "hardened hooves"
    assert item_name("warrior", "attack", 3) == "steel battle axe"
    assert item_name("machine", "defense", 1) == "bolted armor plates"
    with pytest.raises(KeyError, match="archetype"):
        item_name("robot", "attack", 1)
    kit = {"attack": 2}
    assert apply_kit(seed("gray-wolf"), kit).display_name.endswith("with hardened claws")
    assert apply_kit(seed("roman-legionary"), kit).display_name.endswith("with iron war hammer")
    assert apply_kit(seed("main-battle-tank"), kit).display_name.endswith("with hardened ram")


def test_gear_weighs_what_the_kind_of_fighter_would_carry():
    heavy = {"defense": 3, "attack": 2}
    loads = {name: kit_load(heavy, name) for name in c.LOADOUT_ARCHETYPES}
    assert loads["warrior"] > loads["mammal"] > loads["insect"]  # iron is heavier than hide
    # A bird in plates slows sooner (smaller free load, heavier defense); a machine carries more.
    assert c.LOADOUT_ARCHETYPES["bird"]["free"] < c.LOADOUT_ARCHETYPES["machine"]["free"]
    plates = {"defense": 4}
    assert kit_effect(plates, "bird").speed_mul < kit_effect(plates, "machine").speed_mul
    assert kit_effect(plates, "warrior").speed_mul < kit_effect(plates, "mammal").speed_mul


def test_at_the_same_tier_no_loadout_dominates_another_for_any_kind_of_fighter():
    """Equal investment, different lean: nothing is simply better (a tier 5 beating a tier 1 is
    just progression, so only the same tier is compared)."""
    for archetype in c.LOADOUT_ARCHETYPES:
        for tier in TIERS:
            every = [
                (item.id, stats_of(kit_effect({item.id: tier}, archetype)))
                for item in all_loadouts()
            ]
            for (a_id, a), (b_id, b) in permutations(every, 2):
                dominated = all(x >= y for x, y in zip(a, b, strict=True)) and any(
                    x > y for x, y in zip(a, b, strict=True)
                )
                assert not dominated, (archetype, tier, a_id, "dominates", b_id)
        for item in all_loadouts():  # a higher tier is a bigger commitment, for each of them
            for low, high in permutations(TIERS, 2):
                if high > low:
                    a = stats_of(kit_effect({item.id: low}, archetype))
                    b = stats_of(kit_effect({item.id: high}, archetype))
                    assert any(x < y for x, y in zip(b, a, strict=True)), (archetype, item.id)
                    assert any(x > y for x, y in zip(b, a, strict=True)), (archetype, item.id)


def test_every_choice_costs_something_for_every_kind_of_fighter_too():
    for archetype in c.LOADOUT_ARCHETYPES:
        kits = [{}]
        while kits:
            kit = kits.pop()
            if kit_points(kit) >= 5:
                continue
            before = stats_of(kit_effect(kit, archetype)) if kit else (1.0, 1.0, 1.0, 1.0)
            for lean in available_choices(kit):
                grown = add_or_upgrade(kit, lean)
                after = stats_of(kit_effect(grown, archetype))
                free = all(x >= y for x, y in zip(after, before, strict=True)) and any(
                    x > y for x, y in zip(after, before, strict=True)
                )
                assert not free, (archetype, kit, "then", lean)
                kits.append(grown)


# --- kits: add a loadout or upgrade one each round, and the negative traits of weight ------------


def test_each_choice_adds_a_loadout_or_upgrades_one_by_a_tier():
    kit = {}
    kit = add_or_upgrade(kit, "attack")
    assert kit == {"attack": 1}
    kit = add_or_upgrade(kit, "defense")
    assert kit == {"attack": 1, "defense": 1}
    kit = add_or_upgrade(kit, "attack")
    assert kit == {"attack": 2, "defense": 1} and kit_points(kit) == 3
    assert add_or_upgrade({}, "speed") == {"speed": 1}  # the original kit is never changed in place
    with pytest.raises(KeyError):
        add_or_upgrade({}, "bazooka")


def test_a_loadout_at_the_top_tier_cannot_be_upgraded_again():
    kit = {"attack": 5, "defense": 2}
    with pytest.raises(ValueError, match="tier 5"):
        add_or_upgrade(kit, "attack")
    assert "attack" not in available_choices(kit)
    assert set(available_choices(kit)) == {"defense", "speed", "balanced"}


def test_every_choice_costs_something_so_a_kit_is_never_strictly_better_than_the_one_before():
    """Over every kit up to 6 points: one more point gains in one stat and loses in another."""
    kits = [{}]
    seen = 0
    while kits:
        kit = kits.pop()
        if kit_points(kit) >= 6:
            continue
        before = stats_of(kit_effect(kit)) if kit else (1.0, 1.0, 1.0, 1.0)
        for lean in available_choices(kit):
            after_kit = add_or_upgrade(kit, lean)
            after = stats_of(kit_effect(after_kit))
            better = all(x >= y for x, y in zip(after, before, strict=True))
            strictly = any(x > y for x, y in zip(after, before, strict=True))
            assert not (better and strictly), (kit, "then", lean, "is free")
            seen += 1
            kits.append(after_kit)
    assert seen > 100


def test_too_much_defense_reduces_speed_and_a_heavy_swing_is_slower():
    light = kit_effect({"defense": 1})
    heavy = kit_effect({"defense": 5})
    free = c.LOADOUT_ARCHETYPES["warrior"]["free"]
    assert kit_load({"defense": 1}) < free < kit_load({"defense": 5})
    # Below the free load nothing extra applies; above it speed falls faster than the loadout's own
    # cost (tier 5 defense alone would be 0.9 -> 0.668 before the encumbrance penalty).
    assert light.speed_mul == pytest.approx(at_tier(loadout("defense"), 1).speed_mul)
    assert heavy.speed_mul < at_tier(loadout("defense"), 5).speed_mul
    assert heavy.speed_mul >= at_tier(loadout("defense"), 5).speed_mul * c.ENCUMBRANCE_SPEED_FLOOR
    assert heavy.rate_mul < at_tier(loadout("defense"), 5).rate_mul  # heavy gear swings slower


def test_stacking_two_heavy_loadouts_is_slower_than_either_alone():
    both = kit_effect({"attack": 2, "defense": 2})
    assert both.speed_mul < kit_effect({"attack": 2}).speed_mul
    assert both.speed_mul < kit_effect({"defense": 2}).speed_mul


def test_attack_above_tier_three_is_reckless_and_speed_above_tier_three_is_fragile():
    assert kit_effect({"attack": 3}).armor_mul == pytest.approx(1.0)
    shrink = 1.0 - 2 * c.RECKLESS_ARMOR_SHARE_PER_TIER
    assert kit_effect({"attack": 5}).armor_mul == pytest.approx(shrink)
    plain = at_tier(loadout("speed"), 5).force_mul
    assert kit_effect({"speed": 5}).force_mul < plain
    three = at_tier(loadout("speed"), 3).force_mul
    assert kit_effect({"speed": 3}).force_mul == pytest.approx(three)


def test_light_gear_carries_almost_no_load_so_a_speed_loadout_stays_fast():
    assert kit_load({"speed": 5}) < c.LOADOUT_ARCHETYPES["warrior"]["free"]
    five = at_tier(loadout("speed"), 5).speed_mul
    assert kit_effect({"speed": 5}).speed_mul == pytest.approx(five)


def test_a_kit_sheet_names_its_parts_and_stays_labeled_not_sourced():
    wolf = seed("gray-wolf")
    kit = {"attack": 2, "defense": 1}
    sheet = apply_kit(wolf, kit)
    assert sheet.display_name == f"{wolf.display_name} with hardened claws and thicker hide"
    assert apply_kit(wolf, {}) is wolf  # no choices yet, no change
    assert sheet.sheet_hash != apply_kit(wolf, {"attack": 2}).sheet_hash
    for stat in CHANGED:
        assert sheet.stats[stat].source is None
        assert "assumption" in (sheet.stats[stat].note or "")
    assert 0.0 <= sheet.stats[StatName.ARMOR].value <= 1.0


def test_a_champion_can_reach_four_points_and_a_kit_can_use_all_of_them():
    # Entry points, then one for each of the two rounds a champion wins before the final.
    points = c.TOURNAMENT_ENTRY_POINTS + 2 * c.TOURNAMENT_POINTS_PER_WIN
    assert points == 4
    kit = {}
    for lean in ("attack", "attack", "defense", "balanced"):
        kit = add_or_upgrade(kit, lean)
    assert kit_points(kit) == points
    apply_kit(seed("gray-wolf"), kit)  # a full kit makes a valid sheet


# --- starting stats matter, and enhancing a primary attribute pays extra -----------------------


def specialist(name, **stats):
    base = dict(
        top_speed_mps=12,
        attack_force_n=500,
        attacks_per_s=1.0,
        armor_0_1=0.1,
        mass_kg=100,
        size_m=1.5,
    )
    return make_sheet(name, **{**base, **stats})


CHEETAH = specialist("cheetah", top_speed_mps=29, armor_0_1=0.05)
RHINO = specialist("rhino", mass_kg=2000, top_speed_mps=14, attack_force_n=1200, armor_0_1=0.6)
RABBIT = specialist("rabbit", top_speed_mps=18, attack_force_n=40, armor_0_1=0.05)


def test_the_primary_attribute_is_what_the_fighter_is_best_at():
    assert primary_of(CHEETAH) == "speed"
    assert primary_of(RHINO) == "defense"
    assert primary_of(seed("horse")) == "attack"  # its kick
    assert primary_of(seed("roman-legionary")) == "defense"
    assert primary_of(seed("grizzly-bear")) == "balanced"  # no clear strength: a generalist
    scores = primary_scores(CHEETAH)
    assert scores["speed"] > scores["attack"] > scores["defense"]


def test_a_loadout_scales_the_fighters_own_stats_so_strong_starts_gain_more():
    # The same speed loadout adds far more speed to a cheetah than to a rabbit...
    fast = {"speed": 1}
    cheetah_gain = value(apply_kit(CHEETAH, fast), StatName.SPEED) - value(CHEETAH, StatName.SPEED)
    rabbit_gain = value(apply_kit(RABBIT, fast), StatName.SPEED) - value(RABBIT, StatName.SPEED)
    assert cheetah_gain > rabbit_gain > 0
    # ...and the same defense loadout adds far more armor to a rhino than to a cheetah.
    armored = {"defense": 1}
    rhino_gain = value(apply_kit(RHINO, armored), StatName.ARMOR) - value(RHINO, StatName.ARMOR)
    cheetah_armor = value(apply_kit(CHEETAH, armored), StatName.ARMOR) - value(
        CHEETAH, StatName.ARMOR
    )
    assert rhino_gain > cheetah_armor > 0


def test_enhancing_the_primary_attribute_gets_even_better():
    """A cheetah's speed loadout beats a speed loadout on a fighter whose strength lies elsewhere
    (compared by the multiplier, which is the same base for both)."""
    boosted = kit_effect({"speed": 3}, "mammal", primary="speed")
    plain = kit_effect({"speed": 3}, "mammal", primary="attack")
    gain = c.PRIMARY_SYNERGY
    assert boosted.speed_mul == pytest.approx(1.0 + (plain.speed_mul - 1.0) * (1.0 + gain))
    # Only the gains are boosted; the costs (force and armor here) are the same.
    assert boosted.force_mul == pytest.approx(plain.force_mul)
    assert boosted.armor_mul == pytest.approx(plain.armor_mul)
    # On real sheets: the cheetah gets the speed bonus, a rabbit's primary is also speed, and a
    # rhino (primary defense) gets none from a speed loadout.
    cheetah_x = value(apply_kit(CHEETAH, {"speed": 3}), StatName.SPEED) / value(
        CHEETAH, StatName.SPEED
    )
    rhino_x = value(apply_kit(RHINO, {"speed": 3}), StatName.SPEED) / value(RHINO, StatName.SPEED)
    assert cheetah_x > rhino_x


def test_the_rhinos_armor_loadout_gets_the_bonus_and_the_cheetahs_does_not():
    assert primary_of(RHINO) == "defense" and primary_of(CHEETAH) == "speed"
    kit = {"defense": 3}
    rhino = kit_effect(kit, "mammal", primary_of(RHINO))
    cheetah = kit_effect(kit, "mammal", primary_of(CHEETAH))
    assert (
        rhino.armor_mul > cheetah.armor_mul
    )  # the same loadout, a bigger multiplier for the rhino
    # And the rhino starts with far more armor to multiply (capped at 1.0).
    assert value(apply_kit(RHINO, kit), StatName.ARMOR) > value(
        apply_kit(CHEETAH, kit), StatName.ARMOR
    )


def test_the_note_says_when_the_primary_attribute_was_enhanced():
    sheet = apply_kit(CHEETAH, {"speed": 2})
    assert "primary attribute: speed" in (sheet.stats[StatName.SPEED].note or "")
    other = apply_kit(CHEETAH, {"defense": 2})
    assert "primary attribute" not in (other.stats[StatName.SPEED].note or "")


def test_a_fighter_with_no_armor_can_still_gain_some():
    bare = specialist("bare", armor_0_1=0.0)
    assert value(apply_kit(bare, {"defense": 1}), StatName.ARMOR) > 0.0


def test_the_synergy_never_makes_a_loadout_free_for_any_fighter():
    """With the bonus the matching loadout is stronger, but it still costs something."""
    for archetype in c.LOADOUT_ARCHETYPES:
        for primary in ("attack", "defense", "speed", "balanced"):
            for item in all_loadouts():
                for tier in TIERS:
                    effect = stats_of(kit_effect({item.id: tier}, archetype, primary))
                    assert any(x < 1.0 for x in effect), (archetype, primary, item.id, tier)


def test_split_focus_shrinks_the_gains_of_every_loadout_but_not_the_costs():
    alone = kit_effect({"attack": 2}, "mammal")
    split = kit_effect({"attack": 2, "defense": 1}, "mammal")
    share = 1.0 - c.SPLIT_FOCUS_PENALTY
    # The attack gain (force) shrinks by the focus share when a second loadout is carried...
    assert split.force_mul == pytest.approx(1.0 + (alone.force_mul - 1.0) * share)
    # ...but the attack cost (a slower swing) does not shrink.
    defense = at_tier(loadout("defense"), 1)
    assert split.rate_mul == pytest.approx(alone.rate_mul * defense.rate_mul)
    # The floor keeps a big kit from losing every gain.
    big = kit_effect({"attack": 1, "defense": 1, "speed": 1, "balanced": 1}, "mammal")
    assert big.force_mul > 1.0 or big.armor_mul > 1.0
