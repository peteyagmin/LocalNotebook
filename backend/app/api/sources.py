from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import get_runner, get_services, get_settings, get_store
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.notebooks import NotebookStore
from app.ingest import safe_fetch, service
from app.ingest.extract import read_extracted
from app.ingest.parsers import SUPPORTED_EXTENSIONS
from app.ingest.pipeline import extracted_path
from app.ingest.youtube import choose_language_order, is_youtube_url, parse_video_id

router = APIRouter()

SUPPORTED_HINT = "Supported types: PDF, DOCX, TXT, Markdown, HTML, EPUB, PNG, JPG, MP3, WAV, M4A."
COPY_BLOCK = 1024 * 1024


class PastedText(BaseModel):
    name: str | None = None
    text: str


class UrlImport(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=50)


class EnabledBody(BaseModel):
    enabled: bool


def _too_large(name: str, settings: dict) -> AppError:
    limit = settings["max_upload_mb"]
    return AppError(413, "file_too_large", f"'{name}' is larger than the {limit} MB limit.")


def _check_capacity(conn, settings: dict, new_count: int) -> None:
    limit = settings["max_sources_per_notebook"]
    if service.source_count(conn) + new_count > limit:
        raise AppError(
            400, "source_limit", f"A notebook can hold up to {limit} sources. Remove one first."
        )


def _create_and_queue(store, runner, notebook_id, conn, items: list[dict]) -> list[dict]:
    for item in items:
        service.create_source(conn, **item)
    store.touch(notebook_id)
    for item in items:
        runner.submit_ingest(notebook_id, item["source_id"])
    return [service.get_source(conn, item["source_id"]) for item in items]


@router.get("/notebooks/{notebook_id}/sources")
def list_sources(notebook_id: str, store: NotebookStore = Depends(get_store)) -> list[dict]:
    conn = store.open(notebook_id)
    try:
        return service.list_sources(conn)
    finally:
        conn.close()


@router.get("/notebooks/{notebook_id}/sources/stream")
async def stream_sources(
    notebook_id: str, request: Request, store: NotebookStore = Depends(get_store)
) -> StreamingResponse:
    """Server-Sent Events: a snapshot of the sources list whenever it changes. The stream ends
    once nothing is queued or processing; the client reconnects after it starts more work."""
    store.get(notebook_id)

    def snapshot() -> list[dict]:
        conn = store.open(notebook_id)
        try:
            return service.list_sources(conn)
        finally:
            conn.close()

    async def events():
        last = None
        while not await request.is_disconnected():
            try:
                sources = await asyncio.to_thread(snapshot)
            except Exception:
                return
            payload = json.dumps(sources)
            if payload != last:
                last = payload
                yield f"data: {payload}\n\n"
            if not any(s["state"] in ("queued", "processing") for s in sources):
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/notebooks/{notebook_id}/sources/files", status_code=202)
async def upload_files(
    notebook_id: str,
    files: list[UploadFile],
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
    settings: dict = Depends(get_settings),
) -> list[dict]:
    conn = store.open(notebook_id)
    try:
        max_bytes = settings["max_upload_mb"] * 1024 * 1024
        _check_capacity(conn, settings, len(files))
        # Validate everything before any work starts (FR-2.5).
        for f in files:
            name = Path(f.filename or "").name
            if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
                raise AppError(
                    400,
                    "unsupported_type",
                    f"'{name or 'This file'}' is not supported. {SUPPORTED_HINT}",
                )
            if f.size is not None and f.size > max_bytes:
                raise _too_large(name, settings)
        items: list[dict] = []
        try:
            for f in files:
                name = Path(f.filename or "").name
                ext = Path(name).suffix.lower()
                source_id = new_id()
                folder = store.source_dir(notebook_id, source_id)
                folder.mkdir(parents=True)
                size = 0
                with (folder / f"original{ext}").open("wb") as out:
                    while block := await f.read(COPY_BLOCK):
                        size += len(block)
                        if size > max_bytes:
                            raise _too_large(name, settings)
                        out.write(block)
                items.append(
                    dict(
                        source_id=source_id,
                        name=name,
                        source_type=SUPPORTED_EXTENSIONS[ext],
                        original_name=name,
                        size_bytes=size,
                    )
                )
        except Exception:
            for item in items:
                shutil.rmtree(store.source_dir(notebook_id, item["source_id"]), ignore_errors=True)
            shutil.rmtree(store.source_dir(notebook_id, source_id), ignore_errors=True)
            raise
        return _create_and_queue(store, runner, notebook_id, conn, items)
    finally:
        conn.close()


@router.post("/notebooks/{notebook_id}/sources/text", status_code=202)
def paste_text(
    notebook_id: str,
    body: PastedText,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
    settings: dict = Depends(get_settings),
) -> list[dict]:
    if not body.text.strip():
        raise AppError(400, "empty_text", "Paste some text first.")
    data = body.text.encode("utf-8")
    if len(data) > settings["max_upload_mb"] * 1024 * 1024:
        raise AppError(
            413,
            "file_too_large",
            f"The text is larger than the {settings['max_upload_mb']} MB limit.",
        )
    conn = store.open(notebook_id)
    try:
        _check_capacity(conn, settings, 1)
        source_id = new_id()
        folder = store.source_dir(notebook_id, source_id)
        folder.mkdir(parents=True)
        (folder / "original.txt").write_bytes(data)
        item = dict(
            source_id=source_id,
            name=(body.name or "").strip() or "Pasted text",
            source_type="text",
            original_name="pasted.txt",
            size_bytes=len(data),
        )
        return _create_and_queue(store, runner, notebook_id, conn, [item])
    finally:
        conn.close()


@router.post("/notebooks/{notebook_id}/sources/enabled")
def set_all_enabled(
    notebook_id: str, body: EnabledBody, store: NotebookStore = Depends(get_store)
) -> list[dict]:
    """Select all / none (FR-2.7)."""
    conn = store.open(notebook_id)
    try:
        service.set_all_enabled(conn, body.enabled)
        return service.list_sources(conn)
    finally:
        conn.close()


@router.get("/notebooks/{notebook_id}/sources/{source_id}")
def get_source(notebook_id: str, source_id: str, store: NotebookStore = Depends(get_store)) -> dict:
    conn = store.open(notebook_id)
    try:
        return service.get_source(conn, source_id)
    finally:
        conn.close()


@router.get("/notebooks/{notebook_id}/sources/{source_id}/content")
def get_content(
    notebook_id: str, source_id: str, store: NotebookStore = Depends(get_store)
) -> dict:
    """Extracted text with location segments, for the source viewer (FR-2.8)."""
    conn = store.open(notebook_id)
    try:
        service.get_source(conn, source_id)
    finally:
        conn.close()
    path = extracted_path(store, notebook_id, source_id)
    if not path.exists():
        raise AppError(409, "not_ready", "This source has no extracted text yet.")
    return read_extracted(path)


@router.patch("/notebooks/{notebook_id}/sources/{source_id}")
def update_source(
    notebook_id: str, source_id: str, body: EnabledBody, store: NotebookStore = Depends(get_store)
) -> dict:
    conn = store.open(notebook_id)
    try:
        service.set_enabled(conn, source_id, body.enabled)
        return service.get_source(conn, source_id)
    finally:
        conn.close()


@router.post("/notebooks/{notebook_id}/sources/{source_id}/retry", status_code=202)
def retry_source(
    notebook_id: str,
    source_id: str,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
) -> dict:
    conn = store.open(notebook_id)
    try:
        if service.get_source(conn, source_id)["state"] != "failed":
            raise AppError(409, "not_failed", "Only a failed source can be retried.")
        runner.submit_ingest(notebook_id, source_id)
        return service.get_source(conn, source_id)
    finally:
        conn.close()


@router.delete("/notebooks/{notebook_id}/sources/{source_id}", status_code=204)
def delete_source(
    notebook_id: str,
    source_id: str,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
) -> Response:
    conn = store.open(notebook_id)
    try:
        service.get_source(conn, source_id)
        runner.cancel_source(source_id)
        service.delete_source(store, notebook_id, conn, source_id)
        store.touch(notebook_id)
    finally:
        conn.close()
    return Response(status_code=204)


@router.post("/notebooks/{notebook_id}/sources/urls", status_code=202)
async def import_urls(
    notebook_id: str,
    body: UrlImport,
    request: Request,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
    settings: dict = Depends(get_settings),
    services=Depends(get_services),
) -> list[dict]:
    """Import web pages and YouTube videos (FR-2.9, FR-2.10). Every address is checked before
    anything is created (SR-4); a YouTube address becomes a video source."""
    if not settings["allow_web_import"]:
        raise AppError(403, "network_disabled", "Importing from the web is turned off in Settings.")
    urls = list(dict.fromkeys(u.strip() for u in body.urls if u.strip()))
    if not urls:
        raise AppError(400, "no_urls", "Enter at least one web address.")
    languages = choose_language_order(request.headers.get("accept-language"))
    conn = store.open(notebook_id)
    try:
        _check_capacity(conn, settings, len(urls))
        items: list[dict] = []
        for url in urls:
            try:
                if is_youtube_url(url):
                    video_id = parse_video_id(url)
                    items.append(
                        dict(
                            source_type="youtube",
                            name=f"YouTube video {video_id}",
                            url=f"https://www.youtube.com/watch?v={video_id}",
                            meta={"video_id": video_id, "languages": languages},
                        )
                    )
                else:
                    await services.check_url(url)
                    items.append(dict(source_type="web", name=url, url=url, meta=None))
            except (safe_fetch.UnsafeURL, safe_fetch.FetchError) as e:
                raise AppError(400, "unsafe_url", str(e)) from e
        created = []
        for item in items:
            source_id = new_id()
            store.source_dir(notebook_id, source_id).mkdir(parents=True)
            created.append(dict(source_id=source_id, original_name=None, size_bytes=0, **item))
        return _create_and_queue(store, runner, notebook_id, conn, created)
    finally:
        conn.close()


@router.post("/notebooks/{notebook_id}/sources/{source_id}/refresh", status_code=202)
def refresh_source(
    notebook_id: str,
    source_id: str,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
    settings: dict = Depends(get_settings),
) -> dict:
    """Re-fetch a web source. The previous capture is kept as an earlier version (FR-2.9)."""
    if not settings["allow_web_import"]:
        raise AppError(403, "network_disabled", "Importing from the web is turned off in Settings.")
    conn = store.open(notebook_id)
    try:
        source = service.get_source(conn, source_id)
        if source["type"] not in ("web", "youtube"):
            raise AppError(400, "not_refreshable", "Only web pages and videos can be refreshed.")
        if source["state"] not in ("ready", "failed"):
            raise AppError(409, "busy", "Wait for this source to finish processing first.")
        if source["state"] == "ready":
            service.archive_current_version(store, notebook_id, conn, source_id)
        (store.source_dir(notebook_id, source_id) / "original.html").unlink(missing_ok=True)
        runner.submit_ingest(notebook_id, source_id)
        return service.get_source(conn, source_id)
    finally:
        conn.close()
