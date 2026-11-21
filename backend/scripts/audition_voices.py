"""Render the A07 announcer test line in every stock TTS voice (issue #45).

From the repo root:
  uv run --directory backend python scripts/audition_voices.py

From the backend folder:
  uv run python scripts/audition_voices.py

Only bundled stock voices are rendered (id "default" or created == 0). User-uploaded
clones on the shared endpoint are skipped. Files are written under <data_dir>/media/auditions/
(gitignored). The script prints voice ids, names, paths, and sizes only — never a URL, host,
or key. Needs PROVIDER_MODE=live and TTS_URL in the worktree .env.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.providers.live.tts import audition_filename, is_stock_voice  # noqa: E402
from app.providers.registry import ProviderConfigError, get_provider, provider_mode  # noqa: E402

TEST_LINE = (
    "Ladies and gentlemen... in this corner... weighing in at four hundred kilos... THE GRIZZLY!"
)


async def _run() -> int:
    if provider_mode("tts") != "live":
        print("audition_voices.py needs PROVIDER_MODE=live.", file=sys.stderr)
        return 1
    try:
        tts = get_provider("tts")
    except ProviderConfigError as error:
        print(error, file=sys.stderr)
        return 1
    voices = await tts.list_voices()
    stock = [voice for voice in voices if is_stock_voice(voice)]
    print(f"Listed {len(voices)} voices; {len(stock)} stock.")
    if not stock:
        print("No stock voices to audition.", file=sys.stderr)
        return 1
    out_dir = get_settings().data_dir / "media" / "auditions"
    out_dir.mkdir(parents=True, exist_ok=True)
    failed = 0
    for voice in stock:
        voice_id = voice["id"]
        name = voice.get("name") or ""
        path = out_dir / audition_filename(voice)
        try:
            data = await tts.speak(TEST_LINE, voice_id)
            path.write_bytes(data)
        except Exception as error:  # noqa: BLE001 - report any failure by type only
            print(f"FAIL  id={voice_id}  name={name}  {type(error).__name__}")
            failed += 1
            continue
        print(f"WROTE {path}  id={voice_id}  name={name}  bytes={len(data)}")
    print(f"Folder: {out_dir}")
    if failed:
        print(f"{failed} stock voice(s) failed.")
        return 1
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
