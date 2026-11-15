"""SafetyVerdict (internal to safety, not a contract) and the friendly message per block reason."""

from dataclasses import dataclass
from typing import Literal, get_args

from app.models.matchup import IntakeResult

# The contract's blocked_reason values (IntakeResult); a unit test keeps the two lists equal.
BlockedReason = Literal[
    "real_person",
    "minor",
    "sexual",
    "hate",
    "self_harm",
    "copyrighted_character",
    "deity",
    "weapon",
    "out_of_scope",
    "nonsense",
    "other",
]
BLOCKED_REASONS: tuple[str, ...] = get_args(BlockedReason)
# Which safety layer decided (internal: tests and logs only).
Layer = Literal["rules", "classifier", "wikidata"]

# What the user sees for each reason: friendly, never preachy, with something to try instead.
MESSAGES: dict[str, str] = {
    "real_person": (
        "We keep real people out of the ring. Try a type of fighter instead, like "
        '"a Roman legionary" or "a medieval knight".'
    ),
    "minor": (
        "Kids get front-row seats, not a spot in the ring! Try an animal, a machine, or a "
        'grown-up type like "a samurai".'
    ),
    "hate": (
        "We don't pit groups of people against each other. Pick an animal, a machine, or one "
        'fighter type like "a Viking".'
    ),
    "sexual": "Let's keep it family-friendly. How about two animals instead?",
    "self_harm": (
        "That one's not for the ring. If you're going through a rough time, please reach out to "
        "someone you trust or a local crisis line. We'll be right here when you want a goose fight."
    ),
    "copyrighted_character": (
        "Named characters belong to their creators, so they can't step in. Try a creature type "
        'instead, like "a dragon" or "a giant robot".'
    ),
    "deity": 'Gods are above our pay grade. Try a mythical creature, like "a griffin", instead.',
    "weapon": (
        "No firearms or explosives in this arena. Vehicles and machines are welcome, like "
        '"a bulldozer".'
    ),
    "out_of_scope": (
        "That can't exactly throw a punch! Try something physical: an animal, an object, or a "
        "machine."
    ),
    "nonsense": (
        "We couldn't find a fighter in there. Try something like "
        '"a grizzly bear vs 6 gray wolves".'
    ),
    "other": "We can't run that matchup. Try two animals, objects, or machines instead.",
}


@dataclass(frozen=True)
class SafetyVerdict:
    """Whether a request may go on to research, and if not, why."""

    allowed: bool
    reason: BlockedReason | None = None
    """One of the contract's blocked_reason values when blocked."""
    layer: Layer | None = None
    """Which layer blocked it (for tests and logs; never shown to the user)."""

    @property
    def message(self) -> str | None:
        """The friendly text for the user, or None when allowed."""
        return MESSAGES[self.reason] if self.reason else None


ALLOWED = SafetyVerdict(allowed=True)


# A blocked verdict from one layer.
def blocked(reason: BlockedReason, layer: Layer) -> SafetyVerdict:
    return SafetyVerdict(allowed=False, reason=reason, layer=layer)


# A blocked verdict as the IntakeResult the front end shows (status "blocked").
def blocked_result(verdict: SafetyVerdict) -> IntakeResult:
    if verdict.allowed or verdict.reason is None:
        raise ValueError("blocked_result needs a blocked verdict.")
    return IntakeResult(status="blocked", blocked_reason=verdict.reason, message=verdict.message)
