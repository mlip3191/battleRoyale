"""Terrain x habitat: how the battlefield helps or hurts each kind of mover.

Every row is (speed, attack, hit) multipliers. All numbers are assumptions chosen so that
"fish out of water" and "cat in deep water" are heavily handicapped while ordinary terrain
is a small nudge; see docs/simulation-model.md.
"""

from typing import NamedTuple

from app.models.stats import Habitat
from app.models.terrain import Terrain


class Modifier(NamedTuple):
    """Multipliers applied to a fighter standing in a terrain."""

    speed: float
    attack: float
    hit: float


L, W, A, X = Habitat.LAND, Habitat.WATER, Habitat.AIR, Habitat.AMPHIBIOUS
T = Terrain

MODIFIERS: dict[tuple[Terrain, Habitat], Modifier] = {
    # --- arena: flat, enclosed ground; fliers cannot use their full range ---
    (T.ARENA, L): Modifier(1.0, 1.0, 1.0),  # home ground for land animals
    (T.ARENA, W): Modifier(0.1, 0.3, 0.5),  # stranded: gasping, can barely move or bite
    (T.ARENA, A): Modifier(0.8, 1.0, 0.95),  # walls limit flight a little
    (T.ARENA, X): Modifier(0.8, 0.9, 0.9),  # amphibians are clumsy but fine on land
    # --- open field: flat and open; the neutral baseline ---
    (T.OPEN_FIELD, L): Modifier(1.0, 1.0, 1.0),  # baseline
    (T.OPEN_FIELD, W): Modifier(0.1, 0.3, 0.5),  # stranded on dry land
    (T.OPEN_FIELD, A): Modifier(1.0, 1.0, 1.0),  # open sky: fliers are unhindered
    (T.OPEN_FIELD, X): Modifier(0.8, 0.9, 0.9),  # amphibious animal out of the water
    # --- forest: trees slow big, fast movers and hide small ones ---
    (T.FOREST, L): Modifier(0.9, 1.0, 1.0),  # undergrowth costs a little speed
    (T.FOREST, W): Modifier(0.1, 0.3, 0.5),  # stranded
    (T.FOREST, A): Modifier(0.6, 1.0, 0.85),  # branches block flight paths and dives
    (T.FOREST, X): Modifier(0.8, 0.9, 0.9),  # damp ground helps a little, no more
    # --- water: open deep water ---
    (T.WATER, L): Modifier(0.2, 0.4, 0.5),  # deep water: paddling, no footing (heavy penalty)
    (T.WATER, W): Modifier(1.0, 1.0, 1.0),  # home ground for fish and swimmers
    (T.WATER, A): Modifier(1.0, 1.0, 1.0),  # fliers hover over the surface freely
    (T.WATER, X): Modifier(0.9, 1.0, 1.0),  # swimming amphibians are nearly at home
    # --- shoreline: shallows; both sides can engage, both weakly ---
    (T.SHORELINE, L): Modifier(0.7, 0.8, 0.8),  # wading slows footing
    (T.SHORELINE, W): Modifier(0.5, 0.6, 0.7),  # shallows restrict a swimmer's movement
    (T.SHORELINE, A): Modifier(1.0, 1.0, 1.0),  # open air above the shallows
    (T.SHORELINE, X): Modifier(1.0, 1.0, 1.0),  # amphibians' favorite ground
    # --- urban: streets and buildings; cover for some, obstacles for others ---
    (T.URBAN, L): Modifier(1.0, 1.0, 0.95),  # hard ground, some cover
    (T.URBAN, W): Modifier(0.1, 0.3, 0.5),  # stranded
    (T.URBAN, A): Modifier(0.8, 1.0, 0.9),  # buildings clutter the air
    (T.URBAN, X): Modifier(0.8, 0.9, 0.9),  # out of its element
    # --- mountain: steep rock; heavy bodies and fliers cope worst ---
    (T.MOUNTAIN, L): Modifier(0.85, 1.0, 0.95),  # slopes cost speed
    (T.MOUNTAIN, W): Modifier(0.1, 0.3, 0.5),  # stranded
    (T.MOUNTAIN, A): Modifier(0.9, 1.0, 0.95),  # thin air and updrafts, small cost
    (T.MOUNTAIN, X): Modifier(0.7, 0.9, 0.85),  # rough rock is hard on soft bodies
}


def modifier(terrain: Terrain, habitat: Habitat) -> Modifier:
    """The multipliers for one fighter."""
    return MODIFIERS[(terrain, habitat)]


def can_engage(terrain: Terrain, habitat_a: Habitat, habitat_b: Habitat) -> bool:
    """False when neither side can reach the other (the result is then `no_contest`).

    A strictly water-living fighter is submerged in open water or the shallows' deep end, out of
    reach of a flier, and a flier is out of reach of it. On dry land a fish is stranded and
    reachable. In the shallows (shoreline) everyone is reachable, but weakly.
    """
    if terrain is Terrain.WATER and {habitat_a, habitat_b} == {Habitat.AIR, Habitat.WATER}:
        return False
    return True
