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
    """Tracks one download per model. A model counts as installed only once it is complete.

    By default it manages speech-to-text models. `installed`, `dest` and `staged` adapt it to
    other kinds: with `staged=False` the downloader writes straight into `dest` (its own file
    handling already makes files appear complete or not at all)."""

    def __init__(
        self,
        models_dir: Path,
        downloader: Downloader = download_faster_whisper,
        installed: Callable[[Path, str, dict], bool] | None = None,
        dest: Callable[[Path, str], Path] | None = None,
        staged: bool = True,
    ):
        self.models_dir = models_dir
        self._downloader = downloader
        self._installed = installed or (lambda root, model, extra: is_installed(root, model))
        self._dest = dest or model_dir
        self._staged = staged
        self._state: dict[str, dict] = {}
        self._tasks: set[asyncio.Task] = set()

    def status(self, model: str, extra: dict | None = None) -> dict:
        entry = self._state.get(model, {})
        return {
            "installed": self._installed(self.models_dir, model, extra or {}),
            "state": entry.get("state", "idle"),  # idle | downloading | error
            "progress": entry.get("progress"),
            "error": entry.get("error"),
        }

    def start(self, model: str, extra: dict | None = None) -> None:
        if (
            self._installed(self.models_dir, model, extra or {})
            or self._state.get(model, {}).get("state") == "downloading"
        ):
            return
        self._state[model] = {"state": "downloading", "progress": 0.0, "error": None}
        task = asyncio.ensure_future(self._run(model, extra))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, model: str, extra: dict | None = None) -> None:
        final = self._dest(self.models_dir, model)
        partial = final.with_name(final.name + ".partial") if self._staged else final

        def report(fraction: float | None) -> None:
            self._state[model]["progress"] = fraction

        def work() -> None:
            if self._staged:
                shutil.rmtree(partial, ignore_errors=True)
            partial.mkdir(parents=True, exist_ok=True)
            if extra is None:
                self._downloader(model, partial, report)
            else:
                self._downloader(model, partial, report, extra)
            if self._staged:
                shutil.rmtree(final, ignore_errors=True)
                os.replace(partial, final)  # only a finished download becomes "installed"
            elif not self._installed(self.models_dir, model, extra or {}):
                raise FileNotFoundError("the download did not contain the expected files")

        try:
            await asyncio.to_thread(work)
            self._state[model] = {"state": "idle", "progress": 1.0, "error": None}
        except Exception as e:  # noqa: BLE001
            log.exception("Model download failed")
            if self._staged:
                shutil.rmtree(partial, ignore_errors=True)
            self._state[model] = {
                "state": "error",
                "progress": None,
                "error": (
                    f"The download failed ({e.__class__.__name__}). "
                    "Check your connection and try again."
                ),
            }


TTS_PATTERNS = ["tokenizer.json", "config.json", "onnx/model.onnx"]


def download_tts(
    repo: str, target: Path, report: Callable[[float | None], None], extra: dict
) -> None:
    """Download the text-to-speech model and the configured voices from the Hugging Face hub."""
    from fnmatch import fnmatch

    from huggingface_hub import HfApi, snapshot_download

    patterns = TTS_PATTERNS + [f"voices/{v}.bin" for v in extra.get("voices", []) if v]
    expected: int | None = None
    try:
        info = HfApi().model_info(repo, files_metadata=True)
        expected = (
            sum(
                (s.size or 0)
                for s in info.siblings
                if any(fnmatch(s.rfilename, p) for p in patterns)
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
        snapshot_download(repo_id=repo, local_dir=str(target), allow_patterns=patterns)
    finally:
        done.set()
        poller.join(1)
