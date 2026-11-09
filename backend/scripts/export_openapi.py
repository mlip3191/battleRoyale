"""Write the app's OpenAPI schema (including every contract) to a file; no server needed."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, use_settings  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "openapi.json"


# Build the app with default settings (the schema never depends on .env) and dump its OpenAPI.
def main() -> None:
    use_settings(Settings(_env_file=None))
    from app.main import create_app

    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_OUT
    text = json.dumps(create_app().openapi(), indent=2, ensure_ascii=False) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote OpenAPI schema to {out.name}")


if __name__ == "__main__":
    main()
