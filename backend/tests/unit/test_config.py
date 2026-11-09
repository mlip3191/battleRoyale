"""Settings load the root .env, ignore unknown keys, hide secrets, and tests stay in mock mode."""

from pathlib import Path

import pytest

from app.config import REPO_ROOT, Settings, get_settings
from tests.conftest import mock_settings

DECOY_VALUE = "not a real value"
DECOY_HOST = "decoy-host.invalid"


# Write a throwaway settings file (never the real .env) and return its path.
def write_env(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "decoy-settings.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_env_file_is_the_root_env() -> None:
    assert (REPO_ROOT / "backend" / "app" / "config.py").is_file()
    assert Path(Settings.model_config["env_file"]) == REPO_ROOT / ".env"


def test_root_env_path_does_not_depend_on_working_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(REPO_ROOT / "backend")
    from_backend = Settings.model_config["env_file"]
    monkeypatch.chdir(tmp_path)
    assert Settings.model_config["env_file"] == from_backend == REPO_ROOT / ".env"


def test_values_load_from_env_file_and_unknown_keys_are_ignored(tmp_path: Path) -> None:
    env = write_env(tmp_path, "SIM_RUNS=42\nVITE_API_BASE=/x\nSOMETHING_UNKNOWN=1\n")
    settings = Settings(_env_file=env)
    assert settings.sim_runs == 42
    assert not hasattr(settings, "something_unknown")


def test_relative_data_dir_resolves_against_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=write_env(tmp_path, "DATA_DIR=./data\n"))
    assert settings.data_dir == (REPO_ROOT / "data").resolve()


def test_repr_never_shows_keys_or_hosts(tmp_path: Path) -> None:
    env = write_env(
        tmp_path,
        f"COURSE_API_KEY={DECOY_VALUE}\nCHAT_LLM_API_KEY={DECOY_VALUE}\n"
        f"CHAT_LLM_URL=http://{DECOY_HOST}:9001\n",
    )
    settings = Settings(_env_file=env)
    assert settings.course_api_key.get_secret_value() == DECOY_VALUE
    for text in (repr(settings), str(settings), settings.model_dump_json()):
        assert DECOY_VALUE not in text
    assert DECOY_HOST not in repr(settings)


def test_tests_run_in_mock_mode_even_when_env_says_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_env = write_env(tmp_path, "PROVIDER_MODE=live\nSIM_RUNS=7\n")
    monkeypatch.setitem(Settings.model_config, "env_file", live_env)
    assert Settings().provider_mode == "live"  # what the app would load from this .env
    forced = mock_settings()
    assert forced.provider_mode == "mock" and forced.sim_runs == 1000  # .env ignored
    assert get_settings().provider_mode == "mock"
