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
# Any new ENGINE_VERSION needs an entry here; if only the version moved, copy the same fingerprint.
# 13 was updated on purpose twice, for #458 (a crowd reads "6 gray wolves", not "6 Gray wolf") and
# for #552 (an estimated number is labeled "estimate" in the sentence). For both, the PM chose to
# keep ENGINE_VERSION at 13 (#555, Nov 22), because a reseed the day before the bug bash would
# move results measured on 13 (as #423's bump moved cnt-04 from 288 to 320). Only new battles get
# the new text.
TEXT_AT_VERSION = {13: "fe2a3b0024af0bc91b8bd9e18bc7e92c8d0a66d5451bcb590f47d87b70d6e364"}


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
        "No fingerprint for this ENGINE_VERSION, or the deciding-factor wording changed (saved "
        "battles would keep the old text). After a bump for another reason, copy the previous "
        "fingerprint to the new version; after a wording change, bump ENGINE_VERSION and record "
        "the new fingerprint in TEXT_AT_VERSION (#414)."
    )
