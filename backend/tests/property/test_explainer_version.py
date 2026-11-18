"""#414: changing the deciding-factor wording needs a new ENGINE_VERSION.

The repeat-battle cache key builds on the simulation seed, which includes ENGINE_VERSION. A
battle saved before a wording change is served again with the old wording unless the version
moves (#390 changed the size sentence at 12 and saved battles kept the old one). So this test
pins a fingerprint of every explainer template's text to the engine version.
"""

import hashlib

from app.models.stats import StatName
from app.models.terrain import Terrain
from app.simulation import constants as c
from app.simulation.decide import (
    _STAT_TEXT,
    _explain,
    _explain_comfortable,
    _explain_even,
    _explain_stalemate,
    _explain_unmeasured,
)
from tests.property.sim_helpers import make_sheet, matchup_of

# The fingerprint of the explainer text at each engine version. When the test below fails, the
# wording changed: bump ENGINE_VERSION in constants.py and record the new fingerprint here.
TEXT_AT_VERSION = {13: "8301a424be2d0ee8135258e2be0c8dc31c4ff1bb3aedc3a26499053a1dec2cdf"}


# One sample of every template: each factor, helped or not, for the smaller and bigger side.
def explainer_samples() -> list[str]:
    small = make_sheet("small", size_m=1.6, mass_kg=40)
    big = make_sheet("big", size_m=2.4, mass_kg=400)
    snake = make_sheet("snake", weapons=["venom"])
    badger = make_sheet("badger", fighter_id="honey-badger")
    shark = make_sheet("shark", habitat="water")
    cases = [
        (key, matchup, sheets)
        for key in [*_STAT_TEXT, "numbers"]
        for matchup in (matchup_of(1, 1), matchup_of(6, 1), matchup_of(1, 6))
        for sheets in ([small, big], [big, small])
    ]
    cases += [
        ("venom", matchup_of(1, 1), [snake, big]),
        ("venom", matchup_of(1, 1), [big, snake]),
        ("resistance", matchup_of(1, 1), [badger, snake]),
        ("resistance", matchup_of(1, 1), [snake, badger]),
        ("terrain", matchup_of(1, 1, terrain=Terrain.WATER), [shark, small]),
        ("scaling", matchup_of(1, 1, ref_0="horse"), [small, big]),
    ]
    texts = [_explain(k, m, s, 0, helped) for k, m, s in cases for helped in (True, False)]
    fixed = [_explain_stalemate(), _explain_comfortable("Small"), _explain_even()]
    return [*texts, *fixed, _explain_unmeasured()]


def fingerprint(texts: list[str]) -> str:
    return hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()


def test_the_explainer_text_is_pinned_to_the_engine_version():
    texts = explainer_samples()
    assert StatName.SIZE in _STAT_TEXT and len(texts) > 100  # the samples cover the templates
    assert TEXT_AT_VERSION.get(c.ENGINE_VERSION) == fingerprint(texts), (
        "The deciding-factor wording changed, so saved battles would keep the old text: bump "
        "ENGINE_VERSION and record the new fingerprint in TEXT_AT_VERSION (#414)."
    )
