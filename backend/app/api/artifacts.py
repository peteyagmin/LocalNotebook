from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.api.deps import get_runner, get_store
from app.core.errors import AppError
from app.core.notebooks import NotebookStore
from app.studio import audio, service
from app.studio import export as export_module
from app.studio.generate import artifact_dir

router = APIRouter()


class NewArtifact(BaseModel):
    kind: str
    focus: str | None = None
    options: dict | None = None  # audio overview: {"length": ..., "format": ...}


class Regenerate(BaseModel):
    focus: str | None = None
    options: dict | None = None


class ScriptTurnBody(BaseModel):
    speaker: str
    text: str
    chunk_ids: list[str] = []


class ScriptBody(BaseModel):
    turns: list[ScriptTurnBody]


def _conn(store: NotebookStore, notebook_id: str):
    return store.open(notebook_id)


@router.get("/notebooks/{notebook_id}/artifacts")
def list_artifacts(notebook_id: str, store: NotebookStore = Depends(get_store)) -> list[dict]:
    conn = _conn(store, notebook_id)
    try:
        return service.list_artifacts(conn)
    finally:
        conn.close()


@router.post("/notebooks/{notebook_id}/artifacts", status_code=202)
def create_artifact(
    notebook_id: str,
    body: NewArtifact,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
) -> dict:
    focus = service.validate_focus(body.focus)
    conn = _conn(store, notebook_id)
    try:
        artifact_id = service.create_artifact(conn, body.kind, focus, body.options)
        runner.submit_artifact(notebook_id, artifact_id)
        return service.get_artifact(store, notebook_id, conn, artifact_id)
    finally:
        conn.close()


@router.get("/notebooks/{notebook_id}/artifacts/stream")
async def stream_artifacts(
    notebook_id: str, request: Request, store: NotebookStore = Depends(get_store)
) -> StreamingResponse:
    """SSE snapshots of the artifact list while any generation is queued or running (FR-5.12)."""
    store.get(notebook_id)

    def snapshot() -> list[dict]:
        conn = _conn(store, notebook_id)
        try:
            return service.list_artifacts(conn)
        finally:
            conn.close()

    async def events():
        last = None
        while not await request.is_disconnected():
            try:
                items = await asyncio.to_thread(snapshot)
            except Exception:
                return
            payload = json.dumps(items)
            if payload != last:
                last = payload
                yield f"data: {payload}\n\n"
            if not any(a["state"] in service.ACTIVE_STATES for a in items):
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/notebooks/{notebook_id}/artifacts/{artifact_id}")
def get_artifact(
    notebook_id: str, artifact_id: str, store: NotebookStore = Depends(get_store)
) -> dict:
    conn = _conn(store, notebook_id)
    try:
        return service.get_artifact(store, notebook_id, conn, artifact_id)
    finally:
        conn.close()


@router.post("/notebooks/{notebook_id}/artifacts/{artifact_id}/regenerate", status_code=202)
def regenerate(
    notebook_id: str,
    artifact_id: str,
    body: Regenerate | None = None,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
) -> dict:
    conn = _conn(store, notebook_id)
    try:
        row = service.get_row(conn, artifact_id)
        if row["state"] in service.ACTIVE_STATES:
            raise AppError(409, "already_running", "This is already being generated.")
        if body is not None and body.focus is not None:
            focus = service.validate_focus(body.focus)
            with conn:
                conn.execute("UPDATE artifacts SET focus = ? WHERE id = ?", (focus, artifact_id))
        if body is not None and body.options is not None and row["kind"] == "audio_overview":
            current = json.loads(row["options"]) if row["options"] else {}
            options = audio.normalize_options({**current, **body.options})
            with conn:
                conn.execute(
                    "UPDATE artifacts SET options = ? WHERE id = ?",
                    (json.dumps(options), artifact_id),
                )
        runner.submit_artifact(notebook_id, artifact_id)
        return service.get_artifact(store, notebook_id, conn, artifact_id)
    finally:
        conn.close()


@router.post("/notebooks/{notebook_id}/artifacts/{artifact_id}/cancel", status_code=204)
def cancel(
    notebook_id: str,
    artifact_id: str,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
) -> Response:
    conn = _conn(store, notebook_id)
    try:
        service.get_row(conn, artifact_id)
    finally:
        conn.close()
    runner.cancel_artifact(artifact_id)
    return Response(status_code=204)


@router.delete("/notebooks/{notebook_id}/artifacts/{artifact_id}", status_code=204)
def delete_artifact(
    notebook_id: str,
    artifact_id: str,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
) -> Response:
    conn = _conn(store, notebook_id)
    try:
        service.get_row(conn, artifact_id)
        runner.cancel_artifact(artifact_id)
        service.delete_artifact(store, notebook_id, conn, artifact_id)
    finally:
        conn.close()
    return Response(status_code=204)


@router.get("/notebooks/{notebook_id}/artifacts/{artifact_id}/export")
def export_artifact(
    notebook_id: str,
    artifact_id: str,
    format: str = Query(pattern="^(md|docx|pdf|json|png|csv-flashcards|csv-quiz|mp3)$"),
    store: NotebookStore = Depends(get_store),
) -> Response:
    conn = _conn(store, notebook_id)
    try:
        artifact = service.get_artifact(store, notebook_id, conn, artifact_id)
    finally:
        conn.close()
    if not artifact["has_content"]:
        raise AppError(409, "not_ready", "This has not been generated yet.")
    if format not in export_module.ALLOWED_FORMATS[artifact["kind"]]:
        raise AppError(422, "unsupported_format", f"This cannot be exported as {format}.")
    if format == "mp3":
        data = (artifact_dir(store, notebook_id, artifact_id) / "audio.mp3").read_bytes()
        name = export_module.filename(artifact["title"], "mp3")
        return Response(
            data,
            media_type="audio/mpeg",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )
    used = [c for c in artifact["citations"] if not c.get("removed")]
    if artifact["format"] == "json":
        data, media_type, name = export_module.export_structured(
            format, artifact["kind"], artifact["title"], artifact["data"], used
        )
    else:
        data, media_type, name = export_module.export(
            format, artifact["title"], artifact["content"], used
        )
    return Response(
        data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.put("/notebooks/{notebook_id}/artifacts/{artifact_id}/script")
def edit_script(
    notebook_id: str,
    artifact_id: str,
    body: ScriptBody,
    store: NotebookStore = Depends(get_store),
) -> dict:
    """Edit an audio overview's script: text, speakers, order, deletions (FR-6.4)."""
    conn = _conn(store, notebook_id)
    try:
        service.save_script(
            store, notebook_id, conn, artifact_id, [t.model_dump() for t in body.turns]
        )
        return service.get_artifact(store, notebook_id, conn, artifact_id)
    finally:
        conn.close()


@router.post("/notebooks/{notebook_id}/artifacts/{artifact_id}/resynthesize", status_code=202)
def resynthesize(
    notebook_id: str,
    artifact_id: str,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
) -> dict:
    """Rebuild the audio from the current script without writing a new script (FR-6.4)."""
    conn = _conn(store, notebook_id)
    try:
        row = service.get_row(conn, artifact_id)
        if row["kind"] != "audio_overview" or not row["has_content"]:
            raise AppError(409, "no_script", "This has no script to speak.")
        if row["state"] in service.ACTIVE_STATES:
            raise AppError(409, "already_running", "This is already being generated.")
        runner.submit_resynthesis(notebook_id, artifact_id)
        return service.get_artifact(store, notebook_id, conn, artifact_id)
    finally:
        conn.close()


@router.get("/notebooks/{notebook_id}/artifacts/{artifact_id}/audio")
def get_audio(
    notebook_id: str, artifact_id: str, store: NotebookStore = Depends(get_store)
) -> FileResponse:
    conn = _conn(store, notebook_id)
    try:
        service.get_row(conn, artifact_id)
    finally:
        conn.close()
    path = artifact_dir(store, notebook_id, artifact_id) / "audio.mp3"
    if not path.exists():
        raise AppError(404, "not_found", "There is no audio yet.")
    return FileResponse(path, media_type="audio/mpeg")
