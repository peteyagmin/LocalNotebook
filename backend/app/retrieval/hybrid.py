"""Hybrid retrieval over enabled sources: vector + FTS5 BM25 merged by reciprocal rank fusion
(FR-3.1)."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from dataclasses import dataclass

from app.core.notebooks import NotebookStore
from app.llm.base import LLMClient
from app.retrieval.vectors import ENABLED_READY, VectorIndex

CANDIDATES = 20
RRF_K = 60
MAX_QUERY_TERMS = 32


@dataclass
class Retrieved:
    chunk_id: str
    source_id: str
    source_name: str
    text: str
    location: dict
    char_start: int
    char_end: int
    score: float


def fts_search(conn: sqlite3.Connection, query: str, limit: int = CANDIDATES) -> list[str]:
    """Chunk ids ranked by BM25. Terms are OR-ed so a natural-language question still matches."""
    terms = re.findall(r"\w+", query)[:MAX_QUERY_TERMS]
    if not terms:
        return []
    match = " OR ".join(f'"{t}"' for t in terms)
    rows = conn.execute(
        "SELECT chunks_fts.chunk_id AS id FROM chunks_fts "
        "JOIN chunks c ON c.id = chunks_fts.chunk_id JOIN sources s ON s.id = c.source_id "
        f"WHERE chunks_fts MATCH ? AND {ENABLED_READY} ORDER BY bm25(chunks_fts) LIMIT ?",
        (match, limit),
    ).fetchall()
    return [r["id"] for r in rows]


def rrf_merge(rankings: list[list[str]], top_k: int) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]


def _load(conn: sqlite3.Connection, ranked: list[tuple[str, float]]) -> list[Retrieved]:
    if not ranked:
        return []
    marks = ",".join("?" * len(ranked))
    rows = {
        r["id"]: r
        for r in conn.execute(
            "SELECT c.*, s.name AS source_name FROM chunks c JOIN sources s ON s.id = c.source_id "
            f"WHERE c.id IN ({marks})",
            [cid for cid, _ in ranked],
        )
    }
    return [
        Retrieved(
            chunk_id=cid,
            source_id=rows[cid]["source_id"],
            source_name=rows[cid]["source_name"],
            text=rows[cid]["text"],
            location=json.loads(rows[cid]["location"]),
            char_start=rows[cid]["char_start"],
            char_end=rows[cid]["char_end"],
            score=score,
        )
        for cid, score in ranked
        if cid in rows
    ]


def has_searchable_chunks(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM chunks c JOIN sources s ON s.id = c.source_id "
            f"WHERE {ENABLED_READY} LIMIT 1"
        ).fetchone()
        is not None
    )


async def retrieve(
    store: NotebookStore,
    notebook_id: str,
    llm: LLMClient,
    embedding_model: str,
    query: str,
    top_k: int,
    use_vectors: bool = True,
) -> list[Retrieved]:
    """Top `top_k` chunks from enabled, ready sources. With use_vectors=False, keyword only."""
    query_vector = None
    if use_vectors:
        query_vector = (await llm.embed(embedding_model, [query]))[0]

    def _search() -> list[Retrieved]:
        conn = store.open(notebook_id)
        try:
            rankings = [fts_search(conn, query)]
            if query_vector is not None:
                rankings.append(
                    [cid for cid, _ in VectorIndex(conn).search(query_vector, CANDIDATES)]
                )
            return _load(conn, rrf_merge(rankings, top_k))
        finally:
            conn.close()

    return await asyncio.to_thread(_search)


# --- search over sources and notes (FR-7.1) ---------------------------------------------------

EXCERPT_CHARS = 400


def fts_search_notes(conn: sqlite3.Connection, query: str, limit: int = CANDIDATES) -> list[str]:
    terms = re.findall(r"\w+", query)[:MAX_QUERY_TERMS]
    if not terms:
        return []
    match = " OR ".join(f'"{t}"' for t in terms)
    rows = conn.execute(
        "SELECT chunk_id AS id FROM note_chunks_fts WHERE note_chunks_fts MATCH ? "
        "ORDER BY bm25(note_chunks_fts) LIMIT ?",
        (match, limit),
    ).fetchall()
    return [r["id"] for r in rows]


def _note_hits(conn: sqlite3.Connection, ranked: list[tuple[str, float]]) -> list[dict]:
    """Best chunk per note, as search results."""
    if not ranked:
        return []
    marks = ",".join("?" * len(ranked))
    rows = {
        r["id"]: r
        for r in conn.execute(
            "SELECT c.id, c.note_id, c.text, n.title FROM note_chunks c "
            f"JOIN notes n ON n.id = c.note_id WHERE c.id IN ({marks})",
            [cid for cid, _ in ranked],
        )
    }
    seen: set[str] = set()
    hits = []
    for cid, score in ranked:
        row = rows.get(cid)
        if row is None or row["note_id"] in seen:
            continue
        seen.add(row["note_id"])
        hits.append(
            {
                "kind": "note",
                "chunk_id": cid,
                "note_id": row["note_id"],
                "source_id": None,
                "source_name": row["title"],
                "location": {"page": None, "heading_path": None, "char_start": 0, "char_end": 0},
                "excerpt": row["text"][:EXCERPT_CHARS],
                "char_start": 0,
                "char_end": 0,
                "score": score,
            }
        )
    return hits


async def search_all(
    store: NotebookStore,
    notebook_id: str,
    llm: LLMClient,
    embedding_model: str,
    query: str,
    limit: int,
    use_vectors: bool = True,
) -> list[dict]:
    """Hybrid search over enabled sources and notes, best first. Each side is ranked by RRF of
    keyword and vector results; the two lists are merged by score."""
    query_vector = None
    if use_vectors:
        query_vector = (await llm.embed(embedding_model, [query]))[0]

    def _search() -> list[dict]:
        conn = store.open(notebook_id)
        try:
            src_rankings = [fts_search(conn, query)]
            note_rankings = [fts_search_notes(conn, query)]
            if query_vector is not None:
                src_rankings.append(
                    [cid for cid, _ in VectorIndex(conn).search(query_vector, CANDIDATES)]
                )
                note_rankings.append(
                    [cid for cid, _ in VectorIndex(conn, "notes").search(query_vector, CANDIDATES)]
                )
            results = []
            for r in _load(conn, rrf_merge(src_rankings, limit)):
                results.append(
                    {
                        "kind": "source",
                        "chunk_id": r.chunk_id,
                        "note_id": None,
                        "source_id": r.source_id,
                        "source_name": r.source_name,
                        "location": r.location,
                        "excerpt": r.text[:EXCERPT_CHARS],
                        "char_start": r.char_start,
                        "char_end": r.char_end,
                        "score": r.score,
                    }
                )
            results += _note_hits(conn, rrf_merge(note_rankings, limit))
            results.sort(key=lambda h: -h["score"])
            return results[:limit]
        finally:
            conn.close()

    return await asyncio.to_thread(_search)
