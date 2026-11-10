# Game fixtures

## thousand-vs-one.json

A real `SimulationResult` for 1,000 ducks against 1 lion, used to check the battle scene with a big crowd (the 50-sprite cap, the "× 1,000" badge, "more go down" summary KOs, and frame rate).

- **Made by:** the simulation engine at `ENGINE_VERSION = 5`, on the `docs-simulation-api-guide` branch (PR #74). `main` was still at an older engine version when it was made.
- **Fighters:** the stand-in `duck()` and `lion()` sheets from `backend/tests/property/sim_helpers.py` (round numbers, not sourced), in an open field, via `matchup_of(1000, 1)`.
- **Seed:** `2055335936440605860`. The same engine version always gives the identical file.

### How to regenerate it

Do this when `ENGINE_VERSION` changes. From `backend/`, on a branch with the engine you want, run this in Git Bash on Windows or a Mac terminal (Windows PowerShell 5 would save the file as UTF-16):

```sh
uv run python -c "import sys; sys.path[:0] = ['.', 'tests/property']; from app.simulation.engine import run; from sim_helpers import duck, lion, matchup_of; print(run(matchup_of(1000, 1), [duck(), lion()]).model_dump_json(indent=2))" > ../frontend/src/game/fixtures/thousand-vs-one.json
```

Then update the engine version and seed above, run `npm run format` (Prettier tidies the JSON), and run `npm run check`.
