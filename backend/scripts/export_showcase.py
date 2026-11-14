"""Export finished battles into data/showcase/ for a fresh clone (G08, #47).

Run the five showcase battles in the app first (PRODUCT_SPEC section 9), note their battle ids,
then from the backend folder:
  uv run python -m scripts.export_showcase b-abc123 b-def456 ...
  uv run python -m scripts.export_showcase b-abc123="Grizzly bear vs 6 Gray wolves" ...
The ids are written in the order given, which is the home page's order. A title after "=" is
used as is; otherwise the title is the fighters' names joined by "vs".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db.connection import connect  # noqa: E402
from app.db.migrate import apply_migrations  # noqa: E402
from app.db.showcase import SHOWCASE_DIR, export_showcase  # noqa: E402


# "b-abc123" or "b-abc123=Some title" as (battle id, title or None).
def parse(arg: str) -> tuple[str, str | None]:
    battle_id, _, title = arg.partition("=")
    return battle_id.strip(), title.strip() or None


def main(args: list[str]) -> int:
    if not args:
        print(__doc__)
        return 1
    connection = connect()
    try:
        apply_migrations(connection)
        media_dir = get_settings().data_dir / "media"
        result = export_showcase(connection, [parse(a) for a in args], media_dir)
    except ValueError as error:
        print(f"Not exported: {error}")
        return 1
    finally:
        connection.close()
    print(
        f"Exported {result.battles} battles ({result.total_bytes / 1e6:.1f} MB) to {SHOWCASE_DIR}."
    )
    if result.dropped:
        print(f"Left out to stay under 20 MB: {', '.join(result.dropped)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
