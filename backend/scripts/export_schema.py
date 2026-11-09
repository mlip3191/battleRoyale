"""Write a JSON Schema file for every contract model to backend/app/models/schema/."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import CONTRACT_MODELS  # noqa: E402

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "app" / "models" / "schema"


# "StatSheet" -> "stat-sheet" (repo file names are lowercase-with-dashes).
def file_stem(model_name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", model_name).lower()


# Rewrite the schema folder so removed models don't leave stale files behind.
def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for old in SCHEMA_DIR.glob("*.json"):
        old.unlink()
    for model in CONTRACT_MODELS:
        text = json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n"
        path = SCHEMA_DIR / f"{file_stem(model.__name__)}.json"
        path.write_text(text, encoding="utf-8", newline="\n")
    print(
        f"Wrote {len(CONTRACT_MODELS)} schemas to {SCHEMA_DIR.relative_to(SCHEMA_DIR.parents[2])}"
    )


if __name__ == "__main__":
    main()
