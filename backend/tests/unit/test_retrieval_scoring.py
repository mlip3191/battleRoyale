"""One retrieval scoring function for retrieval_eval.py and evaluate_ai.py (#389); no live calls."""

from types import SimpleNamespace
from typing import Any

from scripts import evaluate_ai, retrieval_eval


# Stand-in passages, as evidence_for returns them (only .text is read).
def passages(*texts: str) -> list[Any]:
    return [SimpleNamespace(text=text) for text in texts]


def test_rank_of_finds_the_first_passage_that_holds_the_phrase() -> None:
    found = passages("Wolves hunt in packs.", "An adult weighs 40 kg.", "It weighs 40 kg too.")
    assert retrieval_eval.rank_of("weighs 40 kg", found) == 2  # the first match counts
    assert retrieval_eval.rank_of("Wolves hunt", found) == 1
    assert retrieval_eval.rank_of("1.6 m long", found) is None


def test_rank_of_uses_the_shared_text_normalization() -> None:
    # normalize_text is the same rule the extraction quote check uses.
    found = passages("A bite force of 16,414 N was measured.")
    assert retrieval_eval.rank_of("16,414 N", found) == 1


async def test_case_ranks_scores_every_case_in_order(monkeypatch: Any) -> None:
    by_fighter = {
        "gray-wolf": passages("Wolves hunt in packs.", "An adult weighs 40 kg."),
        "horse": passages("Horses graze."),
    }

    async def fake_evidence(_connection: Any, _e: Any, _r: Any, fighter_id: str, _stat: Any) -> Any:
        return by_fighter[fighter_id]

    monkeypatch.setattr(retrieval_eval, "evidence_for", fake_evidence)
    cases = [
        {"fighter_id": "gray-wolf", "stat": "mass_kg", "phrase": "40 kg"},
        {"fighter_id": "horse", "stat": "top_speed_mps", "phrase": "48 kilometres per hour"},
    ]
    ranked = await retrieval_eval.case_ranks(None, None, None, cases)
    assert [rank for _, rank in ranked] == [2, None]
    assert [case for case, _ in ranked] == cases


def test_the_evaluation_section_is_built_from_the_shared_ranks() -> None:
    ranked = [
        ({"fighter_id": "gray-wolf", "stat": "mass_kg", "phrase": "40 kg"}, 1),
        ({"fighter_id": "lion", "stat": "size_m", "phrase": "2.5 m"}, 3),
        ({"fighter_id": "horse", "stat": "top_speed_mps", "phrase": "48 km/h"}, None),
    ]
    text = evaluate_ai.retrieval_markdown(ranked)
    assert "| hit@5 (target 80%) | 2/3 (67%) |" in text
    assert "| Ranked first | 1/3 (33%) |" in text
    assert "- horse top_speed_mps: '48 km/h'" in text
