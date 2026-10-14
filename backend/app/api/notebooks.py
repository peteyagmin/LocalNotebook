from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from starlette.background import BackgroundTask

from app.api.deps import get_runner, get_settings, get_store
from app.core import db, transfer
from app.core.errors import AppError
from app.core.notebooks import NotebookStore
from app.retrieval.vectors import is_stale
from app.studio.export import filename as export_filename

router = APIRouter()


class NotebookName(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


def _with_index_state(store: NotebookStore, row: dict, model: str) -> dict:
    """Add FR-8.5 state: `index_stale` (built with another embedding model) and `reindexing`."""
    path = store.db_path(row["id"])
    row["index_stale"], row["reindexing"] = False, False
    if path.exists():
        conn = db.connect(path)
        try:
            row["index_stale"] = is_stale(conn, model)
            row["reindexing"] = (
                conn.execute(
                    "SELECT 1 FROM jobs WHERE kind = 'reindex' AND state IN ('queued','running')"
                ).fetchone()
                is not None
            )
        finally:
            conn.close()
    return row


@router.get("/notebooks")
def list_notebooks(
    store: NotebookStore = Depends(get_store), settings: dict = Depends(get_settings)
) -> list[dict]:
    return [_with_index_state(store, r, settings["embedding_model"]) for r in store.list()]


@router.post("/notebooks/import", status_code=201)
def import_notebook(
    file: UploadFile,
    store: NotebookStore = Depends(get_store),
    settings: dict = Depends(get_settings),
) -> dict:
    """FR-1.3: add the notebook in a .lnb file; an id conflict imports it as a copy."""
    with tempfile.NamedTemporaryFile(suffix=".lnb", dir=store.data_root, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
    try:
        row = transfer.import_notebook(store, Path(tmp.name))
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    return _with_index_state(store, row, settings["embedding_model"])


@router.post("/notebooks", status_code=201)
def create_notebook(body: NotebookName, store: NotebookStore = Depends(get_store)) -> dict:
    return store.create(body.name)


@router.get("/notebooks/{notebook_id}")
def get_notebook(
    notebook_id: str,
    store: NotebookStore = Depends(get_store),
    settings: dict = Depends(get_settings),
) -> dict:
    return _with_index_state(store, store.get(notebook_id), settings["embedding_model"])


@router.get("/notebooks/{notebook_id}/export")
def export_notebook(notebook_id: str, store: NotebookStore = Depends(get_store)) -> Response:
    """FR-1.3: the whole notebook as one .lnb file."""
    info = store.get(notebook_id)
    with tempfile.NamedTemporaryFile(suffix=".lnb", dir=store.data_root, delete=False) as tmp:
        path = Path(tmp.name)
    try:
        transfer.export_notebook(store, notebook_id, path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    name = export_filename(info["name"], "lnb")
    ascii_name = name.encode("ascii", "ignore").decode() or "notebook.lnb"
    return FileResponse(
        path,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(name)}"
        },
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


@router.post("/notebooks/{notebook_id}/rebuild-index", status_code=202)
def rebuild_index(
    notebook_id: str,
    store: NotebookStore = Depends(get_store),
    runner=Depends(get_runner),
    settings: dict = Depends(get_settings),
) -> dict:
    """FR-8.5: re-read every source and note with the current embedding model."""
    store.get(notebook_id)
    if not settings["embedding_model"]:
        raise AppError(409, "not_configured", "Choose an embedding model in Settings first.")
    runner.submit_reindex(notebook_id)
    return _with_index_state(store, store.get(notebook_id), settings["embedding_model"])


@router.patch("/notebooks/{notebook_id}")
def rename_notebook(
    notebook_id: str, body: NotebookName, store: NotebookStore = Depends(get_store)
) -> dict:
    return store.rename(notebook_id, body.name)


@router.post("/notebooks/{notebook_id}/duplicate", status_code=201)
def duplicate_notebook(notebook_id: str, store: NotebookStore = Depends(get_store)) -> dict:
    return store.duplicate(notebook_id)


@router.delete("/notebooks/{notebook_id}", status_code=204)
def delete_notebook(
    notebook_id: str, store: NotebookStore = Depends(get_store), runner=Depends(get_runner)
) -> Response:
    store.get(notebook_id)
    runner.cancel_notebook(notebook_id)
    store.delete(notebook_id)
    return Response(status_code=204)
