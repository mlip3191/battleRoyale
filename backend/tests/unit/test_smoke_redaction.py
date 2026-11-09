"""The smoke report never keeps a host, URL, or key, and records replies by shape only."""

from app.config import Settings
from scripts.smoke_providers import first_example, redact, shape

DECOY_HOST = "decoy-host.invalid"
DECOY_KEY = "decoy-key-0000"


# Settings with decoy hosts and keys, never the real .env.
def decoy_settings() -> Settings:
    return Settings(
        _env_file=None,
        course_api_key=DECOY_KEY,
        tts_api_key="decoy-tts-key",
        chat_llm_url=f"http://{DECOY_HOST}:9001",
        image_url=f"https://{DECOY_HOST.upper()}:9006/",
    )


def test_redact_removes_every_host_url_and_key() -> None:
    text = (
        f"servers: http://{DECOY_HOST}:9001/v1, https://{DECOY_HOST}:9006, "
        f"key {DECOY_KEY} and decoy-tts-key, error at {DECOY_HOST}"
    )
    clean, remaining = redact(text, decoy_settings())
    assert remaining == 0
    for secret in (DECOY_HOST, DECOY_KEY, "decoy-tts-key"):
        assert secret not in clean
    assert "<url>/v1" in clean and "<key>" in clean and "<host>" in clean


def test_redact_ignores_letter_case() -> None:
    text = f"error at {DECOY_HOST.upper()} and {DECOY_HOST.title()}, key {DECOY_KEY.upper()}"
    clean, remaining = redact(text, decoy_settings())
    assert remaining == 0
    assert DECOY_HOST not in clean.lower() and DECOY_KEY not in clean.lower()


def test_shape_keeps_structure_but_no_text() -> None:
    reply = {"data": [{"embedding": [0.1, 0.2], "note": f"from {DECOY_HOST}"}], "n": 1}
    described = str(shape(reply))
    assert DECOY_HOST not in described
    assert "embedding" in described and "(1 items)" in described


def test_first_example_finds_a_request_body_in_common_layouts() -> None:
    body = {"state": "s", "questions": {}}
    assert first_example({"examples": [{"request": body}]}) == body
    assert first_example([body]) == body
    assert first_example({"basic": body}) == body
    assert first_example("not json") is None
