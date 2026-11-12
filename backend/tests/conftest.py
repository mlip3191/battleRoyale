"""Shared test setup: every test runs in mock mode and never reads the real .env.

Tests also never touch the real data/app.db: data_dir points at a temp folder for the session.
"""

import atexit
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import Settings, use_settings

# One temp data folder for the whole test session, removed when the run ends.
TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="battle-royale-tests-"))
atexit.register(shutil.rmtree, TEST_DATA_DIR, ignore_errors=True)


# Settings for tests: no .env file, PROVIDER_MODE forced to mock, and the temp data folder.
def mock_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"data_dir": TEST_DATA_DIR} | overrides
    return Settings(_env_file=None, provider_mode="mock", **values)


# Installed at import, because test modules import app.main (which reads settings) when collected.
use_settings(mock_settings())


# Re-install mock settings before every test, in case a test replaced them.
@pytest.fixture(autouse=True)
def _force_mock_settings() -> Iterator[None]:
    use_settings(mock_settings())
    yield
    use_settings(mock_settings())


# Fresh mock settings for a single test, with optional overrides.
@pytest.fixture
def settings() -> Settings:
    return mock_settings()
