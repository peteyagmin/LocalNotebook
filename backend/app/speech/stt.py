"""Speech-to-text behind a small interface (spec §3). faster-whisper is the implementation."""

from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

BLOCK_SECONDS = 30.0


class STTUnavailable(Exception):
    """The model is not configured or not installed. The message is user-readable."""


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


class STTEngine(Protocol):
    def transcribe(self, path: Path) -> list[TranscriptSegment]: ...


def model_dir(models_dir: Path, model: str) -> Path:
    """Where a model lives on disk: <data_root>/models/stt/<name>."""
    safe = re.sub(r"[^\w.\-]+", "_", model).strip("._") or "model"
    return models_dir / "stt" / safe


def is_installed(models_dir: Path, model: str) -> bool:
    if not model:
        return False
    return (model_dir(models_dir, model) / "model.bin").is_file()


class FasterWhisperEngine:
    def __init__(self, model: str, models_dir: Path):
        from faster_whisper import WhisperModel

        self._model = WhisperModel(str(model_dir(models_dir, model)), device="auto")

    def transcribe(self, path: Path) -> list[TranscriptSegment]:
        segments, _info = self._model.transcribe(str(path), vad_filter=True)
        return [
            TranscriptSegment(s.start, s.end, s.text.strip()) for s in segments if s.text.strip()
        ]


def create_engine(model: str, models_dir: Path) -> STTEngine:
    """The engine for `model`. LNB_STT_FACTORY="module:function" swaps in another one (tests,
    development); the function receives (model, models_dir)."""
    if not model:
        raise STTUnavailable(
            "No speech-to-text model is configured. Choose one in Settings, then retry."
        )
    override = os.environ.get("LNB_STT_FACTORY")
    if override:
        module, _, name = override.partition(":")
        return getattr(importlib.import_module(module), name)(model, models_dir)
    if not is_installed(models_dir, model):
        raise STTUnavailable(
            f"The speech-to-text model '{model}' is not installed. Download it in Settings, "
            "then retry."
        )
    return FasterWhisperEngine(model, models_dir)


def group_segments(
    segments: list[TranscriptSegment], window: float = BLOCK_SECONDS
) -> list[tuple[str, float, float]]:
    """Merge short segments into blocks of about `window` seconds: [(text, start, end)]. Blocks
    become paragraphs, so chunks break on timestamp boundaries (FR-2.10)."""
    blocks: list[tuple[str, float, float]] = []
    texts: list[str] = []
    start = end = 0.0
    for seg in segments:
        if texts and seg.end - start >= window:
            blocks.append((" ".join(texts), start, end))
            texts = []
        if not texts:
            start = seg.start
        texts.append(seg.text.strip())
        end = seg.end
    if texts:
        blocks.append((" ".join(texts), start, end))
    return blocks


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
