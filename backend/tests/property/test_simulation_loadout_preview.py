"""Loadout previews (#283): what would each choice do to the odds?"""

import json
from pathlib import Path

import pytest

from app.models.stats import StatSheet
from app.simulation import constants as c
from app.simulation.loadout_preview import preview_choices, win_share
from app.simulation.loadouts import MAX_TIER

SEED = Path(__file__).resolve().parents[3] / "data" / "seed" / "fighters"


def seed(name: str) -> StatSheet:
    return StatSheet.model_validate(json.loads((SEED / f"{name}.json").read_text("utf-8")))


LEGIONARY, WOLF = seed("roman-legionary"), seed("gray-wolf")


def test_every_open_choice_is_previewed_best_first_and_it_is_repeatable():
    first = preview_choices(LEGIONARY, {}, WOLF)
    second = preview_choices(LEGIONARY, {}, WOLF)
    assert first == second  # deterministic: the same inputs give the same previews
    assert {p.lean for p in first} == set(c.LOADOUTS)
    assert [p.change for p in first] == sorted((p.change for p in first), reverse=True)
    for preview in first:
        assert preview.adds and preview.tier_after == 1  # nothing carried yet: each choice adds
        assert 0.0 <= preview.win_share <= 1.0
        assert preview.item  # the item name for this fighter, e.g. "wooden club"


def test_the_preview_says_whether_a_choice_adds_or_upgrades_and_skips_a_maxed_loadout():
    kit = {"attack": MAX_TIER, "defense": 2}
    previews = {p.lean: p for p in preview_choices(LEGIONARY, kit, WOLF)}
    assert "attack" not in previews  # already at the top tier: not a choice
    assert previews["defense"].adds is False and previews["defense"].tier_after == 3
    assert previews["speed"].adds is True and previews["speed"].tier_after == 1


def test_a_change_is_called_clear_only_when_it_is_bigger_than_the_noise():
    previews = preview_choices(LEGIONARY, {}, WOLF)
    for preview in previews:
        assert preview.noise > 0
        assert preview.clear == (abs(preview.change) > preview.noise)
    # The legionary v a wolf is close enough that the best choice is a clear gain (about +10
    # points against a noise near 0.07) and a speed loadout is not an improvement.
    assert previews[0].change > 0
    worst = previews[-1]
    assert worst.lean == "speed" and worst.change < previews[0].change


def test_the_best_choice_depends_on_who_is_across_the_ring():
    """Against a different opponent the ranking of choices changes (it is not one fixed order)."""
    versus_wolf = [p.lean for p in preview_choices(LEGIONARY, {}, WOLF)]
    versus_horse = [p.lean for p in preview_choices(LEGIONARY, {}, seed("horse"))]
    versus_wolf_armed = [
        p.lean for p in preview_choices(LEGIONARY, {}, WOLF, {"defense": 3, "balanced": 1})
    ]
    assert len({tuple(versus_wolf), tuple(versus_horse), tuple(versus_wolf_armed)}) > 1


def test_win_share_applies_each_sides_kit():
    plain = win_share(LEGIONARY, {}, WOLF)
    armed = win_share(LEGIONARY, {"balanced": 3}, WOLF)
    assert armed > plain
    wolf_armed = win_share(LEGIONARY, {}, WOLF, {"attack": 3})
    assert wolf_armed <= plain + 0.05  # the wolf's own kit does not help the legionary


def test_a_fighter_with_nothing_left_to_choose_has_an_empty_preview():
    full = {lean: MAX_TIER for lean in c.LOADOUTS}
    assert preview_choices(LEGIONARY, full, WOLF) == []


@pytest.mark.parametrize("runs", [100, 400])
def test_more_runs_means_less_noise(runs):
    assert preview_choices(LEGIONARY, {}, WOLF, runs=runs)[0].noise < (0.2 if runs == 100 else 0.1)
