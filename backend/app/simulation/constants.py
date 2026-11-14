"""Every number the fight engine uses that is not a stat on a sheet.

Each constant has a comment; docs/simulation-model.md gives its source or labels it an assumption.
Change a value here and the results change, so bump ENGINE_VERSION in the same commit.
"""

# Part of the random seed, so a new engine never silently reproduces an old battle.
ENGINE_VERSION = 8

# Length of one simulation tick; attack times are rounded up to a multiple of this.
TICK_S = 0.1
# A fight still going after this long is a draw.
MAX_FIGHT_S = 600.0
# The representative log never has more events than the contract allows.
MAX_LOG_EVENTS = 300

# Where the two sides start, measured edge to edge.
START_DISTANCE_M = 10.0

# Hit points per kilogram. Body volume (and so tissue to damage) grows with mass.
HP_PER_KG = 10.0
# Damage in hit points per newton of attack force (assumption: calibrates force against hp).
DAMAGE_PER_NEWTON = 0.05
# Share of damage a full armor value (1.0) blocks.
ARMOR_EFFECT = 0.8

# Chance to hit when attacker and defender are equal in speed and size.
HIT_BASE = 0.75
# How strongly a speed advantage raises hit chance: (attacker speed / defender speed) ** exp.
HIT_SPEED_EXP = 0.3
# How strongly a bigger target is easier to hit: (defender size / attacker size) ** exp.
HIT_SIZE_EXP = 0.2
# Hit chance never leaves this range, so no fight is a certainty.
HIT_MIN = 0.05
HIT_MAX = 0.95
# Speed floor so a stationary fighter does not divide by zero.
MIN_SPEED_MPS = 0.1
# Smallest mass and size a sampled fighter can have (numerical safeguards).
MIN_MASS_KG = 1e-6
MIN_SIZE_M = 1e-3
# Log slots kept free at the end for the closing events: a stalemate, the end, and one summary
# knock-out per side for the falls that did not fit in the log ("more go down").
CLOSING_EVENTS = 4
# Hits and misses may fill only this share of the replay log; the rest is kept for knock-outs,
# retreats and escapes, so a crowded fight still shows fighters going down.
LOG_FLOW_SHARE = 0.5

# z-score for a 95% Wilson confidence interval.
WILSON_Z = 1.96

# --- Numbers and size (F03) ---

# Most attackers that can surround one target at once (Lanchester linear law, melee).
MAX_ENGAGERS = 8
# A side with more individuals than this is simulated in groups instead of one by one.
SWARM_THRESHOLD = 200
# Shortest swarm step. Swarm fights act in coarse steps, not per-fighter events.
SWARM_STEP_S = 0.5
# Steps lengthen as a fight goes on: at least this share of the elapsed time (assumption:
# keeps long swarm fights fast while early, decisive moments stay finely resolved).
SWARM_STEP_GROWTH = 0.1

# Square-cube scaling when a fighter is resized by factor k = reference mass / own mass.
# Strength (muscle cross-section) scales with area: k ** (2/3).
STRENGTH_SCALE_EXP = 2 / 3
# Length-like stats (size, reach) scale with k ** (1/3).
LENGTH_SCALE_EXP = 1 / 3
# Top running speed scales roughly with mass ** 0.17 (Garland 1983), about k ** (1/6).
SPEED_SCALE_EXP = 1 / 6

# --- Terrain and behavior (F04) ---

# A side retreats once it has lost this share of its total hit points. The share is
# MORALE_FLOOR + MORALE_SPAN * aggression_0_1, so the most timid break at 20% and the most
# aggressive never do (assumption; no source measures this).
MORALE_FLOOR = 0.2
MORALE_SPAN = 0.8
# Coordinated attacks: with two or more attackers on one target, hit chance rises by up to
# this share at group_tactics_0_1 = 1 (assumption).
GROUP_TACTICS_BONUS = 0.5

# --- Deciding factor (F05) ---

# Runs used for each one-at-a-time sensitivity check.
DECIDING_RUNS = 200
# Weight of the favorite's average survivors next to its win share when ranking factors, so a
# lopsided fight (win share stuck at 100%) still shows which factor matters most (assumption).
SURVIVOR_WEIGHT = 0.5
# If no factor moves the favorite's results by at least this much, the fight is "too close".
MIN_EFFECT = 0.02

# --- Fair-fight search (F06) ---

# Runs per probe of the fair-fight search and per next-challenger duel.
FAIR_RUNS = 200
# A fight is "fair" when the varied side's win share is within this of 50%.
FAIR_TOLERANCE = 0.05
# Most probes one search may use, and the largest count it will try.
FAIR_MAX_PROBES = 20
FAIR_MAX_COUNT = 10_000
# The next-challenger reason says "a coin flip" within FAIR_TOLERANCE of 50%, "a slight" favorite
# or underdog within this of 50%, and "a clear" one beyond it (wording only, never a result).
CHALLENGER_SLIGHT_GAP = 0.15

# --- Machines, objects, and mythical abilities (F08) ---

# Ramming and crushing: damage per hit = RAM_DAMAGE_PER_MOMENTUM * mass * speed (momentum, kg*m/s).
# Momentum is the physical measure of how hard a moving mass hits; the conversion to hit points
# is an assumption (same role as DAMAGE_PER_NEWTON).
RAM_DAMAGE_PER_MOMENTUM = 0.005
# A ramming or crushing vehicle makes one pass every 2.5 s (assumption).
RAM_ATTACKS_PER_S = 0.4
# Crushing needs weight, not speed: speed is floored at this for the momentum formula (assumption).
CRUSH_MIN_SPEED_MPS = 1.0

# Breath weapon: a ranged attack. Damage is the larger of the fighter's melee damage and this many
# newton-equivalents x DAMAGE_PER_NEWTON; it reaches this far (all assumptions: legends give no
# numbers).
BREATH_DAMAGE_N = 100_000.0
BREATH_RANGE_M = 15.0
# Regeneration heals this share of max hit points per second (assumption).
REGEN_SHARE_PER_S = 0.002
# Heads used when a creature has extra_heads but its legend names no verified number (ARCH §9).
DEFAULT_HEADS = 3

# --- Venom (D-44; every number is an assumption) ---

# Venom takes minutes to work. Each landed venomous bite adds this share of a lethal dose to the
# target, scaled by relative body size, and a fighter that carries a full dose (1.0) dies after
# the fight (a side wiped out leaves a poisoned survivor to die, which can make it a draw).
VENOM_BITE_SHARE = 0.65
# A bite is a bigger dose for a smaller victim: it scales with (attacker mass / target mass) to
# this power (an assumption; 0.5 means a bite's effect follows body length more than mass).
VENOM_SIZE_EXP = 0.5
# Delay between the last blow and the venom killing a poisoned survivor ("minutes", D-44).
VENOM_ONSET_S = 120.0
# Resistance to venom, from 0 (none) to 1 (immune), by base fighter id; anything not listed has
# none. Each entry carries a one-line reason; G05's real sheets will refine these.
VENOM_RESISTANCE: dict[str, float] = {
    # Honey badgers are famous for shrugging off cobra bites (a long recovery, not death).
    "honey-badger": 0.85,
}

# Loadouts (#283, a proposal pending the PM's decision): each is one choice that leans one way and
# costs something elsewhere, so none is best everywhere. Every number here is an ASSUMPTION, not a
# sourced figure; each loadout changes only attack force, attack rate, top speed and armor, and is
# applied to a sheet by code (simulation/loadouts.py), never by the engine. "armor_add" adds to the
# 0-1 armor value (kept within 0 to 1); the others multiply the sheet's value.
LOADOUTS: dict[str, dict[str, float | str]] = {
    "attack": {
        "label": "an attack loadout",
        "force_mul": 1.5, "rate_mul": 0.8, "speed_mul": 0.95, "armor_add": 0.0,
    },  # a heavier weapon hits harder and slower, and weighs the fighter down a little
    "defense": {
        "label": "a defense loadout",
        "force_mul": 1.0, "rate_mul": 0.9, "speed_mul": 0.9, "armor_add": 0.2,
    },  # armor or a shield blocks more, at the cost of speed and a slower swing
    "speed": {
        "label": "a speed loadout",
        "force_mul": 0.9, "rate_mul": 1.0, "speed_mul": 1.25, "armor_add": -0.1,
    },  # light gear moves faster but protects less and hits a little softer
    "balanced": {
        "label": "a balanced loadout",
        "force_mul": 1.15, "rate_mul": 1.0, "speed_mul": 0.97, "armor_add": 0.08,
    },  # small gains in force and armor for a small loss of speed
}  # fmt: skip

# Loadout tiers (#283): a tier-up deepens a loadout's trade-off instead of just adding strength.
# Tier 1 is the table above; tier t scales every change (the multipliers' distance from 1, and the
# armor addition) by this factor, so the gains grow and so do the costs (ASSUMPTION).
LOADOUT_TIER_SCALE: dict[int, float] = {1: 1.0, 2: 1.4, 3: 1.8}
