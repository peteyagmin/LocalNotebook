from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, field_validator

from app.api.deps import get_runner, get_store
from app.core.notebooks import NotebookStore

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


@router.get("/notebooks")
def list_notebooks(store: NotebookStore = Depends(get_store)) -> list[dict]:
    return store.list()


@router.post("/notebooks", status_code=201)
def create_notebook(body: NotebookName, store: NotebookStore = Depends(get_store)) -> dict:
    return store.create(body.name)


@router.get("/notebooks/{notebook_id}")
def get_notebook(notebook_id: str, store: NotebookStore = Depends(get_store)) -> dict:
    return store.get(notebook_id)


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
