"""docs/simulation-api.md: the guide's example must keep working (and say true things)."""

import re

import pytest

from app.config import REPO_ROOT
from app.models.simulation import EventType
from app.simulation.engine import run
from tests.property.sim_helpers import duck, horse, lion, matchup_of

GUIDE = REPO_ROOT / "docs" / "simulation-api.md"


def python_blocks() -> list[str]:
    text = GUIDE.read_text(encoding="utf-8")
    return re.findall(r"```python\n(.*?)```", text, flags=re.S)


def test_the_complete_example_runs(monkeypatch, capsys):
    monkeypatch.chdir(REPO_ROOT)  # the example loads fixtures by repo-relative path
    example = next(block for block in python_blocks() if "stat_sheets = [bear, wolf]" in block)
    exec(compile(example, "docs/simulation-api.md", "exec"), {})
    out = capsys.readouterr().out
    assert "Grizzly bear - adult male" in out
    assert "A fair fight needs" in out or "No fair fight" in out


def test_the_size_reference_snippet_matches_how_run_really_works():
    snippet = next(block for block in python_blocks() if "reference_sheets=[horse, None]" in block)
    assert "run(matchup, [duck, lion]" in snippet
    matchup = matchup_of(1, 1, ref_0="horse")
    result = run(
        matchup, [duck(), lion()], runs=50, reference_sheets=[horse(), None], explain=False
    )
    hints = [e.text_hint for e in result.representative_log if e.type == EventType.APPROACH]
    assert any(hint.endswith("scaled to horse size") for hint in hints)
    with pytest.raises(ValueError, match="size_reference"):
        run(matchup, [duck(), lion()], runs=5)


def test_every_function_the_guide_names_exists():
    from app.simulation import engine, fair, summary

    text = GUIDE.read_text(encoding="utf-8")
    for name, module in (
        ("run", engine),
        ("fair_fight", fair),
        ("test_challengers", fair),
        ("summary", summary),
        ("scale_factors", engine),
    ):
        assert hasattr(module, name) and name in text
