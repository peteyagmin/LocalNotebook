"""Text-to-speech behind a small interface (spec §3). The real engine runs the Kokoro ONNX model
with onnxruntime and gets phonemes from the espeak-ng *program* (a subprocess, so no GPL code is
linked into this application).

Files expected in the model folder (a Hugging Face repository named in Settings):
  tokenizer.json          vocabulary: phoneme character -> id (under model.vocab)
  onnx/model.onnx         the network (any *.onnx works; model.onnx is preferred)
  voices/<voice>.bin      float32 style table, shape (N, 1, 256), one file per voice
"""

from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

import numpy as np

SAMPLE_RATE = 24000
MAX_TOKENS = 500  # the model's limit is 510 phoneme tokens including padding
SENTENCE_PAUSE_S = 0.12
STYLE_DIM = 256

# espeak-ng IPA -> symbols in the Kokoro vocabulary (best effort; anything unknown is dropped)
IPA_FIXES = {"r": "ɹ", "x": "k", "ɬ": "l", "ʲ": "j", "ɚ": "əɹ", "ɐ": "ə", "ᵻ": "ɪ"}
ESPEAK_LANGUAGES = {
    "a": "en-us",
    "b": "en-gb",
    "e": "es",
    "f": "fr-fr",
    "h": "hi",
    "i": "it",
    "j": "ja",
    "p": "pt-br",
    "z": "cmn",
}


class TTSUnavailable(Exception):
    """Speech cannot be produced. The message is user-readable."""


class TTSEngine(Protocol):
    sample_rate: int

    def synthesize(self, text: str, voice: str) -> np.ndarray:
        """Mono float32 audio in [-1, 1] at `sample_rate`."""
        ...


def _safe(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name).strip("._") or "model"


def tts_dir(models_dir: Path, repo: str) -> Path:
    return models_dir / "tts" / _safe(repo)


def voice_file(folder: Path, voice: str) -> Path:
    return folder / "voices" / f"{_safe(voice)}.bin"


def model_file(folder: Path) -> Path | None:
    preferred = folder / "onnx" / "model.onnx"
    if preferred.is_file():
        return preferred
    found = sorted(folder.rglob("*.onnx")) if folder.is_dir() else []
    return found[0] if found else None


def is_installed(models_dir: Path, repo: str, voices: list[str]) -> bool:
    if not repo or not all(voices):
        return False
    folder = tts_dir(models_dir, repo)
    return (
        model_file(folder) is not None
        and (folder / "tokenizer.json").is_file()
        and all(voice_file(folder, v).is_file() for v in voices)
    )


def espeak_executable() -> str | None:
    return shutil.which("espeak-ng") or shutil.which("espeak")


def split_sentences(text: str, max_chars: int = 220) -> list[str]:
    """Sentences, with overlong ones broken at commas or spaces so each fits the model."""
    pieces: list[str] = []
    for sentence in re.split(r"(?<=[.!?…])\s+|\n+", text.strip()):
        sentence = sentence.strip()
        while len(sentence) > max_chars:
            cut = max(sentence.rfind(", ", 0, max_chars), sentence.rfind(" ", 0, max_chars))
            cut = cut if cut > 20 else max_chars
            pieces.append(sentence[:cut].strip(" ,"))
            sentence = sentence[cut:].strip(" ,")
        if sentence:
            pieces.append(sentence)
    return pieces


def language_for_voice(voice: str) -> str:
    return ESPEAK_LANGUAGES.get(voice[:1].lower(), "en-us")


def phonemize(text: str, language: str, runner=subprocess.run) -> str:
    """IPA for `text` from the espeak-ng program."""
    exe = espeak_executable()
    if exe is None:
        raise TTSUnavailable(
            "espeak-ng is not installed, so speech cannot be produced. "
            "Install it and add it to PATH."
        )
    result = runner(
        [exe, "-q", "--ipa", "-v", language, "--", text],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise TTSUnavailable("espeak-ng could not read the text.")
    ipa = " ".join(result.stdout.split()).replace("_", " ").replace("͡", "")
    for old, new in IPA_FIXES.items():
        ipa = ipa.replace(old, new)
    return ipa


class KokoroOnnxEngine:
    sample_rate = SAMPLE_RATE

    def __init__(self, session, vocab: dict[str, int], folder: Path, phonemizer=phonemize):
        self._session = session
        self._vocab = vocab
        self._folder = folder
        self._phonemize = phonemizer
        self._voices: dict[str, np.ndarray] = {}
        inputs = session.get_inputs()
        self._ids_name = next(i.name for i in inputs if "int64" in i.type)
        floats = [i for i in inputs if "float" in i.type or "int" in i.type][1:]
        # style is the 256-wide input; speed is the other one
        self._style_name = next(
            (i.name for i in floats if i.shape and i.shape[-1] == STYLE_DIM), floats[0].name
        )
        speed = [i for i in floats if i.name != self._style_name]
        self._speed = (speed[0].name, speed[0].type) if speed else None

    def _style(self, voice: str, token_count: int) -> np.ndarray:
        if voice not in self._voices:
            path = voice_file(self._folder, voice)
            if not path.is_file():
                raise TTSUnavailable(
                    f"The voice '{voice}' is not installed. Download it in Settings, then retry."
                )
            self._voices[voice] = np.fromfile(path, dtype=np.float32).reshape(-1, 1, STYLE_DIM)
        table = self._voices[voice]
        return table[min(token_count, len(table) - 1)]

    def _tokens(self, phonemes: str) -> list[int]:
        return [self._vocab[c] for c in phonemes if c in self._vocab][:MAX_TOKENS]

    def _speak_sentence(self, sentence: str, voice: str) -> np.ndarray:
        tokens = self._tokens(self._phonemize(sentence, language_for_voice(voice)))
        if not tokens:
            return np.zeros(0, dtype=np.float32)
        feed = {
            self._ids_name: np.array([[0, *tokens, 0]], dtype=np.int64),
            self._style_name: self._style(voice, len(tokens)),
        }
        if self._speed:
            name, kind = self._speed
            feed[name] = np.array([1.0], dtype=np.int32 if "int" in kind else np.float32)
        audio = np.asarray(self._session.run(None, feed)[0], dtype=np.float32).reshape(-1)
        return np.clip(audio, -1.0, 1.0)

    def synthesize(self, text: str, voice: str) -> np.ndarray:
        parts: list[np.ndarray] = []
        gap = np.zeros(int(SAMPLE_RATE * SENTENCE_PAUSE_S), dtype=np.float32)
        for sentence in split_sentences(text):
            audio = self._speak_sentence(sentence, voice)
            if audio.size:
                if parts:
                    parts.append(gap)
                parts.append(audio)
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def create_engine(settings: dict, models_dir: Path) -> TTSEngine:
    """The configured engine. LNB_TTS_FACTORY="module:function" swaps in another one (tests,
    development); the function receives (settings, models_dir)."""
    override = os.environ.get("LNB_TTS_FACTORY")
    if override:
        module, _, name = override.partition(":")
        return getattr(importlib.import_module(module), name)(settings, models_dir)
    repo, voices = settings["tts_model"], [settings["tts_voice_a"], settings["tts_voice_b"]]
    if not repo:
        raise TTSUnavailable("No text-to-speech model is configured. Choose one in Settings.")
    if not all(voices):
        raise TTSUnavailable("Choose a voice for Host A and Host B in Settings.")
    if not is_installed(models_dir, repo, voices):
        raise TTSUnavailable(
            f"The text-to-speech model '{repo}' and its voices are not installed. "
            "Download them in Settings, then retry."
        )
    if espeak_executable() is None:
        raise TTSUnavailable("espeak-ng is not installed, so speech cannot be produced.")
    import onnxruntime

    folder = tts_dir(models_dir, repo)
    vocab = json.loads((folder / "tokenizer.json").read_text(encoding="utf-8"))["model"]["vocab"]
    session = onnxruntime.InferenceSession(
        str(model_file(folder)), providers=["CPUExecutionProvider"]
    )
    return KokoroOnnxEngine(session, vocab, folder)
