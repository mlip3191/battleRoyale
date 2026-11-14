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
    assert set(vs.scenarios()) == {"mirror", "uneven", "pack", "cats", "ranged", "large"}


def test_main_prints_one_section_per_scenario(capsys):
    assert vs.main(["--scenario", "pack", "--runs", "30"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("### pack") and out.count("wolves v bear") == 5


def test_the_table_has_a_noise_column():
    label, a, na, b, nb = vs.scenarios()["mirror"][0]
    out = vs.table([vs.compare(label, a, na, b, nb, runs=40)])
    assert "Noise (95%)" in out.splitlines()[0]
    assert out.splitlines()[2].count("|") == out.splitlines()[0].count("|")


def test_the_large_group_is_above_the_threshold_and_opt_in(capsys):
    assert all(max(na, nb) > c.SWARM_THRESHOLD for _, _, na, _, nb in vs.scenarios()["large"])
    assert vs.main(["--scenario", "ranged", "--runs", "20"]) == 0
    assert "### large" not in capsys.readouterr().out
