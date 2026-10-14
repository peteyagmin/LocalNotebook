"""A stand-in speech-to-text engine, loaded in the parser process via LNB_STT_FACTORY."""

from pathlib import Path

from app.speech.stt import TranscriptSegment


class FakeEngine:
    def transcribe(self, path: Path) -> list[TranscriptSegment]:
        if path.read_bytes().startswith(b"SILENCE"):
            return []
        # ~100 seconds of speech in short segments, like a real recogniser produces
        return [
            TranscriptSegment(i * 10.0, i * 10.0 + 9.0, f"Spoken sentence number {i} about zebras.")
            for i in range(10)
        ]


def make(model: str, models_dir: Path) -> FakeEngine:
    return FakeEngine()
