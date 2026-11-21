"""The all-estimate sheet for a plausible fighter we have no sheet for (#345).

When research finds no seed sheet, cached sheet, built sheet, or legend for a fighter, the battle
still runs on this sheet instead of failing. Every number comes from code: `build_stat_sheet`
with no stored facts and no model extraction, so each physical stat is its category default
(defaults.py) and each behavioral stat is its rubric assumption. No model sets any number.

The category is "other" because nothing in code says what kind of thing an unknown fighter is:
FighterRequest carries no category, and choosing one from the name would need a model. So the
fighter is treated like the seed list's objects (an inert body on land with no weapon), and
every stat is labeled `is_estimate` with a note saying so. The one signal code does have is the
legend lookup's fixed reason (#453, #444): `real_animal` gives a living mammal and `generic_kind`
a living human archetype (see `estimate_sheet`); an object, mock mode or no reason stays inert.
This sheet is never cached in the sheet store, so a later real sheet for the same name isn't
shadowed by it.
"""

import re

from app.models.stats import StatName, StatSheet, StatValue
from app.research.defaults import category_default
from app.research.ranges import range_for
from app.research.seed_fighters import fighter_slug
from app.research.sheet_hash import compute_sheet_hash
from app.research.statsheet import FighterProfile, build_stat_sheet, media_name_for

ESTIMATE_CATEGORY = "other"  # no code-level signal for an unknown fighter's category
ESTIMATE_BODY = "inert"  # how docs/research.md treats "object, other": never moves, no attack
ESTIMATE_HABITAT = "land"
ESTIMATE_WEAPONS = ("none",)
UNKNOWN_NAME = "Unknown fighter"  # when nothing in the typed name is a letter or digit
ESTIMATE_NOTE = "Estimate: we have no stat sheet for this fighter. "
# A fighter the legend lookup calls a real animal (#453) is a living land mammal with a bite, built
# from the mammal defaults. The reason is one of a fixed list the model picks; code decides from
# it alone, so no model text or number reaches the sheet. Anything else stays the inert object.
ANIMAL_REASON = "real_animal"
ESTIMATE_ANIMAL_CATEGORY = "mammal"
ESTIMATE_ANIMAL_BODY = "living"
ESTIMATE_ANIMAL_WEAPONS = ("teeth",)
# A generic kind of human or supernatural being the lookup does not call a legend (#444: a priest, a
# samurai, "a god") is a living, human-sized fighter built from the human archetype defaults.
GENERIC_KIND_REASON = "generic_kind"
ESTIMATE_GENERIC_CATEGORY = "human_archetype"
# D-69: a god of mythology (Zeus, Thor) fights like a generic kind, with no special powers yet, and
# a military unit (US Navy SEALs) is a human archetype with a firearm: a ranged attack whose
# reach, force and rate are these judgment values, labeled estimates like every other stat here.
MYTH_DEITY_REASON = "myth_deity"
ARMED_UNIT_REASON = "armed_unit"
HUMAN_REASONS = frozenset({GENERIC_KIND_REASON, MYTH_DEITY_REASON, ARMED_UNIT_REASON})
ARMED_WEAPONS = ("weapon_ranged",)
FIREARM_NOTE = "Firearm assumption (D-69): a judgment value for a rifle, not a sourced number. "
FIREARM_STATS = {
    StatName.REACH: 300.0,  # m: fires from the opening distance (10 m) onward
    StatName.ATTACK_FORCE: 7000.0,  # N-equivalent: about two hits stop a 70 kg human
    StatName.ATTACK_RATE: 1.0,  # aimed shots per second
}


# The all-estimate sheet for `name` (the fighter as the user typed it, e.g. "wolverine"). `kind` is
# the legend lookup's fixed reason when it has one: "real_animal" gives a living animal, and
# anything else (an object, mock mode, no reason) the inert object, as before.
def estimate_sheet(name: str, kind: str | None = None) -> StatSheet:
    display = display_name_for(name)
    animal = kind == ANIMAL_REASON
    generic = kind in HUMAN_REASONS
    armed = kind == ARMED_UNIT_REASON
    living = animal or generic
    category = (
        ESTIMATE_ANIMAL_CATEGORY
        if animal
        else ESTIMATE_GENERIC_CATEGORY
        if generic
        else ESTIMATE_CATEGORY
    )
    profile = FighterProfile(
        fighter_id=fighter_slug(display),
        display_name=display,
        media_name=media_name_for(display, category),
        category=category,
        body=ESTIMATE_ANIMAL_BODY if living else ESTIMATE_BODY,
        habitat=ESTIMATE_HABITAT,
        weapons=ESTIMATE_ANIMAL_WEAPONS if animal else ARMED_WEAPONS if armed else ESTIMATE_WEAPONS,
    )
    built = build_stat_sheet(profile)  # no facts, no extraction: code defaults only
    stats = {
        stat: _labeled(_as_default(value, category, stat)) for stat, value in built.stats.items()
    }
    if armed:
        stats.update({stat: _firearm(stat, stats[stat], v) for stat, v in FIREARM_STATS.items()})
    not_estimates = [str(stat) for stat, value in stats.items() if not value.is_estimate]
    if not_estimates:  # the "other" defaults never derive, so this would be a code change
        raise ValueError(f"estimate sheet has non-estimate stats: {', '.join(not_estimates)}")
    return StatSheet.model_validate(
        {**built.model_dump(), "stats": stats, "sheet_hash": compute_sheet_hash(stats)}
    )


# A display name the StatSheet allowlist accepts: letters, digits, spaces, and hyphens only,
# with the first letter capitalized like the seed list ("Wolverine", "Polar bear").
def display_name_for(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 -]+", " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    if not cleaned:
        return UNKNOWN_NAME
    return cleaned[:1].upper() + cleaned[1:]


# A value code derived from another estimate (a living animal's reach) becomes the category
# default instead, so every physical stat of the sheet is a labeled estimate.
def _as_default(value: StatValue, category: str, stat: StatName) -> StatValue:
    if value.is_estimate:
        return value
    # `or value` keeps a non-estimate only if a default were ever missing; estimate_sheet's guard
    # then raises, so a non-estimate can never reach a saved sheet.
    return category_default(category, stat) or value


# A human estimate's stat replaced by the firearm value, still a labeled estimate (D-69).
def _firearm(stat: StatName, value: StatValue, firearm: float) -> StatValue:
    low, high = range_for(stat, firearm, value.confidence)  # the same spread as any estimate
    return value.model_copy(
        update={"value": firearm, "low": low, "high": high, "note": ESTIMATE_NOTE + FIREARM_NOTE}
    )


# The same estimate, with a note that says plainly it is one.
def _labeled(value: StatValue) -> StatValue:
    return value.model_copy(update={"note": ESTIMATE_NOTE + (value.note or "")})
