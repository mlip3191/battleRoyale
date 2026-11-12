# Game fixtures

Two real `SimulationResult` logs for big crowds, used to check the battle scene under load: the 50-sprite cap, the "× N" badge, and the frame rate.

| File                       | Matchup               | Events | What it tests                                                                                                         |
| -------------------------- | --------------------- | ------ | --------------------------------------------------------------------------------------------------------------------- |
| `thousand-vs-one.json`     | 1,000 ducks vs 1 lion | 93    | The biggest crowd: swarm mode, 50 sprites, the "× 1,000" badge counting down.                                         |
| `two-hundred-vs-five.json` | 200 ducks vs 5 lions  | 103    | A swarm replay below 200 per side (D-50, since engine version 8): group hits and knock-outs, never individual misses. |

- **Made by:** the simulation engine at `ENGINE_VERSION = 8` (`backend/app/simulation/constants.py`).
- **Fighters:** the stand-in `duck()` and `lion()` sheets from `backend/tests/property/sim_helpers.py` (round numbers, not sourced), in an open field, via `matchup_of(1000, 1)` and `matchup_of(200, 5)`.
- **Seeds:** `2253034143055008184` (thousand-vs-one) and `2970169064738633593` (two-hundred-vs-five). The same engine version always gives the identical files.

## How to watch them in the app

In fixtures mode (`VITE_USE_FIXTURES=true`), two reserved battle ids open these replays straight away, already finished, with no backend: `/battle/thousand-vs-one` and `/battle/two-hundred-vs-five`. In normal mode those ids are not special: the app asks the backend, which says the battle doesn't exist. The code is `crowdBattle` in `src/api/fixtures.ts`.

1. Start the front end in fixtures mode from the repo root. Git Bash or a Mac terminal: `VITE_USE_FIXTURES=true npm run dev:frontend`. Windows PowerShell: `$env:VITE_USE_FIXTURES = "true"; npm run dev:frontend` (the setting lasts until you close that terminal).
2. In Chrome, open http://localhost:5173/battle/thousand-vs-one (or `/battle/two-hundred-vs-five`).
3. Check the stage: 50 duck sprites on the left with a "× 1,000" badge, one lion on the right.

## How to measure the frame rate

1. On the battle page, open Chrome DevTools (F12, or Ctrl+Shift+I; Cmd+Option+I on a Mac).
2. Press Ctrl+Shift+P (Cmd+Shift+P on a Mac), type `frame rendering stats`, and choose **Show frame rendering stats**. (Or: the ⋮ menu → More tools → Rendering → tick **Frame rendering stats**.) A meter appears in the top-left corner of the page.
3. Press **Play** on the replay and watch the meter until the fight ends. Try 2× speed and **Replay** too.
4. The goal (D05) is at least 30 fps for the whole replay. Note your computer and browser when you report a number.

## How to regenerate them

Do this when `ENGINE_VERSION` changes. From the repo root, in Git Bash on Windows or a Mac terminal (Windows PowerShell 5 would save the files as UTF-16), run each line:

```sh
cd backend
uv run python -c "import sys; sys.path[:0] = ['.', 'tests/property']; from app.simulation.engine import run; from sim_helpers import duck, lion, matchup_of; print(run(matchup_of(1000, 1), [duck(), lion()]).model_dump_json(indent=2))" > ../frontend/src/game/fixtures/thousand-vs-one.json
uv run python -c "import sys; sys.path[:0] = ['.', 'tests/property']; from app.simulation.engine import run; from sim_helpers import duck, lion, matchup_of; print(run(matchup_of(200, 5), [duck(), lion()]).model_dump_json(indent=2))" > ../frontend/src/game/fixtures/two-hundred-vs-five.json
```

A test (`backend/tests/property/test_crowd_fixtures.py`) fails with "regenerate the crowd fixtures" when the files no longer match the engine. Then update the engine version, seeds and event counts above, run `npm run format` (Prettier tidies the JSON), and run `npm run check`.
