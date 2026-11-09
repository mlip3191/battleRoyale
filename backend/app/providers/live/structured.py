"""Live StructuredLLM: POST /v1/decisions on the course Structured Decisions endpoint (D-41)."""

from typing import TYPE_CHECKING, Any

import httpx

from app.config import Settings
from app.providers.base import DecisionAnswer, DecisionQuestion
from app.providers.live.http import ProviderError, post_json

if TYPE_CHECKING:
    from app.providers.registry import ServiceConfig


class LiveStructuredLLM:
    """Asks the course decision model named choice questions and returns its picks."""

    def __init__(
        self, config: "ServiceConfig", settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        self.config = config
        self.timeout_s = settings.provider_timeout_s
        self.client = client

    # Send the state and questions; return one checked answer per question.
    async def decide(
        self,
        state: dict[str, str],
        questions: dict[str, DecisionQuestion],
        *,
        prompt_name: str,
    ) -> dict[str, DecisionAnswer]:
        reply = await post_json(
            provider="structured",
            base_url=self.config.base_url,
            path="/v1/decisions",
            api_key=self.config.api_key.get_secret_value(),
            payload={"title": prompt_name, "state": state, "questions": questions},
            timeout_s=self.timeout_s,
            client=self.client,
        )
        answers = reply.get("answers") if isinstance(reply, dict) else None
        if not isinstance(answers, dict):
            raise ProviderError("Live 'structured' reply had no answers.")
        return {
            name: read_answer(name, answers.get(name), question)
            for name, question in questions.items()
        }


# Keep only choice, probabilities, and confidence, and check the choice is a real option.
def read_answer(name: str, raw: Any, question: DecisionQuestion) -> DecisionAnswer:
    options = question["criteria"]
    try:
        choice = raw["choice"]
        probabilities = {option: float(raw["probabilities"][option]) for option in options}
        confidence = float(raw["confidence"])
    except (KeyError, TypeError, ValueError) as error:
        raise ProviderError(f"Live 'structured' answer for '{name}' was incomplete.") from error
    if not isinstance(choice, str) or choice not in options:
        raise ProviderError(f"Live 'structured' answer for '{name}' picked an unknown option.")
    return {"choice": choice, "probabilities": probabilities, "confidence": confidence}
