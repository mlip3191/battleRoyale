"""Where generated media files live, shared by audio (A07) and images (A08).

Live files are saved under <data_dir>/media/ (e.g. sprites/gray-wolf-v1.png). Files made in mock
mode go under <data_dir>/media/mock/ instead (e.g. mock/sprites/gray-wolf-v1.png), so a mock
placeholder or silent WAV is never served as if a live provider had made it (#280). Both are
served from /media, and the asset url always names the same relative path as the file.
"""

import os
import time
import uuid
from pathlib import Path

from app.config import get_settings
from app.providers.registry import ProviderMode

MOCK_FOLDER = "mock"
REPLACE_TRIES = 6  # Windows can hold a file for a moment (a virus scan, a reader): wait, then retry
REPLACE_WAIT_S = 0.02  # doubles each try: 20, 40, 80, 160 and 320 ms, 0.6 s in all


# The folder generated media lives in.
def media_root() -> Path:
    return get_settings().data_dir / "media"


# A file's path under the media folder for this provider mode: mock files go in mock/.
def cache_path(relative: Path, mode: ProviderMode) -> Path:
    return Path(MOCK_FOLDER) / relative if mode == "mock" else relative


# A cache hit needs a real, non-empty file (not a symlink): an empty or broken one is redone.
def is_cached(file: Path) -> bool:
    return not file.is_symlink() and file.is_file() and file.stat().st_size > 0


# Move a finished file into place, retrying a PermissionError (#381: Windows refuses to replace a
# file that something has open for a moment) before giving up.
def replace_with_retry(partial: Path, file: Path) -> None:
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(partial, file)
            return
        except PermissionError:
            if attempt == REPLACE_TRIES - 1:
                raise
            time.sleep(REPLACE_WAIT_S * 2**attempt)


# Write a file all at once, so a reader never sees half of it.
def save(file: Path, data: bytes) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    partial = file.with_name(f".{file.name}.{uuid.uuid4().hex}.tmp")
    try:
        partial.write_bytes(data)
        replace_with_retry(partial, file)
    finally:
        partial.unlink(missing_ok=True)
