"""The showcase dry-run script keeps working with the engine."""

from scripts import showcase_dry_run as dry


def test_the_five_showcase_battles_are_defined():
    titles = [b.title for b in dry.battles()]
    assert len(titles) == 5
    assert titles[0].startswith("100 duck-sized horses")
    assert "dragon" in titles[4].lower() and "tank" in titles[4].lower()


def test_a_battle_plays_and_reports():
    badger_vs_cobra = dry.battles()[2]
    outcome = dry.play(badger_vs_cobra, runs=50)
    text = dry.report(outcome)
    assert outcome.result.runs == 50 and badger_vs_cobra.title in text
    assert "Verdict" in text and "Fair fight" in text


def test_the_size_reference_battle_scales_the_fighters():
    duck_horses = dry.battles()[0]
    outcome = dry.play(duck_horses, runs=30)
    hints = [e.text_hint for e in outcome.result.representative_log]
    assert any("scaled to duck size" in h for h in hints)
    assert any("scaled to horse size" in h for h in hints)


def test_main_prints_every_battle(capsys):
    assert dry.main(["--runs", "30"]) == 0
    out = capsys.readouterr().out
    assert out.count("### ") == 5
    # A pasted report must never pass for demo results, and must say the dragon is a stand-in.
    header = out.split("###")[0]
    assert out.startswith("ENGINE CHECK ONLY") and "Not demo results" in header
    assert "dragon" in header and "stand-in" in header
