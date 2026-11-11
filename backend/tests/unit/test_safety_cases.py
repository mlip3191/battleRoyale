"""#27 criterion 1: the safety cases in tests/fixtures/safety_cases.yaml, on mocks.

Every blocked case must be blocked with its exact reason by the expected layer, and no allowed
case may be blocked. On mocks the classifier's verdict is written into each case, so this checks
the plumbing (rules, the Wikidata class map, reason routing), not the classifier's quality; the
live run (backend/scripts/safety_eval.py) measures that. See docs/safety.md.
"""

from collections import Counter

import pytest

from app.safety.verdict import BLOCKED_REASONS
from tests.unit.safety_case_helpers import SafetyCase, cases_by_id, load_cases, run_case

CASES = load_cases()
# Groups that count as objects, machines or mythical creatures (#27: at least 8 allowed cases).
THINGS = {"object", "machine", "mythical"}


def test_the_case_file_meets_the_issue_counts() -> None:
    allowed = [c for c in CASES if c.expect == "allowed"]
    blocked = [c for c in CASES if c.expect == "blocked"]
    assert len(CASES) >= 50
    assert len(allowed) >= 25 and len(blocked) >= 25
    assert sum(c.kind in THINGS for c in allowed) >= 8
    assert {c.reason for c in blocked} == set(BLOCKED_REASONS)
    assert sum(c.clean is not None for c in CASES) >= 5


def test_every_case_is_well_formed() -> None:
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids)), "case ids must be unique"
    by_id = cases_by_id()
    for case in CASES:
        assert case.expect in ("allowed", "blocked"), case.id
        if case.expect == "blocked":
            assert case.reason in BLOCKED_REASONS, case.id
            assert case.layer in ("rules", "classifier", "wikidata"), case.id
        else:
            assert case.reason is None and case.layer is None, case.id
        if case.clean is not None:
            clean = by_id[case.clean]  # an injection and its clean case expect the same
            assert (clean.expect, clean.reason) == (case.expect, case.reason), case.id
            assert clean.clean is None, case.id


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
async def test_each_case_gets_its_expected_verdict_on_mocks(
    case: SafetyCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, layer = await run_case(case, monkeypatch)
    if case.expect == "blocked":
        assert (result.status, result.blocked_reason, layer) == (
            "blocked",
            case.reason,
            case.layer,
        )
    else:
        assert result.status == "ok", (result.status, result.blocked_reason, result.message)


# Precision and recall of "blocked" over every case, printed for the PR (pytest -s shows it).
async def test_mock_precision_and_recall(monkeypatch: pytest.MonkeyPatch) -> None:
    tally: Counter[tuple[bool, bool]] = Counter()  # (expected blocked, got blocked)
    wrong_reason: list[str] = []
    for case in CASES:
        result, _ = await run_case(case, monkeypatch)
        expected, got = case.expect == "blocked", result.status == "blocked"
        tally[(expected, got)] += 1
        if expected and got and result.blocked_reason != case.reason:
            wrong_reason.append(case.id)
    tp, fp, fn = tally[(True, True)], tally[(False, True)], tally[(True, False)]
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    print(f"\nmock safety cases: {len(CASES)}, precision {precision:.0%}, recall {recall:.0%}")
    assert recall == 1.0, "a blocked case got through"
    assert fp == 0, "an allowed case was blocked"
    assert not wrong_reason, wrong_reason
