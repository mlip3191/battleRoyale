"""The user's answer to a clarifying question -> a final IntakeResult, with no second question."""

import re

from app.db.intake_pending import PendingQuestion
from app.intake.parser import SIDE_SPLIT, ok_message, parse_matchup, typed_sides
from app.intake.rules import map_terrain
from app.models.matchup import IntakeResult
from app.models.terrain import Terrain
from app.providers.base import ChatLLM

ARTICLES = {"a", "an", "the"}
# Question words that never name a fighter, so "Which type of bear would you like?" -> "bear".
# A filler word missing here is harmless: no single fighter matches, so the answer is just
# appended as before ("bear vs wolf (Grizzly)").
QUESTION_FILLER = {
    *("which", "what", "kind", "type", "sort", "species", "breed", "would", "like", "you"),
    *("are", "about", "talking", "the", "and", "one", "mean", "for", "this", "that", "should"),
}
AND_WORD = re.compile(r"\band\b", re.I)
# With one side typed, these say the question asks for an opponent ("Who should a bear fight?"),
# so the answer is the other side, not a kind of that fighter (#360). Live models word kind
# questions loosely too ("Which species of bear would you like to fight?"), so a fight word only
# counts when the question names no kind.
OPPONENT_WORDS = re.compile(r"\b(?:who|whom|against|opponents?|vs|versus)\b", re.I)
FIGHT_WORDS = re.compile(r"\b(?:fight|fighting|face|battle|take on)\b", re.I)
KIND_WORDS = re.compile(r"\b(?:type|kind|species|breed|sort|variety)\b", re.I)
# A side's trailing place phrase, "6 gray wolves in a forest" -> "in a forest" (#416). Only the
# tail counts, so a place word inside a fighter's name ("sea turtle") is not the battlefield.
TERRAIN_TAIL = re.compile(r"\s+((?:in|on|at|inside|into)\s+.+)$", re.I)
# A bare count answers "How many horses should fight?" (#508): "1", "one", "a dozen", "2 horses".
HOW_MANY = re.compile(r"\bhow\s+many\b", re.I)
NUMBER_WORDS = {
    **{"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7},
    **{"eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "dozen": 12},
    **{"thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17},
    **{"eighteen": 18, "nineteen": 19, "twenty": 20},
}
MAX_COUNT = 10_000  # the most one side can have (Fighter.count in models/matchup.py)
COUNT_ANSWER = re.compile(rf"(?:an?\s+)?(\d+|{'|'.join(NUMBER_WORDS)})(?:\s+(\w+))?", re.I)
# The count words at the start of the asked side that the answer replaces: "half a", "a dozen",
# "2.5", "0". Only these go, so a describing word stays: "half a big horse" -> "3 big horse".
QUANTITY = r"(?:an?|the|half|quarter|third|couple|pair|of|some|few|several|zero|dozen|[\d./]+)"
QUANTITY_HEAD = re.compile(rf"^(?:(?:{QUANTITY}|{'|'.join(NUMBER_WORDS)})\s+)+", re.I)
START_OVER = (
    "Sorry, we still couldn't set up that matchup. Please start again and name two fighters, "
    'like "a grizzly bear vs a gray wolf".'
)


# Fold the answer into the original request, so the parser reads one complete matchup.
# question and options are what was asked: they say which fighter an offered bare variant
# ("Grizzly") belongs to.
def merge_answer(
    original: str, answer: str, question: str = "", options: list[str] | None = None
) -> str:
    original, answer = original.strip(), " ".join(answer.split())
    if not answer:
        return original
    if len(typed_sides(answer)) >= 2:
        return answer  # the answer is a whole matchup, e.g. a suggested "a vs b" option
    counted = _with_count(original, answer, question)
    if counted is not None:
        return counted
    one_side = len(typed_sides(original)) < 2
    if one_side and (_asks_for_opponent(question) or not _offered(answer, options or [])):
        return f"{original} vs {answer}"  # the opponent was missing
    # One side typed and asked "Which bear?": the offered answer names that fighter (#360).
    if AND_WORD.search(answer):
        return f"{original} ({answer})"  # "grizzly bear and wolf" names both sides; don't splice
    *lead, last = answer.split(" ")
    lead = lead[1:] if lead and lead[0].lower() in ARTICLES else lead
    spot = _asked_about(question, original) if _offered(answer, options or []) else None
    if spot and not _same_noun(last, spot.group(0)):
        # "a bear vs a wolf" + "Grizzly", asked "Which bear?" -> "a grizzly bear vs a wolf" (#296).
        # Runs before the last-word splice, so "American Black" never lands on a "black wolf".
        variant = " ".join([*lead, last]).lower()
        return f"{original[: spot.start()]}{variant} {original[spot.start() :]}"
    # "bear vs wolf" + "grizzly bear" -> "grizzly bear vs wolf" (also matches "bears").
    word = re.compile(rf"\b{re.escape(last)}(?:e?s)?\b", re.I)
    matches = list(word.finditer(original))
    if lead and len(matches) == 1:
        lead = _drop_repeated_words(lead, original[: matches[0].start()].split())
        if lead:
            return word.sub(lambda match: " ".join([*lead, match.group(0)]), original, count=1)
    return f"{original} vs {answer}" if one_side else f"{original} ({answer})"


# "half a horse vs ..." + "1", asked "How many horses?" -> "1 horse vs ..." (#508). None when the
# question isn't "how many", the answer isn't a bare count from 1 to MAX_COUNT, or no single
# fighter is asked about; the answer then merges as before.
def _with_count(original: str, answer: str, question: str) -> str | None:
    match = COUNT_ANSWER.fullmatch(answer)
    if not HOW_MANY.search(question) or match is None:
        return None
    asked = _asked_phrase(question)
    noun = match.group(2)
    if noun and not (asked and _same_noun(noun, asked[-1])):
        return None  # "2 wolves" or "2 house" to "How many house cats?" is not this count
    word = match.group(1).lower()
    count = NUMBER_WORDS.get(word) or int(word)
    spot = _asked_about(" ".join(_singulars(asked)), original)
    if spot is None or not 1 <= count <= MAX_COUNT:
        return None
    head = original[: spot.start()]
    sides = list(SIDE_SPLIT.finditer(head))
    start = sides[-1].end() if sides else 0
    describing = QUANTITY_HEAD.sub("", head[start:])
    return f"{head[:start]}{count} {describing}{original[spot.start() :]}"


# The fighter a "How many ___ should fight?" question names: "house cats" -> ["house", "cats"].
def _asked_phrase(question: str) -> list[str]:
    phrase: list[str] = []
    for word in re.findall(r"[A-Za-z]+", HOW_MANY.split(question, 1)[1]):
        if word.lower() in QUESTION_FILLER or FIGHT_WORDS.fullmatch(word):
            break
        phrase.append(word)
    return phrase


# Each word and its singular, so a question's "horses" or "wolves" finds "horse" or "wolf".
def _singulars(words: list[str]) -> list[str]:
    out: list[str] = []
    for word in words:
        lower = word.lower()
        forms = [word]
        if lower.endswith("ves"):
            forms.append(word[:-3] + "f")
        elif lower.endswith("es"):
            forms += [word[:-2], word[:-1]]
        elif lower.endswith("s"):
            forms.append(word[:-1])
        out += forms
    return out


# True if the question asks who to fight, not which kind of the typed fighter (#360).
def _asks_for_opponent(question: str) -> bool:
    if OPPONENT_WORDS.search(question):
        return True
    return bool(FIGHT_WORDS.search(question)) and not KIND_WORDS.search(question)


# True if the answer is one of the offered options ("a Grizzly" matches "Grizzly"); typed
# free text like "the big one" is never spliced into a fighter's name.
def _offered(answer: str, options: list[str]) -> bool:
    def bare(text: str) -> str:
        words = text.lower().split()
        return " ".join(words[1:] if words and words[0] in ARTICLES else words)

    return bare(answer) in {bare(option) for option in options}


# True if two words name the same noun, singular or plural: "bear"/"bears", "wolf"/"wolves".
def _same_noun(a: str, b: str) -> bool:
    return bool(_noun_pattern(a).fullmatch(b) or _noun_pattern(b).fullmatch(a))


# A word and its plurals: "bear" or "bears", "goose", "wolf" or "wolves".
def _noun_pattern(word: str) -> re.Pattern[str]:
    forms = [rf"{re.escape(word)}(?:e?s)?"]
    if word.lower().endswith("f"):
        forms.append(rf"{re.escape(word[:-1])}ves")
    return re.compile(rf"\b(?:{'|'.join(forms)})\b", re.I)


# The fighter the question asks about: its first word that names exactly one spot in the text.
def _asked_about(question: str, original: str) -> re.Match[str] | None:
    for word in re.findall(r"[A-Za-z]+", question):
        if len(word) < 3 or word.lower() in QUESTION_FILLER:
            continue
        spots = list(_noun_pattern(word).finditer(original))
        if len(spots) == 1:
            return spots[0]
    return None


# Drop the answer's leading words that already sit just before the match, e.g. the "3" in
# "3 bears" + "3 grizzly bears", so the merge reads "3 grizzly bears", not "3 3 grizzly bears".
def _drop_repeated_words(lead: list[str], before: list[str]) -> list[str]:
    for size in range(min(len(lead), len(before)), 0, -1):
        if [w.lower() for w in lead[:size]] == [w.lower() for w in before[-size:]]:
            return lead[size:]
    return lead


# Re-parse once with the answer. Still vague -> the parser assumes the most common kind and says
# so in the assumptions. Anything else that isn't a matchup ends with a "start again" message.
async def resolve_answer(pending: PendingQuestion, answer: str, chat: ChatLLM) -> IntakeResult:
    text = merge_answer(pending.original_text, answer, pending.question, pending.options)
    result = await parse_matchup(text, chat=chat, ask=False)
    if result.status == "clarify":
        return IntakeResult(status="blocked", blocked_reason="nonsense", message=START_OVER)
    return _keep_typed_terrain(result, text, pending.original_text)


# The battlefield the user typed in a side's trailing place phrase, or None if no side has one.
def _typed_terrain(text: str) -> tuple[Terrain, str | None] | None:
    for side in typed_sides(text):
        match = TERRAIN_TAIL.search(side)
        if match is not None:
            return map_terrain(match.group(1))
    return None


# The answer only fills in what was asked (#416): when the re-parse falls back to the arena but
# the user typed a battlefield (in the answer first, else the first request), that one is used.
# A non-arena terrain from the re-parse is kept as it is.
def _keep_typed_terrain(result: IntakeResult, text: str, original: str) -> IntakeResult:
    matchup = result.matchup
    if matchup is None or matchup.terrain != Terrain.ARENA:
        return result
    # The answer wins even when it names the arena: the tuple is always truthy, so `or` only
    # falls through to the first request when the answer typed no battlefield at all.
    typed = _typed_terrain(text) or _typed_terrain(original)
    if typed is None or typed[0] == Terrain.ARENA:
        return result
    terrain, note = typed
    notes = list(dict.fromkeys([*matchup.assumptions, *([note] if note else [])]))
    fixed = matchup.model_copy(update={"terrain": terrain, "assumptions": notes})
    return result.model_copy(
        update={"matchup": fixed, "message": ok_message(fixed.fighters, terrain)}
    )
