"""Cited stat sheets: every number says where it came from (the number rule)."""

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, HttpUrl, field_validator, model_validator

from app.models.base import Contract

# Names sent to media prompts: letters, digits, spaces, and hyphens only (prompt-injection guard).
SAFE_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9 -]*[A-Za-z0-9])?")


class Confidence(StrEnum):
    """How much we trust a value."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Source(Contract):
    """Where a number came from: the page and the exact sentence that contains it."""

    title: str
    """Title of the source page, e.g. "Grizzly bear"."""
    url: HttpUrl
    """Link to the source page."""
    quote: str
    """The exact evidence span the value came from, copied word for word."""
    retrieved_at: datetime
    """When the page was fetched."""
    license: str = "CC BY-SA 4.0"
    """License of the quoted text."""


class StatValue(Contract):
    """One number on a stat sheet, with its unit, origin, and uncertainty range."""

    value: float
    """The number itself, in `unit`."""
    unit: str
    """Unit of the value, e.g. "kg" or "m/s"."""
    source: Source | None = None
    """The page and quote it came from; None for estimates."""
    confidence: Confidence
    """How much we trust it; always low for estimates."""
    is_estimate: bool
    """True when the value is not from a source (method category_default or assumption)."""
    method: Literal["extracted", "derived", "category_default", "hand_verified", "assumption"]
    """How it was produced: extracted = copied with a verified quote; derived = computed by code
    from other stats; category_default = code default when no evidence was found; hand_verified =
    checked by a teammate (seed fighters); assumption = from the written rubric."""
    low: float | None = None
    """Bottom of the plausible range used for uncertainty sampling (filled by code)."""
    high: float | None = None
    """Top of the plausible range used for uncertainty sampling (filled by code)."""
    note: str | None = None
    """Required for derived (which formula) and assumption (the rubric level and why)."""

    # Enforce the number rule for a single value (see ARCHITECTURE "The number rule").
    @model_validator(mode="after")
    def _check_number_rule(self) -> Self:
        estimate_methods = ("category_default", "assumption")
        if self.is_estimate != (self.method in estimate_methods):
            raise ValueError("is_estimate must be True exactly when method is an estimate method")
        if self.is_estimate and (self.source is not None or self.confidence != Confidence.LOW):
            raise ValueError("an estimate has no source and low confidence")
        if self.method in ("extracted", "hand_verified") and (
            self.source is None or not self.source.quote.strip()
        ):
            raise ValueError(f"method {self.method} needs a source with a non-empty quote")
        if self.method in ("assumption", "derived") and not (self.note and self.note.strip()):
            raise ValueError(f"method {self.method} needs a non-empty note")
        if self.low is not None and self.low > self.value:
            raise ValueError("low must be <= value")
        if self.high is not None and self.value > self.high:
            raise ValueError("value must be <= high")
        return self


class StatName(StrEnum):
    """The ten stats every fighter has."""

    MASS = "mass_kg"
    SIZE = "size_m"
    SPEED = "top_speed_mps"
    ATTACK_FORCE = "attack_force_n"
    ATTACK_RATE = "attacks_per_s"
    REACH = "reach_m"
    ARMOR = "armor_0_1"
    ENDURANCE = "endurance_s"
    AGGRESSION = "aggression_0_1"
    GROUP_TACTICS = "group_tactics_0_1"


# Behavioral stats no source measures; the only ones a non-mythical fighter may assume.
ASSUMABLE_STATS = frozenset({StatName.AGGRESSION, StatName.GROUP_TACTICS, StatName.ARMOR})


class Habitat(StrEnum):
    """Where the fighter can move."""

    LAND = "land"
    WATER = "water"
    AIR = "air"
    AMPHIBIOUS = "amphibious"


class Body(StrEnum):
    """How it fights, not its biology."""

    LIVING = "living"
    """Animals, human archetypes, mythical creatures: tire, have morale, can retreat or flee."""
    MACHINE = "machine"
    """Vehicles and robots: no morale (never retreat); stop when endurance_s runs out."""
    INERT = "inert"
    """Objects and plants: never move toward anyone; hit back only with an attack in reach."""


class Ability(StrEnum):
    """Special powers of mythical creatures; each has one documented engine effect."""

    FLIGHT = "flight"
    BREATH_WEAPON = "breath_weapon"
    REGENERATION = "regeneration"
    EXTRA_HEADS = "extra_heads"


class LoreProfile(Contract):
    """How a mythical creature is modeled on real animals, according to legend."""

    body_analog: str
    """Real fighter whose sourced stats are the base, e.g. "saltwater crocodile"."""
    size_analog: str | None = None
    """Real fighter it is scaled to, e.g. "African elephant"; code computes the scale factor."""
    abilities: list[Ability] = []
    """Its legendary powers."""
    heads: int | None = Field(None, ge=2, le=9)
    """Number of heads (2-9), only with the extra_heads ability and a quote that says so."""
    source: Source
    """The sentence in the myth's article that justifies the analogs and abilities."""

    # A head count only makes sense for a creature with the extra_heads ability.
    @model_validator(mode="after")
    def _heads_need_extra_heads(self) -> Self:
        if self.heads is not None and Ability.EXTRA_HEADS not in self.abilities:
            raise ValueError("heads is only allowed with the extra_heads ability")
        return self


class StatSheet(Contract):
    """Everything the simulation knows about one fighter, with a source for every number."""

    fighter_id: str
    """Stable slug, e.g. "grizzly-bear"; a non-default variant adds "--variant"."""
    display_name: str
    """Name shown to users and used in narration (letters, digits, spaces, hyphens)."""
    media_name: str
    """Generic, brand-free name used in image and music prompts, e.g. "electric pickup truck"
    (letters, digits, spaces, hyphens)."""
    category: Literal[
        "mammal",
        "bird",
        "reptile",
        "amphibian",
        "fish",
        "insect",
        "arachnid",
        "mollusk",
        "dinosaur",
        "human_archetype",
        "mythical",
        "plant",
        "vehicle",
        "machine",
        "object",
        "other",
    ]
    """What kind of thing it is."""
    body: Body
    """How it fights: living, machine, or inert."""
    habitat: Habitat
    """Where it can move."""
    weapons: list[
        Literal[
            "teeth",
            "claws",
            "horns",
            "hooves",
            "venom",
            "constriction",
            "tusks",
            "beak",
            "sting",
            "weapon_melee",
            "weapon_ranged",
            "ramming",
            "crushing",
            "spines",
            "breath_weapon",
            "none",
        ]
    ]
    """How it attacks."""
    lore: LoreProfile | None = None
    """Required when category is mythical, otherwise None."""
    stats: dict[StatName, StatValue]
    """Every StatName with its value."""
    schema_version: int = 1
    """Version of this shape, for cached sheets."""
    sheet_hash: str
    """Hash of the stats, used in the cache key and the simulation seed."""

    # Names that reach media prompts may only contain allowlisted characters.
    @field_validator("display_name", "media_name")
    @classmethod
    def _allowlisted_name(cls, value: str) -> str:
        if not SAFE_NAME.fullmatch(value):
            raise ValueError("names may only contain letters, digits, spaces, and hyphens")
        return value

    # Cross-field rules: complete stats, lore only for mythical, assumptions only where allowed.
    @model_validator(mode="after")
    def _check_sheet(self) -> Self:
        missing = [name.value for name in StatName if name not in self.stats]
        if missing:
            raise ValueError(f"stats is missing {', '.join(missing)}")
        mythical = self.category == "mythical"
        if mythical != (self.lore is not None):
            raise ValueError("lore is required for mythical fighters and only for them")
        for name, stat in self.stats.items():
            if mythical and stat.method != "assumption":
                raise ValueError(f"every stat of a mythical fighter is an assumption ({name})")
            if stat.method == "assumption" and not mythical and name not in ASSUMABLE_STATS:
                raise ValueError(f"{name} cannot be an assumption for a non-mythical fighter")
        return self
