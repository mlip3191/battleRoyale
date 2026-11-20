"""Research sections of the live AI evaluation (M09, #51): extraction accuracy and coverage.

Imported by scripts/evaluate_ai.py; live mode only, never in CI. The scoring and Markdown helpers
are plain functions, so the tests check them without any endpoint.
"""

import asyncio
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from app.models.stats import ASSUMABLE_STATS, StatName, StatSheet, StatValue
from app.research.seed_fighters import SeedFighter

SEED_SHEETS = Path(__file__).resolve().parents[2] / "data" / "seed" / "fighters"
PHYSICAL = [s for s in StatName if s not in ASSUMABLE_STATS]
SOURCED = ("extracted", "hand_verified")
# Coverage fighters (M09 item 3), approved by Mike on #51: none is on the seed list or in
# mythical.yaml. In the app the non-mythical ones fight on all-estimate sheets (#345, #453), so
# the evaluation gives each a profile here and runs the same research pipeline on its article.
NEW_FIGHTERS = [
    SeedFighter("moose", "Moose", "Adult bull", "mammal", "living", "land", "Moose"),
    SeedFighter("polar-bear", "Polar bear", "Adult male", "mammal", "living", "land", "Polar bear"),
    SeedFighter("cheetah", "Cheetah", "Adult", "mammal", "living", "land", "Cheetah"),
    SeedFighter(
        "komodo-dragon", "Komodo dragon", "Adult male", "reptile", "living", "land", "Komodo dragon"
    ),
    SeedFighter(
        "red-kangaroo", "Red kangaroo", "Adult male", "mammal", "living", "land", "Red kangaroo"
    ),
    SeedFighter(
        "forklift", "Forklift", "Counterbalance forklift", "vehicle", "machine", "land", "Forklift"
    ),
    SeedFighter(
        "lawn-mower", "Lawn mower", "Push mower", "machine", "machine", "land", "Lawn mower"
    ),
    SeedFighter(
        "vending-machine",
        "Vending machine",
        "Drinks machine",
        "object",
        "inert",
        "land",
        "Vending machine",
    ),
]
NEW_LEGENDS = ["hippogriff", "cockatrice"]
# An overall deadline per fighter, as the app's stage budgets give it: the HTTP client's timeout
# covers each step of a request, not the whole thing, so a stalled call could otherwise hang.
FIGHTER_LIMIT_S = 180.0


class RejectCounter(logging.Handler):
    """Counts extraction's "Rejected ..." warnings, and the quote-check ones among them."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.rejected = 0
        self.quote = 0

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if message.startswith("Rejected"):
            self.rejected += 1
            self.quote += "number not in quote" in message


# Where a research-only value lands against the hand-verified one.
def classify(research: StatValue, truth: float) -> str:
    if research.is_estimate:
        return "estimate"
    off = abs(research.value - truth) / abs(truth) if truth else abs(research.value)
    return "within 10%" if off <= 0.10 else "within 25%" if off <= 0.25 else "wrong"


BUCKETS = ("within 10%", "within 25%", "wrong", "estimate")


@dataclass
class Extraction:
    """Per-stat tallies of research-only values against hand-verified ones."""

    tally: dict[str, Counter[str]] = field(default_factory=dict)
    wrong: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    fighters: int = 0
    rejected: int = 0
    quote_rejected: int = 0

    # Score every hand-verified stat of one fighter.
    def add(self, truth: StatSheet, research: StatSheet) -> None:
        self.fighters += 1
        for stat, value in truth.stats.items():
            if value.method != "hand_verified" or stat not in research.stats:
                continue
            bucket = classify(research.stats[stat], value.value)
            self.tally.setdefault(stat.value, Counter())[bucket] += 1
            if bucket == "wrong":
                self.wrong.append(
                    f"{truth.display_name} {stat.value}: research {research.stats[stat].value:g}, "
                    f"hand-verified {value.value:g}"
                )


# The extraction section's Markdown.
def extraction_markdown(result: Extraction, seconds: float) -> str:
    rows = ["| Stat | " + " | ".join(BUCKETS) + " |", "|---|" + "---|" * len(BUCKETS)]
    total: Counter[str] = Counter()
    for stat in sorted(result.tally):
        counts = result.tally[stat]
        total.update(counts)
        rows.append(f"| {stat} | " + " | ".join(str(counts[b]) for b in BUCKETS) + " |")
    n = sum(total.values())
    rows.append(
        "| **All** | "
        + " | ".join(f"**{total[b]} ({total[b] / n:.0%})**" if n else "0" for b in BUCKETS)
        + " |"
    )
    out = [
        f"Each of the {result.fighters} hand-verified seed fighters was built again by the "
        "research pipeline alone (stored facts, then model extraction with verified quotes), "
        f"ignoring its seed file, and every hand-verified stat was compared ({n} values, "
        f"{seconds:.0f} s).",
        "",
        *rows,
        "",
        f"Extraction answers rejected by code: {result.rejected}, of which "
        f"{result.quote_rejected} failed the quote check (the number wasn't in the quote, or the "
        "quote wasn't in the passage). A rejected answer leaves the stat to a later level, so it "
        "shows up above as an estimate, never as a made-up number.",
        "",
        "Research does not use the fighter's variant (sex, age, or which speed), so some \"more "
        "than 25% off\" values compare different things, for example the lion's mass or the bald "
        "eagle's dive speed.",
    ]
    if result.wrong:
        out += ["", "More than 25% off:", *[f"- {line}" for line in result.wrong]]
    if result.failed:
        out += ["", "Couldn't be built:", *[f"- {line}" for line in result.failed]]
    return "\n".join(out)


# How a sheet's 7 physical stats were filled: sourced, derived, estimate or assumption.
def coverage_of(sheet: StatSheet) -> Counter[str]:
    kinds: Counter[str] = Counter()
    for stat in PHYSICAL:
        value = sheet.stats.get(stat)
        if value is None:
            continue
        method = value.method
        kinds[
            "sourced"
            if method in SOURCED
            else "estimate"
            if method == "category_default"
            else method
        ] += 1
    return kinds


# The coverage section's Markdown: one row per fighter, then the legends' analogs.
def coverage_markdown(
    rows: list[tuple[str, str, Counter[str] | str]], analogs: list[str], seconds: float
) -> str:
    kinds = ("sourced", "derived", "estimate", "assumption")
    table = ["| Fighter | Kind | " + " | ".join(kinds) + " |", "|---|---|" + "---|" * len(kinds)]
    for name, kind, counts in rows:
        if isinstance(counts, str):
            table.append(f"| {name} | {kind} | {counts} |" + " |" * (len(kinds) - 1))
        else:
            table.append(f"| {name} | {kind} | " + " | ".join(str(counts[k]) for k in kinds) + " |")
    out = [
        f"Ten fighters on neither the seed list nor `mythical.yaml` (5 animals, 3 objects or "
        f"machines, 2 mythical creatures; {seconds:.0f} s). Counts are the 7 physical stats.",
        "",
        "**Research only builds sheets for seed-list fighters**, so in the app the 8 "
        "non-mythical ones fight on all-estimate sheets: a real animal as a living fighter on "
        "its category's defaults (#441, #453), an object or machine as an inert one (#345). "
        "So their article was fetched on demand and run through the same pipeline here, to show "
        "what research could add for them. The two mythical creatures went through the app's "
        "real legend path.",
        "",
        *table,
    ]
    if analogs:
        out += [
            "",
            "Mythical analogs (the real animal each legend is modeled on; judge whether they fit):",
            *[f"- {line}" for line in analogs],
        ]
    return "\n".join(out)


# Build every hand-verified seed fighter from research alone and compare (live).
async def run_extraction() -> str:
    from app.db.connection import connect
    from app.db.migrate import apply_migrations
    from app.providers.registry import get_provider
    from app.research.extract import build_sheet_with_evidence
    from app.research.seed_fighters import find_seed_fighter
    from app.research.statsheet import profile_from_seed

    providers = (get_provider("chat"), get_provider("embedder"), get_provider("reranker"))
    counter, result = RejectCounter(), Extraction()
    extract_log = logging.getLogger("app.research.extract")
    extract_log.addHandler(counter)
    connection, started = connect(), time.perf_counter()
    try:
        apply_migrations(connection)
        for path in sorted(SEED_SHEETS.glob("*.json")):
            truth = StatSheet.model_validate_json(path.read_text("utf-8"))
            fighter = find_seed_fighter(truth.fighter_id)
            if fighter is None:
                result.failed.append(f"{truth.display_name}: not on the seed list")
                continue
            try:
                built = await asyncio.wait_for(
                    build_sheet_with_evidence(connection, providers, profile_from_seed(fighter)),
                    FIGHTER_LIMIT_S,
                )
            except Exception as error:  # noqa: BLE001 - one fighter's failure is reported, not fatal
                result.failed.append(f"{truth.display_name}: {type(error).__name__}")
                continue
            result.add(truth, built)
    finally:
        extract_log.removeHandler(counter)
        connection.close()
    result.rejected, result.quote_rejected = counter.rejected, counter.quote
    return extraction_markdown(result, time.perf_counter() - started)


# Research the ten new fighters (live): the 8 others via their articles, the 2 legends via the app.
async def run_coverage() -> str:
    import httpx

    from app.db.connection import connect
    from app.db.migrate import apply_migrations
    from app.providers.registry import get_provider
    from app.research.extract import build_sheet_with_evidence
    from app.research.ingest import ingest_on_demand
    from app.research.sheet_store import resolve_legend
    from app.research.statsheet import profile_from_seed

    chat, embedder = get_provider("chat"), get_provider("embedder")
    providers = (chat, embedder, get_provider("reranker"))
    rows: list[tuple[str, str, Counter[str] | str]] = []
    analogs: list[str] = []
    connection, started = connect(), time.perf_counter()
    try:
        apply_migrations(connection)
        async with httpx.AsyncClient(timeout=15.0) as client:
            for fighter in NEW_FIGHTERS:
                kind = "animal" if fighter.body == "living" else "object or machine"
                try:
                    stored = await asyncio.wait_for(
                        ingest_on_demand(
                            connection,
                            client,
                            get_provider("doc_parser"),
                            embedder,
                            fighter.id,
                            fighter.article,
                        ),
                        FIGHTER_LIMIT_S,
                    )
                    if not stored:
                        rows.append((fighter.display_name, kind, "article not stored"))
                        continue
                    sheet = await asyncio.wait_for(
                        build_sheet_with_evidence(
                            connection, providers, profile_from_seed(fighter)
                        ),
                        FIGHTER_LIMIT_S,
                    )
                    rows.append((fighter.display_name, kind, coverage_of(sheet)))
                except Exception as error:  # noqa: BLE001 - reported per fighter
                    rows.append((fighter.display_name, kind, f"failed ({type(error).__name__})"))
        for name in NEW_LEGENDS:
            try:
                found = await asyncio.wait_for(
                    resolve_legend(connection, chat, name), FIGHTER_LIMIT_S
                )
            except Exception as error:  # noqa: BLE001 - reported per legend
                found = None
                rows.append((name, "mythical", f"failed ({type(error).__name__})"))
                continue
            if isinstance(found, StatSheet) and found.lore is not None:
                rows.append((found.display_name, "mythical", coverage_of(found)))
                size = f", scaled to a {found.lore.size_analog}" if found.lore.size_analog else ""
                analogs.append(f"{found.display_name}: built on a {found.lore.body_analog}{size}")
            else:  # None is "not a legend" (#403) or mock mode; an outcome says refused or down
                blocked = getattr(found, "blocked", False)
                label = "refused" if blocked else "unavailable" if found else "not a legend"
                rows.append((name, "mythical", label))
    finally:
        connection.close()
    return coverage_markdown(rows, analogs, time.perf_counter() - started)
