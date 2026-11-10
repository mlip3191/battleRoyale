"""The user's answer to a clarifying question -> a final IntakeResult, with no second question."""

import re

from app.db.intake_pending import PendingQuestion
from app.intake.parser import parse_matchup, typed_sides
from app.models.matchup import IntakeResult
from app.providers.base import ChatLLM

ARTICLES = {"a", "an", "the"}
START_OVER = (
    "Sorry, we still couldn't set up that matchup. Please start again and name two fighters, "
    'like "a grizzly bear vs a gray wolf".'
)


# Fold the answer into the original request, so the parser reads one complete matchup.
def merge_answer(original: str, answer: str) -> str:
    original, answer = original.strip(), " ".join(answer.split())
    if not answer:
        return original
    if len(typed_sides(answer)) >= 2:
        return answer  # the answer is a whole matchup, e.g. a suggested "a vs b" option
    if len(typed_sides(original)) < 2:
        return f"{original} vs {answer}"  # the opponent was missing
    *lead, last = answer.split(" ")
    lead = lead[1:] if lead and lead[0].lower() in ARTICLES else lead
    # "bear vs wolf" + "grizzly bear" -> "grizzly bear vs wolf" (also matches "bears").
    word = re.compile(rf"\b{re.escape(last)}(?:e?s)?\b", re.I)
    if lead and len(word.findall(original)) == 1:
        return word.sub(lambda match: " ".join([*lead, match.group(0)]), original, count=1)
    return f"{original} ({answer})"


# Re-parse once with the answer. Still vague -> the parser assumes the most common kind and says
# so in the assumptions. Anything else that isn't a matchup ends with a "start again" message.
async def resolve_answer(pending: PendingQuestion, answer: str, chat: ChatLLM) -> IntakeResult:
    text = merge_answer(pending.original_text, answer)
    result = await parse_matchup(text, chat=chat, ask=False)
    if result.status == "clarify":
        return IntakeResult(status="blocked", blocked_reason="other", message=START_OVER)
    return result
