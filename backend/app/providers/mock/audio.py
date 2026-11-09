"""Mock audio providers: silent WAV files of a predictable length."""

import io
import wave

MOCK_SAMPLE_RATE = 8000
MOCK_MAX_SECONDS = 600.0


# Mono 16-bit silence, as WAV bytes.
def silent_wav(seconds: float, sample_rate: int = MOCK_SAMPLE_RATE) -> bytes:
    frames = int(max(0.0, min(seconds, MOCK_MAX_SECONDS)) * sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)
    return buffer.getvalue()


class MockTTS:
    """One second of silence per line."""

    async def speak(self, text: str, voice_id: str) -> bytes:
        return silent_wav(1.0)


class MockMusicGen:
    """A silent track of the requested length."""

    async def compose(self, prompt: str, seconds: float) -> bytes:
        return silent_wav(seconds)
