"""Run the five showcase battles through the running app, then print the export command (G08).

Start the app first (`npm start`, live mode for real narration and images), then from the
backend folder:
  uv run python -m scripts.run_showcase                      # the app at http://localhost:8000
  uv run python -m scripts.run_showcase --base http://localhost:8001
It starts each battle from PRODUCT_SPEC section 9 in order, waits for it to finish, and prints
the `export_showcase` command with the battle ids and titles, ready to copy. A battle that fails
is reported and left out; nothing is exported until you run that command.
"""

import argparse
import shlex
import sys
import time
from typing import Any

import httpx

# The five showcase battles (PRODUCT_SPEC section 9), in home-page order, with their titles.
SHOWCASE: list[tuple[str, dict[str, Any]]] = [
    (
        "100 duck-sized horses vs 1 horse-sized duck",
        {
            "fighters": [
                {"entity": "horse", "count": 100, "size_reference": "duck",
                 "raw": "100 duck-sized horses"},
                {"entity": "duck", "count": 1, "size_reference": "horse",
                 "raw": "1 horse-sized duck"},
            ],
            "terrain": "arena",
            "raw_text": "100 duck-sized horses vs 1 horse-sized duck",
        },
    ),
    (
        "Grizzly bear vs 6 gray wolves",
        {
            "fighters": [
                {"entity": "grizzly bear", "count": 1, "raw": "a grizzly bear"},
                {"entity": "gray wolf", "count": 6, "raw": "6 gray wolves"},
            ],
            "terrain": "forest",
            "raw_text": "a grizzly bear vs 6 gray wolves in a forest",
        },
    ),
    (
        "Honey badger vs king cobra",
        {
            "fighters": [
                {"entity": "honey badger", "count": 1, "raw": "a honey badger"},
                {"entity": "king cobra", "count": 1, "raw": "a king cobra"},
            ],
            "terrain": "arena",
            "raw_text": "a honey badger vs a king cobra",
        },
    ),
    (
        "Roman legionary vs gorilla",
        {
            "fighters": [
                {"entity": "roman legionary", "count": 1, "raw": "a Roman legionary"},
                {"entity": "gorilla", "count": 1, "raw": "a gorilla"},
            ],
            "terrain": "arena",
            "raw_text": "a Roman legionary vs a gorilla",
        },
    ),
    (
        "Dragon vs main battle tank",
        {
            "fighters": [
                {"entity": "dragon", "count": 1, "raw": "a dragon"},
                {"entity": "main battle tank", "count": 1, "raw": "a main battle tank"},
            ],
            "terrain": "open_field",
            "raw_text": "a dragon vs a main battle tank in an open field",
        },
    ),
]  # fmt: skip
POLL_S = 3.0
TIMEOUT_S = 300.0  # per battle: research, narration, audio and images can take minutes live


# Start one battle and wait for it to end; returns (battle id, final status).
def run_battle(client: httpx.Client, matchup: dict[str, Any]) -> tuple[str, str]:
    reply = client.post("/api/battles", json=matchup)
    reply.raise_for_status()
    battle_id = reply.json()["battle_id"]
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        status = client.get(f"/api/battles/{battle_id}").json()["status"]
        if status != "running":
            return battle_id, status
        time.sleep(POLL_S)
    return battle_id, "timed out"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://localhost:8000", help="the running app")
    base = parser.parse_args(argv).base
    done: list[tuple[str, str]] = []
    with httpx.Client(base_url=base, timeout=30.0) as client:
        for title, matchup in SHOWCASE:
            try:
                battle_id, status = run_battle(client, matchup)
            except httpx.HTTPError as error:
                print(f"Could not run {title!r}: {error}. Is the app running at {base}?")
                return 1
            print(f"{status:>9}  {battle_id}  {title}")
            if status == "done":
                done.append((battle_id, title))
    if len(done) < len(SHOWCASE):
        print(f"\n{len(SHOWCASE) - len(done)} battle(s) didn't finish; they are left out below.")
    args = " ".join(shlex.quote(f"{battle_id}={title}") for battle_id, title in done)
    print("\nTo export them, from the backend folder:")
    print(f"  uv run python -m scripts.export_showcase {args}")
    return 0 if len(done) == len(SHOWCASE) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
