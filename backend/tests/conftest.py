"""Shared test setup: every test runs in mock mode and never reads the real .env."""

from collections.abc import Iterator

import pytest

from app.config import Settings, use_settings


# Settings for tests: no .env file and PROVIDER_MODE forced to mock.
def mock_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, provider_mode="mock", **overrides)


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
