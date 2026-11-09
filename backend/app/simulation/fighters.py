"""Turn a stat sheet into fighters for one simulated run."""

import random
from dataclasses import dataclass, replace

from app.models.stats import Habitat, StatName, StatSheet
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.terrain import modifier

# Short neutral words for the log, by weapon.
_WEAPON_WORD = {
    "teeth": "bite",
    "claws": "claw swipe",
    "horns": "goring thrust",
    "hooves": "kick",
    "venom": "venom strike",
    "constriction": "squeeze",
    "tusks": "tusk jab",
    "beak": "peck",
    "sting": "sting",
    "weapon_melee": "blow",
    "weapon_ranged": "shot",
    "ramming": "ram",
    "crushing": "crush",
    "spines": "spine jab",
    "breath_weapon": "blast",
}


@dataclass(frozen=True)
class Template:
    """One side's stats for one run, each sampled from its low-high range."""

    mass_kg: float
    size_m: float
    speed_mps: float
    attack_force_n: float
    attacks_per_s: float
    reach_m: float
    armor: float
    count: int
    max_hp: float
    damage: float
    weapon_word: str
    ranged: bool = False
    habitat: Habitat = Habitat.LAND
    group_tactics: float = 0.0
    morale: float = 1.0  # share of total hit points lost at which the side retreats
    hit_mult: float = 1.0

    @property
    def can_attack(self) -> bool:
        return self.damage > 0 and self.attacks_per_s > 0


def scale_factor(sheet: StatSheet, reference: StatSheet) -> float:
    """k = reference mass / own mass, from the sheets' central values (computed in code)."""
    own = sheet.stats[StatName.MASS].value
    if own <= 0:
        raise ValueError(f"cannot scale {sheet.display_name}: its mass must be above zero")
    return reference.stats[StatName.MASS].value / own


def sample_template(sheet: StatSheet, count: int, rng: random.Random, k: float = 1.0) -> Template:
    """Draw every stat uniformly between its low and high, so input uncertainty shows up.

    `k` resizes the fighter to a reference size (square-cube rules, see constants.py).
    """

    def draw(name: StatName) -> float:
        stat = sheet.stats[name]
        low = stat.value if stat.low is None else stat.low
        high = stat.value if stat.high is None else stat.high
        return rng.uniform(low, high) if high > low else stat.value

    mass = max(draw(StatName.MASS), c.MIN_MASS_KG) * k
    force = max(draw(StatName.ATTACK_FORCE), 0.0) * k**c.STRENGTH_SCALE_EXP
    length = k**c.LENGTH_SCALE_EXP
    weapon = next((w for w in sheet.weapons if w in _WEAPON_WORD), None)
    return Template(
        mass_kg=mass,
        size_m=max(draw(StatName.SIZE), c.MIN_SIZE_M) * length,
        speed_mps=max(draw(StatName.SPEED), 0.0) * k**c.SPEED_SCALE_EXP,
        attack_force_n=force,
        attacks_per_s=max(draw(StatName.ATTACK_RATE), 0.0),
        reach_m=max(draw(StatName.REACH), 0.0) * length,
        armor=min(max(draw(StatName.ARMOR), 0.0), 1.0),
        count=count,
        max_hp=mass * c.HP_PER_KG,
        damage=force * c.DAMAGE_PER_NEWTON,
        weapon_word=_WEAPON_WORD.get(weapon, "strike"),
        ranged="weapon_ranged" in sheet.weapons,
        habitat=sheet.habitat,
        group_tactics=min(max(draw(StatName.GROUP_TACTICS), 0.0), 1.0),
        morale=min(
            c.MORALE_FLOOR + c.MORALE_SPAN * min(max(draw(StatName.AGGRESSION), 0.0), 1.0), 1.0
        ),
    )


def hit_chance(attacker: Template, defender: Template) -> float:
    """Faster attackers and bigger targets are hit more easily."""
    attacker_speed = max(attacker.speed_mps, c.MIN_SPEED_MPS)
    speed_ratio = attacker_speed / max(defender.speed_mps, c.MIN_SPEED_MPS)
    size_ratio = defender.size_m / attacker.size_m
    chance = c.HIT_BASE * speed_ratio**c.HIT_SPEED_EXP * size_ratio**c.HIT_SIZE_EXP
    chance *= attacker.hit_mult
    return min(max(chance, c.HIT_MIN), c.HIT_MAX)


def damage_per_hit(attacker: Template, defender: Template) -> float:
    """Attack damage after the defender's armor."""
    return attacker.damage * (1.0 - defender.armor * c.ARMOR_EFFECT)


def max_engagers(attacker: Template, target: Template) -> int:
    """How many of `attacker`'s kind can attack one `target` at once (melee, Lanchester linear)."""
    ratio = (target.size_m / attacker.size_m) ** 2
    return int(min(max(ratio, 1.0), c.MAX_ENGAGERS))


def apply_terrain(template: Template, terrain: Terrain) -> Template:
    """Apply the terrain's speed, attack, and hit multipliers for this fighter's habitat."""
    mod = modifier(terrain, template.habitat)
    return replace(
        template,
        speed_mps=template.speed_mps * mod.speed,
        damage=template.damage * mod.attack,
        hit_mult=template.hit_mult * mod.hit,
    )


def group_bonus(template: Template) -> float:
    """Hit-chance multiplier when two or more of this side attack the same target."""
    return 1.0 + c.GROUP_TACTICS_BONUS * template.group_tactics
