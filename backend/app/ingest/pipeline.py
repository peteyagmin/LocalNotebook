"""Ingestion pipeline, one run per source (FR-2.3):
extract -> normalize -> chunk -> embed -> write FTS5 + vector index -> source guide -> ready."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, field_validator

from app.core.ids import new_id, now_iso
from app.core.notebooks import NotebookStore, NotFound
from app.ingest import service
from app.ingest.chunker import Chunk, chunk_text
from app.ingest.extract import build_extracted, read_extracted, write_extracted
from app.ingest.parsers import Block, ParseError, ParseResult
from app.ingest.safe_fetch import FetchError, UnsafeURL
from app.ingest.sandbox import run_parse
from app.ingest.services import Services
from app.ingest.youtube import (
    NO_CAPTIONS_MESSAGE,
    VideoInfo,
    caption_blocks,
    parse_video_id,
)
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


def write_index(
    conn,
    source_id: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
    source_fields: dict | None = None,
    model: str | None = None,
) -> list[str]:
    """Replace a source's chunks, FTS rows and vectors in one transaction (DR-6). With
    `source_fields`, the source row is updated in that same transaction, so a source is never
    half old and half new."""
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
            index.ensure(len(vectors[0]), model)
            index.add(ids, vectors)
        if source_fields:
            fields = {**source_fields, "updated_at": now_iso()}
            assignments = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE sources SET {assignments} WHERE id = ?", (*fields.values(), source_id)
            )
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
            write_index(conn, source_id, chunks, vectors, model=embedding_model)
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


def _meta(source: dict) -> dict:
    return json.loads(source["meta"]) if source.get("meta") else {}


@dataclass
class Acquired:
    """What was read from the source, plus changes to apply only when everything has worked."""

    parsed: ParseResult
    fields: dict = field(default_factory=dict)  # source columns to set at commit
    staged_original: tuple[Path, Path] | None = None  # (temporary file, final file)


async def _acquire_web(store, notebook_id, source, settings, services, stage) -> Acquired:
    """Fetch the page (once; kept as original.html) and extract its main content (FR-2.9). A
    refresh fetches into a temporary file; it replaces the old capture only at commit."""
    if not settings["allow_web_import"]:
        raise IngestError("Importing from the web is turned off in Settings.")
    final = store.source_dir(notebook_id, source["id"]) / "original.html"
    meta = {k: v for k, v in _meta(source).items() if k != "refreshing"}
    fields: dict = {}
    staged = None
    path = final
    if _meta(source).get("refreshing") or not final.exists():
        stage("Fetching the page", 0.05)
        result = await services.fetch(source["url"])
        path = final.with_name("original.html.new")
        path.write_bytes(result.content)
        staged = (path, final)
        fields["fetched_at"] = now_iso()
    parsed = await asyncio.to_thread(run_parse, path, "web")
    if parsed.title:
        fields["name"] = parsed.title[:300]
        meta["title"] = parsed.title
    fields["meta"] = json.dumps(meta)
    return Acquired(parsed, fields, staged)


async def _acquire_youtube(
    store, notebook_id, source, settings, services, stage, check
) -> Acquired:
    """Captions if the video has them; otherwise local transcription, only if the user allowed
    it (FR-2.10)."""
    if not settings["allow_web_import"]:
        raise IngestError("Importing from the web is turned off in Settings.")
    video_id = parse_video_id(source["url"])
    languages = _meta(source).get("languages") or ["en"]
    stage("Reading the video's details", 0.05)
    try:
        info = await asyncio.to_thread(services.youtube.metadata, source["url"], video_id)
    except FetchError:  # details are nice to have; the transcript is what matters
        info = VideoInfo(video_id=video_id, title=f"YouTube video {video_id}", url=source["url"])
    check()
    stage("Fetching captions", 0.1)
    captions = await asyncio.to_thread(services.youtube.captions, video_id, languages)
    check()
    if captions and captions.lines:
        blocks = [
            Block(text, start_s=start, end_s=end)
            for text, start, end in caption_blocks(captions.lines)
        ]
        parsed = ParseResult(blocks)
        transcript_source = "captions"
    elif settings["transcribe_uncaptioned_videos"]:
        stage("Downloading the audio", 0.1)
        folder = store.source_dir(notebook_id, source["id"]) / "audio_tmp"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            audio = await asyncio.to_thread(services.youtube.download_audio, source["url"], folder)
            check()
            stage("Transcribing", 0.15)
            parsed = await asyncio.to_thread(
                run_parse,
                audio,
                "audio",
                None,
                None,
                {"stt_model": settings["stt_model"], "models_dir": str(services.models_dir)},
            )
        finally:
            shutil.rmtree(folder, ignore_errors=True)  # the downloaded audio is never kept
        transcript_source = "transcription"
    else:
        raise IngestError(NO_CAPTIONS_MESSAGE)
    meta = {k: v for k, v in _meta(source).items() if k != "refreshing"}
    meta.update(
        video_id=video_id,
        title=info.title,
        channel=info.channel,
        description=info.description,
        duration=info.duration,
        transcript=transcript_source,
    )
    return Acquired(
        parsed,
        {"name": info.title[:300], "fetched_at": now_iso(), "meta": json.dumps(meta)},
    )


async def run_ingest(
    store: NotebookStore,
    notebook_id: str,
    source_id: str,
    llm: LLMClient,
    settings: dict,
    is_cancelled: Callable[[], bool] = lambda: False,
    services: Services | None = None,
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
        services = services or Services(models_dir=store.data_root / "models")

        if source["type"] == "web":
            acquired = await _acquire_web(store, notebook_id, source, settings, services, stage)
        elif source["type"] == "youtube":
            acquired = await _acquire_youtube(
                store, notebook_id, source, settings, services, stage, check
            )
        else:
            acquired = Acquired(
                await asyncio.to_thread(
                    run_parse,
                    original_path(store, notebook_id, source),
                    source["type"],
                    None,
                    2 * 1024**3,
                    {"stt_model": settings["stt_model"], "models_dir": str(services.models_dir)},
                )
            )
        check()
        extracted = build_extracted(acquired.parsed)

        # Nothing below changes the source until the commit at the end, so a failure while
        # refreshing leaves the previous capture exactly as it was.
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

        final_extracted = extracted_path(store, notebook_id, source_id)
        staged_extracted = final_extracted.with_name("extracted.json.new")
        write_extracted(staged_extracted, extracted)
        fields = {
            **acquired.fields,
            "char_count": len(extracted["text"]),
            "page_count": extracted["page_count"],
            "state": "ready",
            "stage": None,
            "progress": 1.0,
            "error": None,
            "guide": guide.model_dump_json(),
        }
        if "meta" not in fields:
            fields["meta"] = json.dumps(
                {k: v for k, v in _meta(source).items() if k != "refreshing"}
            )

        def _commit() -> None:
            conn = store.open(notebook_id)
            try:
                write_index(conn, source_id, chunks, vectors, fields, settings["embedding_model"])
            finally:
                conn.close()

        await asyncio.to_thread(_commit)
        os.replace(staged_extracted, final_extracted)
        if acquired.staged_original:
            os.replace(*acquired.staged_original)
        return None
    except (Cancelled, NotFound):
        return "Cancelled."
    except (
        ParseError,
        LLMError,
        IngestError,
        StructuredOutputError,
        FetchError,
        UnsafeURL,
        ValueError,
    ) as e:
        message = str(e)
    except Exception as e:
        log.exception("Ingestion failed for source %s", source_id)
        message = f"Unexpected error ({e.__class__.__name__}). See the app log for details."
    try:
        conn = store.open(notebook_id)
        try:
            service.settle_failure(store, notebook_id, conn, source_id, message)
        finally:
            conn.close()
    except Exception:  # notebook or source was deleted meanwhile
        log.debug("Could not record failure for %s", source_id)
    return message
