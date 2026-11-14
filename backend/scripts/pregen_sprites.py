"""Draw a sprite for every seed fighter and a battlefield for every terrain, then check them (A08).

From the backend folder:
  uv run python -m scripts.pregen_sprites                  # uses PROVIDER_MODE from .env
  uv run python -m scripts.pregen_sprites --force          # redraw even when cached
  uv run python -m scripts.pregen_sprites --thumbs thumbs  # also write thumbnails + contact sheet

Pictures are cached in data/media/ per fighter_id (or terrain) and style version, so a second
run draws nothing new. Every sprite must be a PNG whose four corner pixels are transparent; the
script prints a PASS/FAIL table (ids, timings, and sizes only, never a URL, host, or key), lists
any failures, and exits 1 if there are any. The logic lives in app/media/pregen.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.media.pregen import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
