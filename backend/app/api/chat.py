from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.api.deps import get_settings, get_store
from app.chat import service
from app.core.notebooks import NotebookStore
from app.llm.base import LLMError

router = APIRouter()


class Question(BaseModel):
    question: str = Field(max_length=4000)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be blank")
        return v.strip()


class ChatSettings(BaseModel):
    response_style: Literal["default", "concise", "detailed", "learning_guide"]
    custom_instruction: str = Field(max_length=1000)


@router.get("/notebooks/{notebook_id}/chat")
def get_chat(notebook_id: str, store: NotebookStore = Depends(get_store)) -> list[dict]:
    conn = store.open(notebook_id)
    try:
        return service.list_messages(conn)
    finally:
        conn.close()


@router.delete("/notebooks/{notebook_id}/chat", status_code=204)
def clear_chat(notebook_id: str, store: NotebookStore = Depends(get_store)) -> Response:
    conn = store.open(notebook_id)
    try:
        service.clear_chat(conn)
    finally:
        conn.close()
    return Response(status_code=204)


@router.get("/notebooks/{notebook_id}/chat/settings")
def get_chat_settings(notebook_id: str, store: NotebookStore = Depends(get_store)) -> dict:
    conn = store.open(notebook_id)
    try:
        return service.get_chat_settings(conn)
    finally:
        conn.close()


@router.put("/notebooks/{notebook_id}/chat/settings")
def put_chat_settings(
    notebook_id: str, body: ChatSettings, store: NotebookStore = Depends(get_store)
) -> dict:
    conn = store.open(notebook_id)
    try:
        return service.set_chat_settings(conn, body.response_style, body.custom_instruction)
    finally:
        conn.close()


@router.get("/notebooks/{notebook_id}/chat/starters")
async def starters(
    notebook_id: str,
    request: Request,
    store: NotebookStore = Depends(get_store),
    settings: dict = Depends(get_settings),
) -> dict:
    store.get(notebook_id)
    if not settings["chat_model"]:
        return {"questions": []}
    llm = request.app.state.llm_factory(settings)
    try:
        return {
            "questions": await service.starter_questions(
                store, notebook_id, llm, settings["chat_model"]
            )
        }
    except LLMError:
        return {"questions": []}
    finally:
        close = getattr(llm, "aclose", None)
        if close:
            await close()


@router.post("/notebooks/{notebook_id}/chat/stop", status_code=204)
async def stop_chat(notebook_id: str, request: Request) -> Response:
    """Stop the answer being generated for this notebook (FR-3.8)."""
    event = request.app.state.chat_stops.get(notebook_id)
    if event is not None:
        event.set()
    return Response(status_code=204)


@router.post("/notebooks/{notebook_id}/chat")
async def ask(
    notebook_id: str,
    body: Question,
    request: Request,
    store: NotebookStore = Depends(get_store),
    settings: dict = Depends(get_settings),
) -> StreamingResponse:
    """Server-Sent Events: user_message, sources, token*, done, suggestions | error."""
    store.get(notebook_id)
    stop = asyncio.Event()
    request.app.state.chat_stops[notebook_id] = stop
    llm = request.app.state.llm_factory(settings)

    async def events():
        try:
            async for event in service.stream_answer(
                store, notebook_id, body.question, llm, settings, stop
            ):
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            if request.app.state.chat_stops.get(notebook_id) is stop:
                del request.app.state.chat_stops[notebook_id]
            close = getattr(llm, "aclose", None)
            if close:
                await close()

    return StreamingResponse(events(), media_type="text/event-stream")
