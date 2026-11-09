"""Every number the fight engine uses that is not a stat on a sheet.

Each constant has a comment; docs/simulation-model.md gives its source or labels it an assumption.
Change a value here and the results change, so bump ENGINE_VERSION in the same commit.
"""

# Part of the random seed, so a new engine never silently reproduces an old battle.
ENGINE_VERSION = 5

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
# Log slots kept free at the end for the closing events (a stalemate and the end).
CLOSING_EVENTS = 2

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
