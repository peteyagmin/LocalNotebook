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
