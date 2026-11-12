"""Turn a stat sheet into fighters for one simulated run."""

import random
from dataclasses import dataclass, replace

from app.models.stats import Ability, Body, Habitat, StatName, StatSheet
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


def plural_word(word: str) -> str:
    """ "bite" -> "bites", "crush" -> "crushes" (for swarm hints like "bites land")."""
    return word + ("es" if word.endswith(("s", "x", "z", "sh", "ch")) else "s")


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
    body: Body = Body.LIVING
    endurance_s: float = float("inf")  # machines stop working after this long
    regen_per_s: float = 0.0  # share of max hit points healed per second
    spiky: bool = False  # inert fighter whose spines hurt whoever hits it
    venomous: bool = False  # its bites deliver venom (resolved after the fight, D-44)
    venom_resist: float = 0.0  # 0 = none, 1 = immune
    abilities: tuple[Ability, ...] = ()

    @property
    def can_attack(self) -> bool:
        return self.damage > 0 and self.attacks_per_s > 0


def effective_habitat(sheet: StatSheet) -> Habitat:
    """Where the fighter moves: a creature with the flight ability uses air rules."""
    flies = sheet.lore is not None and Ability.FLIGHT in sheet.lore.abilities
    return Habitat.AIR if flies else sheet.habitat


def scale_factor(sheet: StatSheet, reference: StatSheet) -> float:
    """k = reference mass / own mass, from the sheets' central values (computed in code)."""
    own = sheet.stats[StatName.MASS].value
    if own <= 0:
        raise ValueError(f"cannot scale {sheet.display_name}: its mass must be above zero")
    return reference.stats[StatName.MASS].value / own


def sample_template(
    sheet: StatSheet, count: int, rng: random.Random, k: float = 1.0, central: bool = False
) -> Template:
    """Draw every stat uniformly between its low and high, so input uncertainty shows up.

    `k` resizes the fighter to a reference size (square-cube rules, see constants.py).
    `central=True` uses each stat's central value instead (for yes/no checks about a sheet).
    """

    def draw(name: StatName) -> float:
        stat = sheet.stats[name]
        low = stat.value if stat.low is None else stat.low
        high = stat.value if stat.high is None else stat.high
        return rng.uniform(low, high) if high > low and not central else stat.value

    mass = max(draw(StatName.MASS), c.MIN_MASS_KG) * k
    force = max(draw(StatName.ATTACK_FORCE), 0.0) * k**c.STRENGTH_SCALE_EXP
    length = k**c.LENGTH_SCALE_EXP
    speed = max(draw(StatName.SPEED), 0.0) * k**c.SPEED_SCALE_EXP
    if sheet.body == Body.INERT:
        speed = 0.0  # objects and plants never move toward anyone, whatever speed a source lists
    rate = max(draw(StatName.ATTACK_RATE), 0.0)
    reach = max(draw(StatName.REACH), 0.0) * length
    damage = force * c.DAMAGE_PER_NEWTON
    weapons = sheet.weapons
    abilities = tuple(sheet.lore.abilities) if sheet.lore else ()
    word_source = next((w for w in weapons if w in _WEAPON_WORD), None)

    # Ramming and crushing: damage from momentum (mass x speed), slow fixed attack rate.
    if "ramming" in weapons or "crushing" in weapons:
        momentum_speed = max(speed, c.CRUSH_MIN_SPEED_MPS) if "crushing" in weapons else speed
        damage = max(damage, c.RAM_DAMAGE_PER_MOMENTUM * mass * momentum_speed)
        rate = c.RAM_ATTACKS_PER_S
    ranged = "weapon_ranged" in weapons
    habitat = effective_habitat(sheet)
    # Legendary abilities (F08).
    if Ability.BREATH_WEAPON in abilities:
        ranged = True  # square law: everyone can breathe on the same target
        damage = max(damage, c.BREATH_DAMAGE_N * c.DAMAGE_PER_NEWTON)
        reach = max(reach, c.BREATH_RANGE_M)
        word_source = "breath_weapon"
    if Ability.EXTRA_HEADS in abilities:
        heads = sheet.lore.heads if sheet.lore and sheet.lore.heads else c.DEFAULT_HEADS
        rate *= heads
    # Machines and objects have no morale: they never retreat or flee.
    morale = 1.0
    if sheet.body == Body.LIVING:
        aggression = min(max(draw(StatName.AGGRESSION), 0.0), 1.0)
        morale = min(c.MORALE_FLOOR + c.MORALE_SPAN * aggression, 1.0)
    return Template(
        mass_kg=mass,
        size_m=max(draw(StatName.SIZE), c.MIN_SIZE_M) * length,
        speed_mps=speed,
        attack_force_n=force,
        attacks_per_s=rate,
        reach_m=reach,
        armor=min(max(draw(StatName.ARMOR), 0.0), 1.0),
        count=count,
        max_hp=mass * c.HP_PER_KG,
        damage=damage,
        weapon_word=_WEAPON_WORD.get(word_source, "strike"),
        ranged=ranged,
        habitat=habitat,
        group_tactics=min(max(draw(StatName.GROUP_TACTICS), 0.0), 1.0),
        morale=morale,
        body=sheet.body,
        endurance_s=max(draw(StatName.ENDURANCE), 0.0)
        if sheet.body == Body.MACHINE
        else float("inf"),
        regen_per_s=c.REGEN_SHARE_PER_S if Ability.REGENERATION in abilities else 0.0,
        spiky=sheet.body == Body.INERT and "spines" in weapons,
        venomous="venom" in weapons,
        venom_resist=venom_resistance(sheet),
        abilities=abilities,
    )


def hit_chance(attacker: Template, defender: Template) -> float:
    """Faster attackers and bigger targets are hit more easily."""
    attacker_speed = max(attacker.speed_mps, c.MIN_SPEED_MPS)
    speed_ratio = attacker_speed / max(defender.speed_mps, c.MIN_SPEED_MPS)
    size_ratio = defender.size_m / attacker.size_m
    chance = c.HIT_BASE * speed_ratio**c.HIT_SPEED_EXP * size_ratio**c.HIT_SIZE_EXP
    chance *= attacker.hit_mult
    return min(max(chance, c.HIT_MIN), c.HIT_MAX)


def venom_resistance(sheet: StatSheet) -> float:
    """0 (none) to 1 (immune), from the per-fighter assumption table in constants.py."""
    return c.VENOM_RESISTANCE.get(sheet.fighter_id.split("--")[0], 0.0)


def venom_dose(attacker: Template, target: Template) -> float:
    """Share of a lethal dose one landed bite delivers (0 for a bite without venom).

    The same bite is a bigger dose for a smaller victim: it scales with (attacker mass / target
    mass) ** VENOM_SIZE_EXP, an assumption, and resistance cuts it.
    """
    if not attacker.venomous:
        return 0.0
    size = (attacker.mass_kg / max(target.mass_kg, c.MIN_MASS_KG)) ** c.VENOM_SIZE_EXP
    return c.VENOM_BITE_SHARE * size * (1.0 - target.venom_resist)


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


def can_hurt(attacker: Template, target: Template) -> bool:
    """True if `attacker` could ever damage `target`: it has an attack and can reach it."""
    if not attacker.can_attack:
        return False
    return attacker.speed_mps > 0 or target.speed_mps > 0 or attacker.reach_m >= c.START_DISTANCE_M
