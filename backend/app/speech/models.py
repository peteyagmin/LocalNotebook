"""Downloading speech-to-text models on first use, with progress (FR-8.2, FR-8.6)."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from app.speech.stt import is_installed, model_dir

log = logging.getLogger(__name__)

# downloader(model, target_dir, report) -> None; report(fraction | None) is called as it goes.
Downloader = Callable[[str, Path, Callable[[float | None], None]], None]

_FILE_PATTERNS = [
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
]


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def download_faster_whisper(
    model: str, target: Path, report: Callable[[float | None], None]
) -> None:
    """Download from the Hugging Face hub into `target`, reporting how much has arrived."""
    from faster_whisper.utils import _MODELS, download_model

    expected: int | None = None
    try:
        from fnmatch import fnmatch

        from huggingface_hub import HfApi

        info = HfApi().model_info(_MODELS.get(model, model), files_metadata=True)
        expected = (
            sum(
                (s.size or 0)
                for s in info.siblings
                if any(fnmatch(s.rfilename, pat) for pat in _FILE_PATTERNS)
            )
            or None
        )
    except Exception:  # noqa: BLE001 - progress is a nicety
        log.debug("Could not look up the model size", exc_info=True)

    done = threading.Event()

    def poll() -> None:
        while not done.wait(0.5):
            report(min(0.99, _dir_size(target) / expected) if expected else None)

    poller = threading.Thread(target=poll, daemon=True)
    poller.start()
    try:
        download_model(model, output_dir=str(target))
    finally:
        done.set()
        poller.join(1)


class ModelDownloads:
    """Tracks one download per model. A model counts as installed only once it is complete."""

    def __init__(self, models_dir: Path, downloader: Downloader = download_faster_whisper):
        self.models_dir = models_dir
        self._downloader = downloader
        self._state: dict[str, dict] = {}
        self._tasks: set[asyncio.Task] = set()

    def status(self, model: str) -> dict:
        entry = self._state.get(model, {})
        return {
            "installed": is_installed(self.models_dir, model),
            "state": entry.get("state", "idle"),  # idle | downloading | error
            "progress": entry.get("progress"),
            "error": entry.get("error"),
        }

    def start(self, model: str) -> None:
        if (
            is_installed(self.models_dir, model)
            or self._state.get(model, {}).get("state") == "downloading"
        ):
            return
        self._state[model] = {"state": "downloading", "progress": 0.0, "error": None}
        task = asyncio.ensure_future(self._run(model))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, model: str) -> None:
        final = model_dir(self.models_dir, model)
        partial = final.with_name(final.name + ".partial")

        def report(fraction: float | None) -> None:
            self._state[model]["progress"] = fraction

        def work() -> None:
            shutil.rmtree(partial, ignore_errors=True)
            partial.mkdir(parents=True, exist_ok=True)
            self._downloader(model, partial, report)
            shutil.rmtree(final, ignore_errors=True)
            os.replace(partial, final)  # only a finished download becomes "installed"

        try:
            await asyncio.to_thread(work)
            self._state[model] = {"state": "idle", "progress": 1.0, "error": None}
        except Exception as e:  # noqa: BLE001
            log.exception("Model download failed")
            shutil.rmtree(partial, ignore_errors=True)
            self._state[model] = {
                "state": "error",
                "progress": None,
                "error": (
                    f"The download failed ({e.__class__.__name__}). "
                    "Check your connection and try again."
                ),
            }
