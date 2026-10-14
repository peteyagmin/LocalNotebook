"""Ingestion pipeline, one run per source (FR-2.3):
extract -> normalize -> chunk -> embed -> write FTS5 + vector index -> source guide -> ready."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, field_validator

from app.core.ids import new_id, now_iso
from app.core.notebooks import NotebookStore, NotFound
from app.ingest.chunker import Chunk, chunk_text
from app.ingest.extract import build_extracted, read_extracted, write_extracted
from app.ingest.parsers import ParseError
from app.ingest.sandbox import run_parse
from app.llm.base import LLMClient, LLMError
from app.llm.prompts import render_prompt
from app.llm.structured import StructuredOutputError, generate_json
from app.retrieval.vectors import VectorIndex

log = logging.getLogger(__name__)

EMBED_BATCH = 32
GUIDE_INPUT_CHARS = 12_000


class Cancelled(Exception):
    pass


class IngestError(Exception):
    """A user-readable reason the source could not be processed."""


class SourceGuide(BaseModel):
    summary: str
    topics: list[str]

    @field_validator("summary")
    @classmethod
    def _summary(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("summary must not be empty")
        return v.strip()

    @field_validator("topics")
    @classmethod
    def _topics(cls, v: list[str]) -> list[str]:
        topics = [t.strip() for t in v if t.strip()]
        if not topics:
            raise ValueError("topics must not be empty")
        return topics[:8]


def original_path(store: NotebookStore, notebook_id: str, source: dict) -> Path:
    suffix = (
        source["original_name"].rsplit(".", 1)[-1].lower() if source["original_name"] else "txt"
    )
    return store.source_dir(notebook_id, source["id"]) / f"original.{suffix}"


def extracted_path(store: NotebookStore, notebook_id: str, source_id: str) -> Path:
    return store.source_dir(notebook_id, source_id) / "extracted.json"


# --- indexing (also the DR-3 rebuild path) -------------------------------------------------


def build_chunks(extracted: dict) -> list[Chunk]:
    return chunk_text(extracted["text"], extracted["segments"])


def write_index(conn, source_id: str, chunks: list[Chunk], vectors: list[list[float]]) -> list[str]:
    """Replace a source's chunks, FTS rows and vectors in one transaction (DR-6)."""
    index = VectorIndex(conn)
    # Take the write lock first: two sources finishing together must not both try to create the
    # vector table.
    conn.execute("BEGIN IMMEDIATE")
    with conn:
        old = [
            r["id"] for r in conn.execute("SELECT id FROM chunks WHERE source_id = ?", (source_id,))
        ]
        index.delete(old)
        conn.execute("DELETE FROM chunks_fts WHERE source_id = ?", (source_id,))
        conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
        ids = [new_id() for _ in chunks]
        for cid, ch in zip(ids, chunks, strict=True):
            conn.execute(
                "INSERT INTO chunks (id, source_id, ordinal, text, char_start, char_end, location) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    cid,
                    source_id,
                    ch.ordinal,
                    ch.text,
                    ch.char_start,
                    ch.char_end,
                    json.dumps(ch.location()),
                ),
            )
            conn.execute(
                "INSERT INTO chunks_fts (chunk_id, source_id, text) VALUES (?,?,?)",
                (cid, source_id, ch.text),
            )
        if vectors:
            index.ensure(len(vectors[0]))
            index.add(ids, vectors)
    return ids


async def embed_chunks(
    llm: LLMClient,
    model: str,
    chunks: list[Chunk],
    on_progress: Callable[[float], None] | None = None,
    check_cancelled: Callable[[], None] | None = None,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in range(0, len(chunks), EMBED_BATCH):
        if check_cancelled:
            check_cancelled()
        vectors.extend(await llm.embed(model, [c.text for c in chunks[i : i + EMBED_BATCH]]))
        if on_progress:
            on_progress(min(1.0, (i + EMBED_BATCH) / len(chunks)))
    return vectors


async def reindex_source(
    store: NotebookStore, notebook_id: str, source_id: str, llm: LLMClient, embedding_model: str
) -> int:
    """Rebuild one source's index purely from extracted.json (DR-3)."""
    extracted = read_extracted(extracted_path(store, notebook_id, source_id))
    chunks = build_chunks(extracted)
    vectors = await embed_chunks(llm, embedding_model, chunks)

    def _write() -> None:
        conn = store.open(notebook_id)
        try:
            write_index(conn, source_id, chunks, vectors)
        finally:
            conn.close()

    await asyncio.to_thread(_write)
    return len(chunks)


# --- the full pipeline ---------------------------------------------------------------------


def _update_source(store: NotebookStore, notebook_id: str, source_id: str, **fields) -> None:
    fields["updated_at"] = now_iso()
    assignments = ", ".join(f"{k} = ?" for k in fields)
    conn = store.open(notebook_id)
    try:
        with conn:
            conn.execute(
                f"UPDATE sources SET {assignments} WHERE id = ?", (*fields.values(), source_id)
            )
    finally:
        conn.close()


async def run_ingest(
    store: NotebookStore,
    notebook_id: str,
    source_id: str,
    llm: LLMClient,
    settings: dict,
    is_cancelled: Callable[[], bool] = lambda: False,
) -> str | None:
    """Process one source. Returns None on success, else the user-readable error."""

    def check() -> None:
        if is_cancelled():
            raise Cancelled

    def stage(name: str, progress: float) -> None:
        _update_source(store, notebook_id, source_id, stage=name, progress=progress)

    try:
        conn = store.open(notebook_id)
        try:
            row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise Cancelled
        source = dict(row)
        if not settings["embedding_model"]:
            raise IngestError(
                "No embedding model is configured. Choose one in Settings, then retry."
            )
        if not settings["chat_model"]:
            raise IngestError("No chat model is configured. Choose one in Settings, then retry.")

        _update_source(store, notebook_id, source_id, state="processing", error=None)
        stage("Reading file", 0.05)
        parsed = await asyncio.to_thread(
            run_parse, original_path(store, notebook_id, source), source["type"]
        )
        check()
        extracted = build_extracted(parsed)
        write_extracted(extracted_path(store, notebook_id, source_id), extracted)
        _update_source(
            store,
            notebook_id,
            source_id,
            char_count=len(extracted["text"]),
            page_count=extracted["page_count"],
        )

        stage("Splitting into passages", 0.3)
        chunks = build_chunks(extracted)

        stage("Indexing", 0.35)
        vectors = await embed_chunks(
            llm,
            settings["embedding_model"],
            chunks,
            on_progress=lambda f: stage("Indexing", 0.35 + 0.5 * f),
            check_cancelled=check,
        )
        check()

        def _write() -> None:
            conn = store.open(notebook_id)
            try:
                write_index(conn, source_id, chunks, vectors)
            finally:
                conn.close()

        await asyncio.to_thread(_write)

        stage("Writing source guide", 0.9)
        guide = await generate_json(
            llm,
            settings["chat_model"],
            [
                {
                    "role": "user",
                    "content": render_prompt(
                        "source_guide", document=extracted["text"][:GUIDE_INPUT_CHARS]
                    ),
                }
            ],
            SourceGuide,
        )
        check()
        _update_source(
            store,
            notebook_id,
            source_id,
            state="ready",
            stage=None,
            progress=1.0,
            error=None,
            guide=guide.model_dump_json(),
        )
        return None
    except (Cancelled, NotFound):
        return "Cancelled."
    except (ParseError, LLMError, IngestError, StructuredOutputError, ValueError) as e:
        message = str(e)
    except Exception as e:
        log.exception("Ingestion failed for source %s", source_id)
        message = f"Unexpected error ({e.__class__.__name__}). See the app log for details."
    try:
        _update_source(store, notebook_id, source_id, state="failed", stage=None, error=message)
    except Exception:  # notebook or source was deleted meanwhile
        log.debug("Could not record failure for %s", source_id)
    return message
