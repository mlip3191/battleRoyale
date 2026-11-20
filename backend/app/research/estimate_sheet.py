"""The all-estimate sheet for a plausible fighter we have no sheet for (#345).

When research finds no seed sheet, cached sheet, built sheet, or legend for a fighter, the battle
still runs on this sheet instead of failing. Every number comes from code: `build_stat_sheet`
with no stored facts and no model extraction, so each physical stat is its category default
(defaults.py) and each behavioral stat is its rubric assumption. No model sets any number.

The category is "other" because nothing in code says what kind of thing an unknown fighter is:
FighterRequest carries no category, and choosing one from the name would need a model. So the
fighter is treated like the seed list's objects (an inert body on land with no weapon), and
every stat is labeled `is_estimate` with a note saying so. This sheet is never cached in the
sheet store, so a later real sheet for the same name isn't shadowed by it.
"""

import re

from app.models.stats import StatName, StatSheet, StatValue
from app.research.defaults import category_default
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


# The all-estimate sheet for `name` (the fighter as the user typed it, e.g. "wolverine"). `kind` is
# the legend lookup's fixed reason when it has one: "real_animal" gives a living animal, and
# anything else (an object, mock mode, no reason) the inert object, as before.
def estimate_sheet(name: str, kind: str | None = None) -> StatSheet:
    display = display_name_for(name)
    animal = kind == ANIMAL_REASON
    category = ESTIMATE_ANIMAL_CATEGORY if animal else ESTIMATE_CATEGORY
    profile = FighterProfile(
        fighter_id=fighter_slug(display),
        display_name=display,
        media_name=media_name_for(display, category),
        category=category,
        body=ESTIMATE_ANIMAL_BODY if animal else ESTIMATE_BODY,
        habitat=ESTIMATE_HABITAT,
        weapons=ESTIMATE_ANIMAL_WEAPONS if animal else ESTIMATE_WEAPONS,
    )
    built = build_stat_sheet(profile)  # no facts, no extraction: code defaults only
    stats = {
        stat: _labeled(_as_default(value, category, stat)) for stat, value in built.stats.items()
    }
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
    return category_default(category, stat) or value


# The same estimate, with a note that says plainly it is one.
def _labeled(value: StatValue) -> StatValue:
    return value.model_copy(update={"note": ESTIMATE_NOTE + (value.note or "")})
