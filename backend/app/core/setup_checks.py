"""First-launch dependency checks for the setup wizard (FR-8.3, FR-8.2)."""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass

from app.llm.base import LLMClient, LLMError


@dataclass
class Check:
    id: str
    label: str
    ok: bool
    detail: str
    fix: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _model_installed(name: str, installed: list[str]) -> bool:
    return name in installed or f"{name}:latest" in installed


def _model_check(check_id: str, label: str, name: str, installed: list[str] | None) -> Check:
    if not name:
        return Check(check_id, label, False, "Not configured.", "Choose a model in Settings.")
    if installed is None:
        return Check(check_id, label, False, f"Cannot verify '{name}': model server unreachable.")
    if _model_installed(name, installed):
        return Check(check_id, label, True, f"'{name}' is installed.")
    return Check(check_id, label, False, f"'{name}' is not installed.", f"Run: ollama pull {name}")


async def run_checks(settings: dict, llm: LLMClient) -> list[Check]:
    installed: list[str] | None
    try:
        installed = await llm.list_models()
        server = Check(
            "llm_server",
            "Model server reachable",
            True,
            f"{len(installed)} model(s) installed.",
        )
    except LLMError as e:
        installed = None
        server = Check(
            "llm_server",
            "Model server reachable",
            False,
            str(e),
            "Install and start Ollama, or set the endpoint in Settings.",
        )

    checks = [
        server,
        _model_check("chat_model", "Chat model installed", settings["chat_model"], installed),
        _model_check(
            "embedding_model",
            "Embedding model installed",
            settings["embedding_model"],
            installed,
        ),
    ]
    for exe, label, fix in (
        ("tesseract", "Tesseract (OCR) installed", "Install Tesseract and add it to PATH."),
        ("ffmpeg", "ffmpeg installed", "Install ffmpeg and add it to PATH."),
        (
            "espeak-ng",
            "espeak-ng installed (for audio overviews)",
            "Install espeak-ng and add it to PATH.",
        ),
    ):
        path = shutil.which(exe)
        checks.append(
            Check(exe, label, path is not None, path or "Not found on PATH.", None if path else fix)
        )
    return checks
