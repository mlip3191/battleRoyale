"""Every number the fight engine uses that is not a stat on a sheet.

Each constant has a comment; docs/simulation-model.md gives its source or labels it an assumption.
Change a value here and the results change, so bump ENGINE_VERSION in the same commit.
"""

# Part of the random seed, so a new engine never silently reproduces an old battle.
ENGINE_VERSION = 1

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
