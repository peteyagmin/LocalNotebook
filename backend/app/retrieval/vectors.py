"""Vector storage: sqlite-vec when it loads, plain float32 BLOB table otherwise (spec §3).

The fallback keeps the data; brute-force search with NumPy is added with retrieval (M2).
"""

from __future__ import annotations

import logging
import sqlite3
from array import array

import numpy as np

log = logging.getLogger(__name__)

_TABLES = {
    # scope: (sqlite-vec table, fallback table)
    "sources": ("chunk_vectors", "chunk_vectors_fallback"),
    "notes": ("note_vectors", "note_vectors_fallback"),
}
_warned = False
_VEC0_MAX_K = 4096
ENABLED_READY = "s.enabled = 1 AND s.state = 'ready'"


def try_load(conn: sqlite3.Connection) -> bool:
    """Load the sqlite-vec extension into this connection. False if unavailable."""
    global _warned
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        try:
            sqlite_vec.load(conn)
        finally:
            conn.enable_load_extension(False)
        return True
    except (ImportError, AttributeError, sqlite3.Error, OSError) as e:
        if not _warned:
            log.warning("sqlite-vec unavailable (%s); using the NumPy fallback.", e)
            _warned = True
        return False


def _blob(vector: list[float]) -> bytes:
    return array("f", vector).tobytes()


class VectorIndex:
    """Vectors for one scope: "sources" (chunks of enabled sources) or "notes"."""

    def __init__(self, conn: sqlite3.Connection, scope: str = "sources"):
        self.conn = conn
        self.scope = scope
        self.native = try_load(conn)

    @property
    def table(self) -> str:
        native, fallback = _TABLES[self.scope]
        return native if self.native else fallback

    def _meta_dim(self) -> int | None:
        row = self.conn.execute(
            "SELECT value FROM notebook_meta WHERE key = 'embedding_dim'"
        ).fetchone()
        return int(row["value"]) if row else None

    def exists(self) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name = ?", (self.table,)
            ).fetchone()
            is not None
        )

    def ensure(self, dim: int) -> None:
        """Create the table on first use; refuse a different dimension afterwards."""
        existing = self._meta_dim()
        if existing is not None and existing != dim:
            raise ValueError(
                f"The index was built with {existing}-dimension vectors but the embedding model "
                f"returned {dim}. Rebuild the notebook index."
            )
        if self.exists():
            return
        if self.native:
            self._create_native(dim)
        else:
            self.conn.execute(
                f"CREATE TABLE {self.table} (chunk_id TEXT PRIMARY KEY, embedding BLOB NOT NULL)"
            )
        if existing is None:
            self._set_meta("embedding_dim", str(dim))
        if self.native and self.scope == "sources":
            self._set_meta("vector_metric", "cosine")

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO notebook_meta (key, value) VALUES (?, ?)", (key, value)
        )

    def _create_native(self, dim: int) -> None:
        self.conn.execute(
            f"CREATE VIRTUAL TABLE {self.table} USING vec0("
            f"chunk_id text primary key, embedding float[{dim}] distance_metric=cosine)"
        )

    def _upgrade_to_cosine(self) -> None:
        """Tables created by M1 used L2 distance; rebuild once with cosine, keeping the data."""
        meta = self.conn.execute(
            "SELECT value FROM notebook_meta WHERE key = 'vector_metric'"
        ).fetchone()
        dim = self._meta_dim()
        if self.scope != "sources" or not (self.native and self.exists() and dim) or meta:
            return
        with self.conn:
            rows = self.conn.execute(f"SELECT chunk_id, embedding FROM {self.table}").fetchall()
            self.conn.execute(f"DROP TABLE {self.table}")
            self._create_native(dim)
            for r in rows:
                self.conn.execute(
                    f"INSERT INTO {self.table} (chunk_id, embedding) VALUES (?, ?)",
                    (r["chunk_id"], r["embedding"]),
                )
            self._set_meta("vector_metric", "cosine")

    def add(self, chunk_ids: list[str], vectors: list[list[float]]) -> None:
        for cid, vec in zip(chunk_ids, vectors, strict=True):
            self.conn.execute(
                f"INSERT INTO {self.table} (chunk_id, embedding) VALUES (?, ?)", (cid, _blob(vec))
            )

    def delete(self, chunk_ids: list[str]) -> None:
        if not self.exists():
            return
        for cid in chunk_ids:
            self.conn.execute(f"DELETE FROM {self.table} WHERE chunk_id = ?", (cid,))

    def count(self) -> int:
        if not self.exists():
            return 0
        return self.conn.execute(f"SELECT COUNT(*) AS n FROM {self.table}").fetchone()["n"]

    # --- search ---------------------------------------------------------------------------

    def search(self, query: list[float], limit: int) -> list[tuple[str, float]]:
        """Nearest chunks by cosine similarity among enabled, ready sources: [(chunk_id, score)]
        best first. Uses sqlite-vec when possible, otherwise brute force with NumPy."""
        if not self.exists():
            return []
        self._upgrade_to_cosine()
        if self.native:
            excluded = 0
            if self.scope == "sources":
                excluded = self.conn.execute(
                    "SELECT COUNT(*) AS n FROM chunks c JOIN sources s ON s.id = c.source_id "
                    f"WHERE NOT ({ENABLED_READY})"
                ).fetchone()["n"]
            k = limit + excluded
            if k <= _VEC0_MAX_K:
                return self._search_native(query, limit, k)
        return self._search_brute_force(query, limit)

    def _search_native(self, query: list[float], limit: int, k: int) -> list[tuple[str, float]]:
        rows = self.conn.execute(
            f"SELECT chunk_id, distance FROM {self.table} "
            "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (_blob(query), k),
        ).fetchall()
        if not rows:
            return []
        if self.scope == "sources":
            marks = ",".join("?" * len(rows))
            allowed = {
                r["id"]
                for r in self.conn.execute(
                    "SELECT c.id FROM chunks c JOIN sources s ON s.id = c.source_id "
                    f"WHERE {ENABLED_READY} AND c.id IN ({marks})",
                    [r["chunk_id"] for r in rows],
                )
            }
        else:
            allowed = {r["chunk_id"] for r in rows}
        hits = [(r["chunk_id"], 1.0 - r["distance"]) for r in rows if r["chunk_id"] in allowed]
        return hits[:limit]

    def _search_brute_force(self, query: list[float], limit: int) -> list[tuple[str, float]]:
        if self.scope == "sources":
            rows = self.conn.execute(
                f"SELECT v.chunk_id AS chunk_id, v.embedding AS embedding FROM {self.table} v "
                "JOIN chunks c ON c.id = v.chunk_id JOIN sources s ON s.id = c.source_id "
                f"WHERE {ENABLED_READY}"
            ).fetchall()
        else:
            rows = self.conn.execute(f"SELECT chunk_id, embedding FROM {self.table}").fetchall()
        if not rows:
            return []
        matrix = np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
        q = np.asarray(query, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(q) or 1.0)
        scores = (matrix @ q) / np.where(norms == 0, 1.0, norms)
        order = np.argsort(-scores)[:limit]
        return [(rows[i]["chunk_id"], float(scores[i])) for i in order]
