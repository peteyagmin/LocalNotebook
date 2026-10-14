from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import get_settings, get_store
from app.core.notebooks import NotebookStore
from app.llm.base import LLMError
from app.retrieval.hybrid import search_all

router = APIRouter()

SEARCH_RESULTS = 20


@router.get("/notebooks/{notebook_id}/search")
async def search(
    notebook_id: str,
    request: Request,
    q: str = Query(min_length=1, max_length=500),
    store: NotebookStore = Depends(get_store),
    settings: dict = Depends(get_settings),
) -> list[dict]:
    """Hybrid search over enabled source text (FR-7.1). Falls back to keyword-only matching if
    the embedding model is unavailable."""
    store.get(notebook_id)
    llm = request.app.state.llm_factory(settings)
    try:
        try:
            if not settings["embedding_model"]:
                raise LLMError("no embedding model")
            results = await search_all(
                store, notebook_id, llm, settings["embedding_model"], q, SEARCH_RESULTS
            )
        except LLMError:
            results = await search_all(
                store, notebook_id, llm, "", q, SEARCH_RESULTS, use_vectors=False
            )
    finally:
        close = getattr(llm, "aclose", None)
        if close:
            await close()
    return [{k: v for k, v in r.items() if k != "score"} for r in results]
