"""App settings: the only module that reads environment variables (from the root .env)."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root (battleRoyale/), so the root .env is found whatever folder a command runs from.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Every setting from .env.example; keys are SecretStr and URLs are hidden from repr."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_env: str = "development"
    port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    log_level: str = "INFO"

    # Providers
    provider_mode: Literal["mock", "live"] = "mock"
    provider_timeout_s: float = 30.0

    # Course endpoints (URLs hold hosts, so they never appear in repr or logs)
    course_api_key: SecretStr = SecretStr("")
    chat_llm_url: str = Field(default="", repr=False)
    chat_llm_model: str = ""
    chat_llm_api_key: SecretStr | None = None
    structured_llm_url: str = Field(default="", repr=False)
    structured_llm_model: str = ""
    structured_llm_api_key: SecretStr | None = None
    embeddings_url: str = Field(default="", repr=False)
    embeddings_model: str = ""
    embeddings_api_key: SecretStr | None = None
    rerank_url: str = Field(default="", repr=False)
    rerank_api_key: SecretStr | None = None
    doc_parse_url: str = Field(default="", repr=False)
    doc_parse_api_key: SecretStr | None = None
    image_url: str = Field(default="", repr=False)
    image_api_key: SecretStr | None = None
    tts_url: str = Field(default="", repr=False)
    tts_api_key: SecretStr | None = None
    music_url: str = Field(default="", repr=False)
    music_api_key: SecretStr | None = None
    stt_url: str = Field(default="", repr=False)
    mm_embeddings_url: str = Field(default="", repr=False)

    # Announcer voice
    announcer_voice_source: str = "stock"
    announcer_voice_id: str = ""
    announcer_voice_style: str = ""
    announcer_voice_consent_file: Path | None = None

    # Simulation
    sim_runs: int = 1000
    sim_max_count: int = 10000

    # Storage
    data_dir: Path = Path("data")

    # Resolve relative paths against the repo root, not the current folder.
    @field_validator("data_dir", "announcer_voice_consent_file", mode="after")
    @classmethod
    def _resolve_from_repo_root(cls, value: Path | None) -> Path | None:
        if value is None or value.is_absolute():
            return value
        return (REPO_ROOT / value).resolve()

    # Treat a blank optional path in .env as "not set".
    @field_validator("announcer_voice_consent_file", mode="before")
    @classmethod
    def _blank_path_is_none(cls, value: object) -> object:
        return None if value == "" else value


_settings: Settings | None = None


# Return the shared settings, loading the root .env on first use.
def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Replace the shared settings (tests use this to force mock mode and ignore .env).
def use_settings(settings: Settings | None) -> None:
    global _settings
    _settings = settings
