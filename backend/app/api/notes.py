from __future__ import annotations

import json
from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import get_runner, get_settings, get_store
from app.chat.citations import strip_citations
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.notebooks import NotebookStore, NotFound
from app.ingest import service as source_service
from app.ingest.chunker import est_tokens
from app.llm.base import LLMError
from app.llm.prompts import render_prompt
from app.notes import service
from app.studio.generate import OUTPUT_RESERVE_TOKENS, PROMPT_OVERHEAD_TOKENS, build_messages

router = APIRouter()
T = TypeVar("T")


class NoteCreate(BaseModel):
    title: str = Field(default="", max_length=200)
    content: str = Field(default="", max_length=500_000)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, max_length=500_000)


class NoteIds(BaseModel):
    note_ids: list[str] = Field(min_length=1)


def _with_conn(store: NotebookStore, notebook_id: str, fn: Callable):
    conn = store.open(notebook_id)
    try:
        return fn(conn)
    finally:
        conn.close()


@router.get("/notebooks/{notebook_id}/notes")
def list_notes(notebook_id: str, store: NotebookStore = Depends(get_store)) -> list[dict]:
    return _with_conn(store, notebook_id, service.list_notes)


@router.post("/notebooks/{notebook_id}/notes", status_code=201)
def create_note(
    notebook_id: str,
    body: NoteCreate,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
) -> dict:
    note = _with_conn(
        store, notebook_id, lambda c: service.create_note(c, body.title, body.content)
    )
    runner.submit_note_index(notebook_id, note["id"])
    return note


@router.get("/notebooks/{notebook_id}/notes/{note_id}")
def get_note(notebook_id: str, note_id: str, store: NotebookStore = Depends(get_store)) -> dict:
    return _with_conn(store, notebook_id, lambda c: service.get_note(c, note_id))


@router.patch("/notebooks/{notebook_id}/notes/{note_id}")
def update_note(
    notebook_id: str,
    note_id: str,
    body: NoteUpdate,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
) -> dict:
    note = _with_conn(
        store, notebook_id, lambda c: service.update_note(c, note_id, body.title, body.content)
    )
    runner.submit_note_index(notebook_id, note_id)
    return note


@router.delete("/notebooks/{notebook_id}/notes/{note_id}", status_code=204)
def delete_note(
    notebook_id: str, note_id: str, store: NotebookStore = Depends(get_store)
) -> Response:
    _with_conn(store, notebook_id, lambda c: service.delete_note(c, note_id))
    return Response(status_code=204)


def _load_selected(conn, note_ids: list[str]) -> list[dict]:
    return [service.get_note(conn, nid) for nid in note_ids]


@router.post("/notebooks/{notebook_id}/notes/combine", status_code=201)
def combine_notes(
    notebook_id: str,
    body: NoteIds,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
) -> dict:
    """One new note holding the selected notes in order, citations renumbered. Originals stay."""

    def go(conn):
        content, citations = service.merge_notes(_load_selected(conn, body.note_ids))
        return service.create_note(conn, "Combined notes", content, citations)

    note = _with_conn(store, notebook_id, go)
    runner.submit_note_index(notebook_id, note["id"])
    return note


@router.post("/notebooks/{notebook_id}/notes/summarize", status_code=201)
async def summarize_notes(
    notebook_id: str,
    body: NoteIds,
    request: Request,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
    settings: dict = Depends(get_settings),
) -> dict:
    """A model-written summary of the selected notes, saved as a new note."""
    if not settings["chat_model"]:
        raise AppError(400, "not_configured", "Choose a chat model in Settings first.")
    content, citations = _with_conn(
        store, notebook_id, lambda c: service.merge_notes(_load_selected(c, body.note_ids))
    )
    budget = settings["context_window_tokens"] - OUTPUT_RESERVE_TOKENS - PROMPT_OVERHEAD_TOKENS
    if est_tokens(len(content)) > budget:
        raise AppError(
            400, "too_long", "The selected notes are too long to summarize at once. Select fewer."
        )
    llm = request.app.state.llm_factory(settings)
    try:
        reply = await llm.chat(
            settings["chat_model"],
            build_messages(render_prompt("notes_summarize"), content, ""),
        )
    except LLMError as e:
        raise AppError(502, "llm_error", str(e)) from e
    finally:
        close = getattr(llm, "aclose", None)
        if close:
            await close()
    text, used = service.filter_to_valid(reply.strip(), citations)
    if not text.strip():
        raise AppError(502, "empty_answer", "The model returned an empty summary. Try again.")
    count = len(body.note_ids)
    title = f"Summary of {count} note{'s' if count != 1 else ''}"
    note = _with_conn(store, notebook_id, lambda c: service.create_note(c, title, text, used))
    runner.submit_note_index(notebook_id, note["id"])
    return note


@router.post("/notebooks/{notebook_id}/notes/convert-to-source", status_code=202)
def convert_to_source(
    notebook_id: str,
    body: NoteIds,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
    settings: dict = Depends(get_settings),
) -> list[dict]:
    """A new pasted-text source from each selected note (FR-4.3); it is then ingested normally."""
    conn = store.open(notebook_id)
    try:
        notes = _load_selected(conn, body.note_ids)
        limit = settings["max_sources_per_notebook"]
        if source_service.source_count(conn) + len(notes) > limit:
            raise AppError(
                400,
                "source_limit",
                f"A notebook can hold up to {limit} sources. Remove one first.",
            )
        created = []
        for note in notes:
            text = f"{note['title']}\n\n{strip_citations(note['content'])}".strip()
            source_id = new_id()
            folder = store.source_dir(notebook_id, source_id)
            folder.mkdir(parents=True)
            data = text.encode("utf-8")
            (folder / "original.txt").write_bytes(data)
            source_service.create_source(
                conn,
                source_id=source_id,
                name=note["title"],
                source_type="text",
                original_name="pasted.txt",
                size_bytes=len(data),
            )
            created.append(source_id)
        store.touch(notebook_id)
        for source_id in created:
            runner.submit_ingest(notebook_id, source_id)
        return [source_service.get_source(conn, sid) for sid in created]
    finally:
        conn.close()


@router.post("/notebooks/{notebook_id}/chat/messages/{message_id}/save-note", status_code=201)
def save_message_to_note(
    notebook_id: str,
    message_id: str,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
) -> dict:
    """Keep an assistant answer as a note with its citations (FR-3.6)."""

    def go(conn):
        rows = conn.execute("SELECT * FROM chat_messages ORDER BY created_at, id").fetchall()
        index = next((n for n, r in enumerate(rows) if r["id"] == message_id), None)
        if index is None:
            raise NotFound(message_id)
        row = rows[index]
        if row["role"] != "assistant":
            raise AppError(400, "not_an_answer", "Only an assistant answer can be saved.")
        question = next(
            (r["content"] for r in reversed(rows[:index]) if r["role"] == "user"), "Saved answer"
        )
        title = " ".join(question.split())[:80]
        return service.create_note(conn, title, row["content"], json.loads(row["citations"]))

    note = _with_conn(store, notebook_id, go)
    runner.submit_note_index(notebook_id, note["id"])
    return note
