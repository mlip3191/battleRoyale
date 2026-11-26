"""#612: the card line's place words exist in two places, so a test keeps them in step.

The intake writes the card line (`ok_message`), and the card rewrites its place when the viewer
picks another battlefield (frontend/src/pages/terrain-words.ts). If the two tables drift apart, the
rewritten line would no longer match what intake writes.
"""

from app.config import REPO_ROOT
from app.intake.parser import TERRAIN_PHRASES, ok_message
from app.models.matchup import FighterRequest
from app.models.terrain import Terrain

FRONTEND_WORDS = REPO_ROOT / "frontend" / "src" / "pages" / "terrain-words.ts"


def test_the_front_end_card_uses_the_same_place_words_as_the_intake() -> None:
    text = FRONTEND_WORDS.read_text(encoding="utf-8")
    for terrain in Terrain:
        phrase = TERRAIN_PHRASES.get(terrain, "")  # the arena is the default: no place
        assert f'{terrain.value}: "{phrase}"' in text, (terrain.value, phrase)


def test_the_card_line_ends_with_the_place_and_the_rumble_words_the_front_end_expects() -> None:
    wolf = FighterRequest(entity="gray wolf", count=6, raw="6 gray wolves")
    line = ok_message([wolf, wolf], Terrain.FOREST)
    assert line.endswith(" in the forest. Let's get ready to rumble!")
    assert ". Let's get ready to rumble!" in FRONTEND_WORDS.read_text(encoding="utf-8")
