"""Notes: user-written or saved Markdown with citation snapshots (FR-4.1 to FR-4.3, FR-3.6).

A note's `[n]` markers refer to its own `citations` list, exactly like a chat message. Notes are
indexed (chunks + FTS5 immediately, vectors in the background) so search can be hybrid (FR-7.1).
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3

from app.chat.citations import CitationFilter, strip_citations
from app.core.ids import new_id, now_iso
from app.core.notebooks import NotebookStore, NotFound
from app.ingest.chunker import chunk_text
from app.llm.base import LLMClient
from app.retrieval.vectors import VectorIndex

DEFAULT_TITLE = "Untitled note"
_MARKER = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def _labels(marker: str) -> list[int]:
    return [int(x) for x in re.split(r"\s*,\s*", marker.strip())]


def used_labels(content: str) -> set[int]:
    return {n for m in _MARKER.finditer(content) for n in _labels(m.group(1))}


def prune_citations(content: str, citations: list[dict]) -> list[dict]:
    """Keep only citations whose label still appears in the text."""
    used = used_labels(content)
    return [c for c in citations if c["label"] in used]


def remap_markers(content: str, mapping: dict[int, int]) -> str:
    """Rewrite [n] markers through `mapping`; labels without a mapping are dropped."""

    def sub(match: re.Match) -> str:
        new = []
        for n in _labels(match.group(1)):
            if n in mapping and mapping[n] not in new:
                new.append(mapping[n])
        return "".join(f"[{n}]" for n in new)

    return _MARKER.sub(sub, content)


def merge_notes(notes: list[dict]) -> tuple[str, list[dict]]:
    """Concatenate notes under their titles, renumbering citations so they stay unique. The same
    chunk cited by several notes gets one label."""
    label_of: dict[str, int] = {}
    merged: list[dict] = []
    parts: list[str] = []
    for note in notes:
        mapping: dict[int, int] = {}
        for c in note["citations"]:
            if c["chunk_id"] not in label_of:
                label_of[c["chunk_id"]] = len(label_of) + 1
                merged.append({**c, "label": label_of[c["chunk_id"]]})
            mapping[c["label"]] = label_of[c["chunk_id"]]
        parts.append(f"## {note['title']}\n\n{remap_markers(note['content'], mapping)}".rstrip())
    return "\n\n".join(parts), merged


def filter_to_valid(text: str, citations: list[dict]) -> tuple[str, list[dict]]:
    """Drop markers that match no supplied citation (same rule as chat, FR-3.2)."""
    filt = CitationFilter({c["label"] for c in citations})
    out = filt.feed(text) + filt.flush()
    return out, [c for c in citations if c["label"] in filt.used]


# --- storage -------------------------------------------------------------------------------


def _existing_chunks(conn: sqlite3.Connection, citations: list[dict]) -> set[str]:
    ids = list({c["chunk_id"] for c in citations})
    if not ids:
        return set()
    marks = ",".join("?" * len(ids))
    return {r["id"] for r in conn.execute(f"SELECT id FROM chunks WHERE id IN ({marks})", ids)}


def _to_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    citations = json.loads(row["citations"])
    existing = _existing_chunks(conn, citations)
    for c in citations:
        c["removed"] = c["chunk_id"] not in existing
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "citations": citations,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_note(conn: sqlite3.Connection, note_id: str) -> dict:
    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if row is None:
        raise NotFound(note_id)
    return _to_dict(conn, row)


def list_notes(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM notes ORDER BY updated_at DESC, id").fetchall()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "preview": " ".join(strip_citations(r["content"]).split())[:140],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def _index_text(conn: sqlite3.Connection, note_id: str, title: str, content: str) -> None:
    """Replace the note's chunks and FTS rows (caller holds the transaction). Old vectors go too;
    new ones are added by `embed_note`."""
    index = VectorIndex(conn, "notes")
    old = [
        r["id"] for r in conn.execute("SELECT id FROM note_chunks WHERE note_id = ?", (note_id,))
    ]
    index.delete(old)
    conn.execute("DELETE FROM note_chunks_fts WHERE note_id = ?", (note_id,))
    conn.execute("DELETE FROM note_chunks WHERE note_id = ?", (note_id,))
    text = f"{title}\n\n{strip_citations(content)}".strip()
    for chunk in chunk_text(text, []):
        chunk_id = new_id()
        conn.execute(
            "INSERT INTO note_chunks (id, note_id, ordinal, text) VALUES (?,?,?,?)",
            (chunk_id, note_id, chunk.ordinal, chunk.text),
        )
        conn.execute(
            "INSERT INTO note_chunks_fts (chunk_id, note_id, text) VALUES (?,?,?)",
            (chunk_id, note_id, chunk.text),
        )


def create_note(
    conn: sqlite3.Connection,
    title: str = "",
    content: str = "",
    citations: list[dict] | None = None,
) -> dict:
    note_id, now = new_id(), now_iso()
    title = title.strip() or DEFAULT_TITLE
    kept = prune_citations(content, citations or [])
    conn.execute("BEGIN IMMEDIATE")
    with conn:
        conn.execute(
            "INSERT INTO notes (id, title, content, citations, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (note_id, title, content, json.dumps(_strip_flags(kept)), now, now),
        )
        _index_text(conn, note_id, title, content)
    return get_note(conn, note_id)


def _strip_flags(citations: list[dict]) -> list[dict]:
    return [{k: v for k, v in c.items() if k != "removed"} for c in citations]


def update_note(
    conn: sqlite3.Connection, note_id: str, title: str | None, content: str | None
) -> dict:
    current = get_note(conn, note_id)
    new_title = (title.strip() if title is not None else current["title"]) or DEFAULT_TITLE
    new_content = content if content is not None else current["content"]
    kept = prune_citations(new_content, current["citations"])
    conn.execute("BEGIN IMMEDIATE")
    with conn:
        conn.execute(
            "UPDATE notes SET title=?, content=?, citations=?, updated_at=? WHERE id=?",
            (new_title, new_content, json.dumps(_strip_flags(kept)), now_iso(), note_id),
        )
        _index_text(conn, note_id, new_title, new_content)
    return get_note(conn, note_id)


def delete_note(conn: sqlite3.Connection, note_id: str) -> None:
    get_note(conn, note_id)
    index = VectorIndex(conn, "notes")
    conn.execute("BEGIN IMMEDIATE")
    with conn:
        old = [
            r["id"]
            for r in conn.execute("SELECT id FROM note_chunks WHERE note_id = ?", (note_id,))
        ]
        index.delete(old)
        conn.execute("DELETE FROM note_chunks_fts WHERE note_id = ?", (note_id,))
        conn.execute("DELETE FROM note_chunks WHERE note_id = ?", (note_id,))
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))


async def embed_note(
    store: NotebookStore, notebook_id: str, note_id: str, llm: LLMClient, model: str
) -> None:
    """Add vectors for the note's current chunks. Skips chunks that changed or vanished while
    the embeddings were being computed."""

    def _chunks() -> list[tuple[str, str]]:
        conn = store.open(notebook_id)
        try:
            return [
                (r["id"], r["text"])
                for r in conn.execute(
                    "SELECT id, text FROM note_chunks WHERE note_id = ? ORDER BY ordinal",
                    (note_id,),
                )
            ]
        finally:
            conn.close()

    chunks = await asyncio.to_thread(_chunks)
    if not chunks:
        return
    vectors = await llm.embed(model, [text for _, text in chunks])

    def _write() -> None:
        conn = store.open(notebook_id)
        try:
            index = VectorIndex(conn, "notes")
            conn.execute("BEGIN IMMEDIATE")
            with conn:
                still = {
                    r["id"]
                    for r in conn.execute(
                        "SELECT id FROM note_chunks WHERE note_id = ?", (note_id,)
                    )
                }
                pairs = [
                    (cid, v) for (cid, _), v in zip(chunks, vectors, strict=True) if cid in still
                ]
                if pairs:
                    index.ensure(len(pairs[0][1]), model)
                    index.delete([cid for cid, _ in pairs])
                    index.add([cid for cid, _ in pairs], [v for _, v in pairs])
        finally:
            conn.close()

    await asyncio.to_thread(_write)
