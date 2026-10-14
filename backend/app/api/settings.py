from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_db, get_llm, get_settings
from app.core import settings_store
from app.core.setup_checks import run_checks
from app.llm.base import LLMClient, LLMError

router = APIRouter()


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_model: str | None = None
    embedding_model: str | None = None
    stt_model: str | None = None
    tts_model: str | None = None
    tts_voice_a: str | None = None
    tts_voice_b: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    setup_completed: bool | None = None
    max_sources_per_notebook: int | None = Field(default=None, ge=1)
    max_upload_mb: int | None = Field(default=None, ge=1)
    retrieval_top_k: int | None = Field(default=None, ge=1, le=20)
    context_window_tokens: int | None = Field(default=None, ge=1000)
    allow_web_import: bool | None = None
    allow_discover: bool | None = None
    allow_model_downloads: bool | None = None
    transcribe_uncaptioned_videos: bool | None = None
    searxng_url: str | None = None


@router.get("/settings")
def read_settings(settings: dict = Depends(get_settings)) -> dict:
    return settings


@router.put("/settings")
def update_settings(
    body: SettingsUpdate,
    conn: sqlite3.Connection = Depends(get_db),
    settings: dict = Depends(get_settings),
) -> dict:
    settings_store.update(conn, body.model_dump(exclude_none=True))
    return {**settings, **body.model_dump(exclude_none=True)}


@router.post("/settings/test-connection")
async def test_connection(llm: LLMClient = Depends(get_llm)) -> dict:
    try:
        models = await llm.list_models()
    except LLMError as e:
        return {"ok": False, "message": str(e), "models": []}
    return {
        "ok": True,
        "message": f"Connected. {len(models)} model(s) installed.",
        "models": models,
    }


@router.get("/setup/checks")
async def setup_checks(
    settings: dict = Depends(get_settings), llm: LLMClient = Depends(get_llm)
) -> dict:
    return {"checks": [c.to_dict() for c in await run_checks(settings, llm)]}
