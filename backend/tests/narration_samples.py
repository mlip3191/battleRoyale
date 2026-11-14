"""Three sample battles for the announcer writer, shared by its tests and the sample printout.

An animal fight (two hand-verified seed fighters), a machine (a hand-built pickup truck, every
physical stat a labeled category default), and a mythical creature (a hand-built griffin, every
stat an assumption, with lore). The simulation results are hand-built, plausible, and fixed, so
the sample replies below can point at real events. ScriptedChat is a fake ChatLLM that returns
chosen replies per prompt name and records every call; it never touches the network.

The "LLM" replies are hand-written to the tone guide and must pass the writer's own checks.

Print every sample script (the "LLM" ones, then the template fallbacks) for the A06 PR, with no
network and the same output every time; from the repo root:
  uv run --directory backend python -m tests.narration_samples
"""

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.models.narration import Script
from app.models.simulation import EventType, FairFight, FightEvent, SimulationResult
from app.models.stats import StatSheet
from app.narration.writer import write_scripts
from app.providers.base import ChatMessage

SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "fighters"
ASSUMED = "Assumption from the written rubric for this sample fighter."
DEFAULTED = "Category default for a full-size pickup truck (no source found)."


# A real, hand-verified seed sheet by file name, e.g. "gray-wolf".
def seed_sheet(name: str) -> StatSheet:
    return StatSheet.model_validate(json.loads((SEED / f"{name}.json").read_text("utf-8")))


# One estimated stat: no source, low confidence, a +/-50% sampling range, and a note.
def _estimate(value: float, unit: str, method: str, note: str) -> dict[str, Any]:
    return {
        "value": value, "unit": unit, "source": None, "confidence": "low", "is_estimate": True,
        "method": method, "low": value * 0.5, "high": min(value * 1.5, 1.0)
        if unit == "0-1" else value * 1.5, "note": note,
    }  # fmt: skip


def pickup_truck() -> StatSheet:
    """A hand-built machine: physical stats are category defaults, behavior is assumed."""
    physical = {
        "mass_kg": (2500.0, "kg"), "size_m": (5.8, "m"), "top_speed_mps": (44.0, "m/s"),
        "attack_force_n": (20000.0, "N"), "attacks_per_s": (0.2, "1/s"), "reach_m": (0.5, "m"),
        "endurance_s": (3600.0, "s"),
    }  # fmt: skip
    behavior = {"armor_0_1": 0.6, "aggression_0_1": 0.5, "group_tactics_0_1": 0.0}
    stats = {k: _estimate(v, u, "category_default", DEFAULTED) for k, (v, u) in physical.items()}
    stats |= {k: _estimate(v, "0-1", "assumption", ASSUMED) for k, v in behavior.items()}
    return StatSheet.model_validate(
        {
            "fighter_id": "pickup-truck",
            "display_name": "Pickup truck",
            "media_name": "full-size pickup truck",
            "category": "vehicle",
            "body": "machine",
            "habitat": "land",
            "weapons": ["ramming"],
            "lore": None,
            "stats": stats,
            "sheet_hash": "sample-pickup-truck",
        }
    )


def griffin() -> StatSheet:
    """A hand-built mythical creature: lore, and every stat an assumption (an estimate)."""
    values = {
        "mass_kg": (300.0, "kg"), "size_m": (2.5, "m"), "top_speed_mps": (22.0, "m/s"),
        "attack_force_n": (4000.0, "N"), "attacks_per_s": (1.0, "1/s"), "reach_m": (1.2, "m"),
        "armor_0_1": (0.2, "0-1"), "endurance_s": (400.0, "s"), "aggression_0_1": (0.7, "0-1"),
        "group_tactics_0_1": (0.1, "0-1"),
    }  # fmt: skip
    stats = {k: _estimate(v, u, "assumption", ASSUMED) for k, (v, u) in values.items()}
    lore = {
        "body_analog": "lion",
        "size_analog": None,
        "abilities": ["flight"],
        "heads": None,
        "source": {
            "title": "Griffin",
            "url": "https://en.wikipedia.org/wiki/Griffin",
            "quote": "The griffin is a legendary creature with the body, tail, and back legs of "
            "a lion, and the head and wings of an eagle.",
            "retrieved_at": "2026-11-09T07:00:00Z",
            "license": "CC BY-SA 4.0",
        },
    }
    return StatSheet.model_validate(
        {
            "fighter_id": "griffin",
            "display_name": "Griffin",
            "media_name": "winged lion-eagle griffin",
            "category": "mythical",
            "body": "living",
            "habitat": "air",
            "weapons": ["claws", "beak"],
            "lore": lore,
            "stats": stats,
            "sheet_hash": "sample-griffin",
        }
    )


# A compact event: (t, type, side, group_size, hint).
def _log(rows: Sequence[tuple[float, str, int, int, str]]) -> list[FightEvent]:
    return [
        FightEvent(t=t, type=EventType(kind), side=side, group_size=size, text_hint=hint)  # type: ignore[arg-type]
        for t, kind, side, size, hint in rows
    ]


# A fixed SimulationResult (probabilities rounded the way the engine reports them).
def _result(
    win: tuple[float, float],
    outcome: str,
    factor: str,
    duration: float,
    survivors: tuple[float, float],
    log: list[FightEvent],
) -> SimulationResult:
    draw = round(1 - win[0] - win[1], 2)
    ci = tuple((round(p - 0.03, 2), round(p + 0.03, 2)) for p in win)
    return SimulationResult.model_validate(
        {
            "seed": 20261112, "runs": 1000, "win_prob": win, "draw_prob": draw,
            "win_prob_ci95": ci, "mean_survivors": survivors, "mean_duration_s": duration,
            "outcome": outcome, "deciding_factor": factor,
            "deciding_factor_explainer": "Sample result for the narration writer.",
            "representative_log": log,
        }
    )  # fmt: skip


@dataclass(frozen=True)
class Sample:
    """One battle: the inputs to write_scripts plus hand-written model replies."""

    key: str
    title: str
    sheets: tuple[StatSheet, StatSheet]
    result: SimulationResult
    fair: FairFight | None
    counts: tuple[int, int]
    replies: dict[str, dict[str, Any]]
    """Prompt name -> a valid reply ({"lines": [...]})."""


# Shorthand for reply lines.
def _a(text: str, at: int | None = None) -> dict[str, Any]:
    return {"speaker": "announcer", "text": text} | ({} if at is None else {"at_event": at})


def _c(text: str, at: int | None = None) -> dict[str, Any]:
    return {"speaker": "color_commentator", "text": text} | ({} if at is None else {"at_event": at})


def grizzly_vs_gorilla() -> Sample:
    """The animal sample: two hand-verified seed sheets."""
    log = _log([
        (0.0, "approach", 0, 1, "closes in"),
        (0.0, "approach", 1, 1, "closes in"),
        (2.1, "attack", 1, 1, "charges in"),
        (2.6, "miss", 0, 1, "claw swipe misses"),
        (3.4, "hit", 1, 1, "punch lands"),
        (4.0, "hit", 0, 1, "claw swipe lands"),
        (9.5, "retreat", 1, 1, "backs off"),
        (14.2, "approach", 1, 1, "closes in"),
        (18.8, "hit", 0, 1, "bite lands"),
        (22.3, "miss", 1, 1, "punch misses"),
        (30.7, "hit", 0, 1, "shoulder charge lands"),
        (41.5, "ko", 1, 1, "goes down"),
        (41.5, "end", 0, 1, "the fight is over"),
    ])  # fmt: skip
    result = _result((0.71, 0.24), "win_0", "mass_kg", 41.5, (0.81, 0.12), log)
    fair = FairFight(
        varied_side=1, count=3, win_prob_at_count=0.5,
        message="About 3 gorillas make it a coin flip against one grizzly bear.",
    )  # fmt: skip
    intro = [
        _a("Good evening, fight fans! Tonight, fur meets fury in the Battle Royale arena!"),
        _a("In the red corner, 389 kilograms of pure forest management: the Grizzly bear!"),
        _c("That is about 858 pounds. He does not skip leg day. He does not skip any day."),
        _a("And in the blue corner, 140 kilograms of chest-thumping confidence: the Gorilla!"),
        _c(
            "Our best guess puts his top speed at 12 meters per second. An estimate. He wants more."
        ),
        _a("Two heavyweights. One arena. No refunds. Let the science begin!"),
    ]
    pbp = [
        _a("The Grizzly bear lumbers forward like a refrigerator with a grudge.", 0),
        _a("The Gorilla steps up to answer. Here we go!", 1),
        _a("Gorilla charges in early. Bold strategy!", 2),
        _c("The Grizzly bear swings and misses. The air has been defeated, at least.", 3),
        _a("Gorilla connects! A clean punch lands!", 4),
        _a("And the Grizzly bear answers with a claw swipe! That one landed!", 5),
        _c("The Gorilla backs off to reconsider some life choices.", 6),
        _a("He is back! The Gorilla closes in again!", 7),
        _a("Grizzly bear connects again! The momentum has a mailing address now.", 8),
        _c("Gorilla throws a punch at a spot where a bear used to be.", 9),
        _a("Shoulder charge from the Grizzly bear! Like a sofa falling down the stairs!", 10),
        _a("The Gorilla goes down! That is a knockout!", 11),
        _c("And that is the fight. A very productive evening for the bear.", 12),
    ]
    outro = [
        _a("Ladies and gentlemen, your winner: the {winner}!"),
        _c("The {winner} took it {win_pct} of the time across {runs} simulated fights."),
        _a("The deciding factor tonight: {deciding_factor}. You cannot argue with that much bear."),
        _c("{fair_fight}"),
        _a("That's all from the arena. Tip your referees. Good night!"),
    ]
    return Sample(
        key="grizzly-vs-gorilla",
        title="Grizzly bear vs Gorilla (animal)",
        sheets=(seed_sheet("grizzly-bear"), seed_sheet("gorilla")),
        result=result,
        fair=fair,
        counts=(1, 1),
        replies=_replies(intro, pbp, outro),
    )


def truck_vs_wolves() -> Sample:
    """The machine sample: a hand-built pickup truck against a pack of six gray wolves."""
    log = _log([
        (0.0, "approach", 1, 6, "pack closes in"),
        (0.0, "approach", 0, 1, "engine revs"),
        (3.2, "attack", 1, 6, "pack surrounds the truck"),
        (4.1, "hit", 1, 1, "bite on the bumper"),
        (5.0, "hit", 0, 1, "ramming hit lands"),
        (11.6, "retreat", 1, 1, "backs off"),
        (19.3, "miss", 0, 1, "ramming run misses"),
        (24.8, "hit", 1, 1, "bite on the tire"),
        (37.0, "hit", 0, 1, "ramming hit lands"),
        (52.4, "flee", 1, 4, "pack scatters"),
        (52.4, "end", 0, 1, "the fight is over"),
    ])  # fmt: skip
    result = _result((0.83, 0.12), "win_0", "armor_0_1", 52.4, (1.0, 2.1), log)
    fair = FairFight(
        varied_side=1, count=14, win_prob_at_count=0.48,
        message="About 14 gray wolves make it a coin flip against one pickup truck.",
    )  # fmt: skip
    intro = [
        _a("Good evening, fight fans! Tonight it is nature versus horsepower!"),
        _a("In the red corner, an estimated 2,500 kilograms of steel and questionable parking: "
           "the Pickup truck!"),
        _c("Our best guess puts its top speed at 158 kilometers per hour. That is an estimate. "
           "The truck has not commented."),
        _a("And in the blue corner, hunting as a team: the Gray wolf, six of them!"),
        _c("Six wolves. One truck. Somebody call the insurance company."),
        _a("Metal versus fur. Horsepower versus pack power. Let's fight!"),
    ]  # fmt: skip
    pbp = [
        _a("The Gray wolf pack fans out. They have done this before.", 0),
        _a("The Pickup truck revs its engine. It is not here to make friends.", 1),
        _c("The pack surrounds the truck. The truck does not appear to notice.", 2),
        _a("Gray wolf goes for the bumper! A bite lands!", 3),
        _a("Pickup truck answers with a ramming hit! That one landed!", 4),
        _c("One wolf backs off to rethink the whole bumper plan.", 5),
        _a("Pickup truck goes for another ramming run and finds nothing but air.", 6),
        _a("Gray wolf gets the tire! The tire has filed a complaint.", 7),
        _a("Another ramming hit from the Pickup truck! The pack is rattled!", 8),
        _a("The pack has seen enough and heads for the exit!", 9),
        _c("And that is the fight. The truck would like you to know it was never worried.", 10),
    ]
    outro = [
        _a("It's over! Your winner, by way of sheer stubborn steel: the {winner}!"),
        _c("{winner} won {win_pct} of {runs} simulated fights. Very reliable. Low mileage."),
        _a("The deciding factor: {deciding_factor}. Fur is no match for a tailgate."),
        _c("{fair_fight}"),
        _a("That's all from the arena. Drive safe, everybody. Good night!"),
    ]
    return Sample(
        key="truck-vs-wolves",
        title="Pickup truck vs 6 Gray wolves (machine)",
        sheets=(pickup_truck(), seed_sheet("gray-wolf")),
        result=result,
        fair=fair,
        counts=(1, 6),
        replies=_replies(intro, pbp, outro),
    )


def griffin_vs_horse() -> Sample:
    """The mythical sample: a hand-built griffin (legend, all estimates) against a horse."""
    log = _log([
        (0.0, "approach", 0, 1, "takes to the air"),
        (0.0, "approach", 1, 1, "closes in"),
        (3.5, "attack", 0, 1, "dives from above"),
        (3.9, "hit", 0, 1, "talon strike lands"),
        (4.4, "miss", 1, 1, "kick misses"),
        (8.2, "hit", 1, 1, "kick lands"),
        (12.0, "retreat", 0, 1, "circles back up"),
        (17.5, "hit", 0, 1, "talon strike lands"),
        (26.3, "flee", 1, 1, "gallops off"),
        (26.3, "end", 0, 1, "the fight is over"),
    ])  # fmt: skip
    result = _result((0.64, 0.3), "win_0", "abilities", 26.3, (0.92, 0.41), log)
    fair = FairFight(
        varied_side=1, count=2, win_prob_at_count=0.51,
        message="About 2 horses make it a coin flip against one griffin.",
    )  # fmt: skip
    intro = [
        _a("Good evening, fight fans! Tonight, a creature of myth steps into a very real arena."),
        _a("In the red corner, according to legend: part lion, part eagle, all business. "
           "The Griffin!"),
        _c("Legend puts it at an estimated 300 kilograms. Legends are estimates. We checked."),
        _a("And in the blue corner, the pride of the paddock: the Horse!"),
        _c("The Horse tops out at 48 kilometers per hour. No wings. Excellent posture."),
        _a("Feathers versus hooves. Myth versus mane. Let's fight!"),
    ]  # fmt: skip
    pbp = [
        _a("The Griffin takes to the air. According to legend, it does that a lot.", 0),
        _a("The Horse trots in, ears forward. Here we go!", 1),
        _a("The Griffin dives from above!", 2),
        _a("Talon strike lands! The Horse did not see that coming from up there!", 3),
        _c("The Horse kicks and finds only sky. The sky is unbothered.", 4),
        _a("But the Horse connects! A kick lands! That one landed!", 5),
        _c("The Griffin circles back up to think about what just happened.", 6),
        _a("Down it comes again! Another talon strike lands!", 7),
        _a("The Horse has seen enough and gallops for the exit!", 8),
        _c("And that is the fight. The legend lives on. The horse lives on too. Everybody wins.",
           9),
    ]  # fmt: skip
    outro = [
        _a("The myth is real tonight, folks! Your winner: the {winner}!"),
        _c("The {winner} won {win_pct} of the time. Wings: still undefeated as a concept."),
        _a("The deciding factor: {deciding_factor}. Hard to kick what is above you."),
        _c("{fair_fight}"),
        _a("That's all from the arena. Mind the feathers on your way out. Good night!"),
    ]
    return Sample(
        key="griffin-vs-horse",
        title="Griffin vs Horse (mythical)",
        sheets=(griffin(), seed_sheet("horse")),
        result=result,
        fair=fair,
        counts=(1, 1),
        replies=_replies(intro, pbp, outro),
    )


# The three replies keyed by prompt name, as the writer asks for them.
def _replies(intro: list, pbp: list, outro: list) -> dict[str, dict[str, Any]]:
    return {
        "announcer_intro": {"lines": intro},
        "play_by_play": {"lines": pbp},
        "outro": {"lines": outro},
    }


def samples() -> list[Sample]:
    """The three sample battles: animal, machine, mythical."""
    return [grizzly_vs_gorilla(), truck_vs_wolves(), griffin_vs_horse()]


@dataclass
class ScriptedChat:
    """A fake ChatLLM: replies per prompt name, in order (the last one repeats), or raises.

    A reply that is an Exception is raised instead of returned. Every call is recorded.
    """

    replies: dict[str, list[Any]]
    calls: list[tuple[str, list[ChatMessage], dict[str, Any] | None]] = field(default_factory=list)

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        prompt_name: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """The next reply for this prompt name (dicts are sent as JSON text)."""
        self.calls.append((prompt_name, list(messages), json_schema))
        queue = self.replies.get(prompt_name)
        if not queue:
            raise LookupError(f"ScriptedChat has no reply for '{prompt_name}'")
        done = sum(1 for name, _, _ in self.calls if name == prompt_name) - 1
        reply = queue[min(done, len(queue) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)

    def count(self, prompt_name: str) -> int:
        """How many times this prompt was sent."""
        return sum(1 for name, _, _ in self.calls if name == prompt_name)


def sample_chat(sample: Sample) -> ScriptedChat:
    """A fake model that answers each prompt with the sample's hand-written reply."""
    return ScriptedChat({name: [reply] for name, reply in sample.replies.items()})


# --- Printout for the PR ----------------------------------------------------------------------

SPEAKER = {"announcer": "ANNOUNCER", "color_commentator": "COLOR"}


def render(script: Script) -> str:
    """One script as readable text: a heading, then "SPEAKER [event n]: text" per line."""
    head = f"#### {script.kind} (fallback={script.fallback}, {len(script.lines)} lines)"
    rows = []
    for line in script.lines:
        at = f" [event {line.at_event}]" if line.at_event is not None else ""
        rows.append(f"- {SPEAKER[line.speaker]}{at}: {line.text}")
    return "\n".join([head, *rows])


async def print_samples() -> None:
    """Each battle's "LLM" scripts (fake model, real checks), then its template fallbacks."""
    for sample in samples():
        print(f"### {sample.title}\n")
        for label, chat in (("LLM", sample_chat(sample)), ("Template", ScriptedChat({}))):
            print(f"**{label} scripts**\n")
            scripts = await write_scripts(
                sample.sheets, sample.result, sample.fair, chat=chat, counts=sample.counts
            )
            for script in scripts:
                print(render(script) + "\n")


if __name__ == "__main__":
    asyncio.run(print_samples())
