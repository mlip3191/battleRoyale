"""Asset.script_kind tells which Script a narration_audio file reads (#209)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models import Asset

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


# Build the fields of a narration_audio asset, plus any overrides.
def narration(**extra: object) -> dict:
    return {
        "asset_id": "narration-intro",
        "kind": "narration_audio",
        "url": "/media/audio/narration-intro.mp3",
        "prompt_hash": "abc123",
        **extra,
    }


def test_script_kind_defaults_to_none() -> None:
    asset = Asset.model_validate(narration())
    assert asset.script_kind is None


@pytest.mark.parametrize("script_kind", ["intro", "play_by_play", "outro"])
def test_narration_audio_accepts_each_script_kind(script_kind: str) -> None:
    asset = Asset.model_validate(narration(script_kind=script_kind))
    assert asset.script_kind == script_kind


def test_unknown_script_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Asset.model_validate(narration(script_kind="recap"))


def test_existing_asset_fixture_still_validates() -> None:
    data = json.loads((FIXTURES / "asset.json").read_text(encoding="utf-8"))
    asset = Asset.model_validate(data)
    assert asset.script_kind is None
