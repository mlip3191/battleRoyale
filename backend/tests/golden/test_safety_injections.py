"""Golden (#27 criterion 4): each prompt injection in tests/fixtures/safety_cases.yaml gives the
same parsed matchup, or the same block, as its clean version.

The stand-in model reads the same fighters from both, as the prompts ask; in the injected version
it also echoes the injection into its notes (a variant and an assumption with numbers), which code
must drop (number rule) or ignore. These pairs moved here from tests/unit/test_intake_safety.py.
"""

from typing import Any

import pytest

from app.models.matchup import IntakeResult
from tests.unit.safety_case_helpers import SafetyCase, cases_by_id, load_cases, run_case

INJECTIONS = [case for case in load_cases() if case.clean is not None]


# Everything about a result except the user's own text.
def comparable(result: IntakeResult) -> dict[str, Any]:
    data = result.model_dump()
    if data["matchup"]:
        data["matchup"].pop("raw_text")
    return data


def test_there_are_at_least_five_injection_pairs() -> None:
    assert len(INJECTIONS) >= 5


@pytest.mark.parametrize("injected", INJECTIONS, ids=[c.id for c in INJECTIONS])
async def test_an_injection_gives_the_same_result_as_its_clean_version(
    injected: SafetyCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean = cases_by_id()[injected.clean or ""]
    got, _ = await run_case(injected, monkeypatch)
    want, _ = await run_case(clean, monkeypatch)
    assert comparable(got) == comparable(want)
