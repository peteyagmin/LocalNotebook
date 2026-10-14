"""Rebuild a notebook's search index from its extracted text (FR-8.5, DR-3)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from app.core.notebooks import NotebookStore
from app.ingest.pipeline import reindex_source
from app.llm.base import LLMClient, LLMError
from app.notes.service import embed_note
from app.retrieval import vectors

log = logging.getLogger(__name__)


async def rebuild_index(
    store: NotebookStore,
    notebook_id: str,
    llm: LLMClient,
    embedding_model: str,
    is_cancelled: Callable[[], bool] = lambda: False,
) -> str | None:
    """Re-chunk and re-embed every ready source and every note with the current embedding model.
    Returns an error message, or None. A failure leaves the index marked out of date."""

    def _prepare() -> tuple[list[str], list[str]]:
        conn = store.open(notebook_id)
        try:
            source_ids = [
                r["id"] for r in conn.execute("SELECT id FROM sources WHERE state = 'ready'")
            ]
            note_ids = [r["id"] for r in conn.execute("SELECT id FROM notes")]
            vectors.reset_vectors(conn)
            return source_ids, note_ids
        finally:
            conn.close()

    source_ids, note_ids = await asyncio.to_thread(_prepare)
    try:
        for source_id in source_ids:
            if is_cancelled():
                return "Cancelled."
            await reindex_source(store, notebook_id, source_id, llm, embedding_model)
        for note_id in note_ids:
            if is_cancelled():
                return "Cancelled."
            await embed_note(store, notebook_id, note_id, llm, embedding_model)
    except (LLMError, ValueError, OSError) as e:
        log.warning("Rebuilding the index of %s failed: %s", notebook_id, e)
        return f"The index could not be rebuilt: {e}"

    def _finish() -> None:
        conn = store.open(notebook_id)
        try:
            with conn:
                vectors.set_index_model(conn, embedding_model)
        finally:
            conn.close()

    await asyncio.to_thread(_finish)
    return None
