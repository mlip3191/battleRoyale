"""Turn a stat sheet into fighters for one simulated run."""

import random
from dataclasses import dataclass

from app.models.stats import StatName, StatSheet
from app.simulation import constants as c

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

    @property
    def can_attack(self) -> bool:
        return self.damage > 0 and self.attacks_per_s > 0


def sample_template(sheet: StatSheet, count: int, rng: random.Random) -> Template:
    """Draw every stat uniformly between its low and high, so input uncertainty shows up."""

    def draw(name: StatName) -> float:
        stat = sheet.stats[name]
        low = stat.value if stat.low is None else stat.low
        high = stat.value if stat.high is None else stat.high
        return rng.uniform(low, high) if high > low else stat.value

    mass = max(draw(StatName.MASS), c.MIN_MASS_KG)
    force = max(draw(StatName.ATTACK_FORCE), 0.0)
    weapon = next((w for w in sheet.weapons if w in _WEAPON_WORD), None)
    return Template(
        mass_kg=mass,
        size_m=max(draw(StatName.SIZE), c.MIN_SIZE_M),
        speed_mps=max(draw(StatName.SPEED), 0.0),
        attack_force_n=force,
        attacks_per_s=max(draw(StatName.ATTACK_RATE), 0.0),
        reach_m=max(draw(StatName.REACH), 0.0),
        armor=min(max(draw(StatName.ARMOR), 0.0), 1.0),
        count=count,
        max_hp=mass * c.HP_PER_KG,
        damage=force * c.DAMAGE_PER_NEWTON,
        weapon_word=_WEAPON_WORD.get(weapon, "strike"),
    )


def hit_chance(attacker: Template, defender: Template) -> float:
    """Faster attackers and bigger targets are hit more easily."""
    attacker_speed = max(attacker.speed_mps, c.MIN_SPEED_MPS)
    speed_ratio = attacker_speed / max(defender.speed_mps, c.MIN_SPEED_MPS)
    size_ratio = defender.size_m / attacker.size_m
    chance = c.HIT_BASE * speed_ratio**c.HIT_SPEED_EXP * size_ratio**c.HIT_SIZE_EXP
    return min(max(chance, c.HIT_MIN), c.HIT_MAX)


def damage_per_hit(attacker: Template, defender: Template) -> float:
    """Attack damage after the defender's armor."""
    return attacker.damage * (1.0 - defender.armor * c.ARMOR_EFFECT)
