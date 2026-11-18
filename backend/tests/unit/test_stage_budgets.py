"""The stage limits as shipped (test_pipeline_stages shrinks them for speed, so they live here)."""

import pytest

from app.pipeline import stages


def test_the_script_stage_leaves_room_for_one_retry() -> None:
    # 15 s for the stage (D-66, #363): the writer gets 12 s and each script 10.5 s.
    budget = stages.STAGE_BUDGETS_S["script"]
    assert budget == 15.0
    assert budget * stages.SCRIPT_WRITER_SHARE == pytest.approx(12.0)
    assert budget * stages.SCRIPT_CALL_SHARE == pytest.approx(10.5)
