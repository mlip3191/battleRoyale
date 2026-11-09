"""The swarm validation script keeps working and restores the swarm threshold."""

from app.simulation import constants as c
from scripts import validate_swarm as vs


def test_compare_runs_both_engines_and_restores_the_threshold():
    threshold = c.SWARM_THRESHOLD
    label, a, na, b, nb = vs.scenarios()["mirror"][0]
    row = vs.compare(label, a, na, b, nb, runs=40)
    assert c.SWARM_THRESHOLD == threshold
    for result in (row.individual, row.swarm):
        assert result.runs == 40
        assert abs(sum(result.win_prob) + result.draw_prob - 1.0) < 1e-9
    assert "|" in vs.table([row]) and label in vs.table([row])


def test_every_scenario_group_is_present():
    assert set(vs.scenarios()) == {"mirror", "uneven", "pack", "cats", "ranged"}


def test_main_prints_one_section_per_scenario(capsys):
    assert vs.main(["--scenario", "pack", "--runs", "30"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("### pack") and out.count("wolves v bear") == 5
