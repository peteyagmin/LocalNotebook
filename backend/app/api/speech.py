from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.deps import get_settings
from app.core.errors import AppError
from app.ingest import ocr
from app.speech import tts

router = APIRouter()


class ConfirmDownload(BaseModel):
    confirm: bool = False


@router.get("/speech/stt")
def stt_status(request: Request, settings: dict = Depends(get_settings)) -> dict:
    model = settings["stt_model"]
    downloads = request.app.state.model_downloads
    return {
        "model": model,
        "configured": bool(model),
        "downloads_allowed": settings["allow_model_downloads"],
        **(downloads.status(model) if model else {"installed": False, "state": "idle"}),
    }


@router.post("/speech/stt/download", status_code=202)
async def stt_download(
    body: ConfirmDownload, request: Request, settings: dict = Depends(get_settings)
) -> dict:
    """Start downloading the speech-to-text model. Needs the user's confirmation (FR-8.2)."""
    model = settings["stt_model"]
    if not model:
        raise AppError(400, "not_configured", "Choose a speech-to-text model in Settings first.")
    if not settings["allow_model_downloads"]:
        raise AppError(403, "network_disabled", "Model downloads are turned off in Settings.")
    if not body.confirm:
        raise AppError(400, "needs_confirmation", "Confirm that you want to download the model.")
    downloads = request.app.state.model_downloads
    downloads.start(model)
    return downloads.status(model)


def _tts_status(request: Request, settings: dict) -> dict:
    repo = settings["tts_model"]
    voices = [settings["tts_voice_a"], settings["tts_voice_b"]]
    downloads = request.app.state.tts_downloads
    status = (
        downloads.status(repo, {"voices": voices})
        if repo and all(voices)
        else {
            "installed": False,
            "state": "idle",
        }
    )
    return {
        "model": repo,
        "voices": voices,
        "configured": bool(repo) and all(voices),
        "downloads_allowed": settings["allow_model_downloads"],
        "espeak": tts.espeak_executable() is not None,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        **status,
    }


@router.get("/speech/tts")
def tts_status(request: Request, settings: dict = Depends(get_settings)) -> dict:
    return _tts_status(request, settings)


@router.post("/speech/tts/download", status_code=202)
async def tts_download(
    body: ConfirmDownload, request: Request, settings: dict = Depends(get_settings)
) -> dict:
    """Download the text-to-speech model and the two voices. Needs the user's confirmation."""
    voices = [settings["tts_voice_a"], settings["tts_voice_b"]]
    if not settings["tts_model"] or not all(voices):
        raise AppError(
            400, "not_configured", "Enter a text-to-speech model and both voices in Settings first."
        )
    if not settings["allow_model_downloads"]:
        raise AppError(403, "network_disabled", "Model downloads are turned off in Settings.")
    if not body.confirm:
        raise AppError(400, "needs_confirmation", "Confirm that you want to download the model.")
    request.app.state.tts_downloads.start(settings["tts_model"], {"voices": voices})
    return _tts_status(request, settings)


@router.get("/capabilities")
def capabilities(request: Request, settings: dict = Depends(get_settings)) -> dict:
    """What this machine and these settings can do, so the UI can explain what is disabled."""
    downloads = request.app.state.model_downloads
    model = settings["stt_model"]
    return {
        "ocr": ocr.available(),
        "stt": {
            "configured": bool(model),
            "installed": bool(model) and downloads.status(model)["installed"],
        },
        "audio_overview": _audio_capability(request, settings),
        "web_import": settings["allow_web_import"],
        "discover": {
            "allowed": settings["allow_discover"],
            "configured": bool((settings["searxng_url"] or "").strip()),
        },
    }


def _audio_capability(request: Request, settings: dict) -> dict:
    """Everything an audio overview needs, so the UI can say what is missing."""
    status = _tts_status(request, settings)
    problems = []
    if not settings["chat_model"]:
        problems.append("Choose a chat model in Settings.")
    if not status["configured"]:
        problems.append("Choose a text-to-speech model and two voices in Settings.")
    elif not status["installed"]:
        problems.append("Download the text-to-speech model and voices in Settings.")
    if not status["espeak"]:
        problems.append("Install espeak-ng (it turns text into sounds).")
    if not status["ffmpeg"]:
        problems.append("Install ffmpeg (it makes the MP3).")
    return {"ready": not problems, "problems": problems}
