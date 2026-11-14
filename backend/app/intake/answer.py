"""The user's answer to a clarifying question -> a final IntakeResult, with no second question."""

import re

from app.db.intake_pending import PendingQuestion
from app.intake.parser import parse_matchup, typed_sides
from app.models.matchup import IntakeResult
from app.providers.base import ChatLLM

ARTICLES = {"a", "an", "the"}
# Question words that never name a fighter, so "Which type of bear would you like?" -> "bear".
QUESTION_FILLER = {
    *("which", "what", "kind", "type", "sort", "species", "breed", "would", "like", "you"),
    *("are", "about", "talking", "the", "and", "one", "mean", "for", "this", "that", "should"),
}
AND_WORD = re.compile(r"\band\b", re.I)
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
    if len(typed_sides(original)) < 2:
        return f"{original} vs {answer}"  # the opponent was missing
    if AND_WORD.search(answer):
        return f"{original} ({answer})"  # "grizzly bear and wolf" names both sides; don't splice
    *lead, last = answer.split(" ")
    lead = lead[1:] if lead and lead[0].lower() in ARTICLES else lead
    # "bear vs wolf" + "grizzly bear" -> "grizzly bear vs wolf" (also matches "bears").
    word = re.compile(rf"\b{re.escape(last)}(?:e?s)?\b", re.I)
    matches = list(word.finditer(original))
    if lead and len(matches) == 1:
        lead = _drop_repeated_words(lead, original[: matches[0].start()].split())
        if lead:
            return word.sub(lambda match: " ".join([*lead, match.group(0)]), original, count=1)
    if not matches and _offered(answer, options or []):
        # "a bear vs a wolf" + "Grizzly", asked "Which bear?" -> "a grizzly bear vs a wolf" (#296).
        spot = _asked_about(question, original)
        if spot:
            variant = " ".join([*lead, last]).lower()
            return f"{original[: spot.start()]}{variant} {original[spot.start() :]}"
    return f"{original} ({answer})"


# True if the answer is one of the offered options ("a Grizzly" matches "Grizzly"); typed
# free text like "the big one" is never spliced into a fighter's name.
def _offered(answer: str, options: list[str]) -> bool:
    def bare(text: str) -> str:
        words = text.lower().split()
        return " ".join(words[1:] if words and words[0] in ARTICLES else words)

    return bare(answer) in {bare(option) for option in options}


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
    return result
