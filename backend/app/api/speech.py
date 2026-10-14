from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.deps import get_settings
from app.core.errors import AppError
from app.ingest import ocr

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
        "web_import": settings["allow_web_import"],
        "discover": {
            "allowed": settings["allow_discover"],
            "configured": bool((settings["searxng_url"] or "").strip()),
        },
    }
