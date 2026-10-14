"""Vector storage: sqlite-vec when it loads, plain float32 BLOB table otherwise (spec §3).

The fallback keeps the data; brute-force search with NumPy is added with retrieval (M2).
"""

from __future__ import annotations

import logging
import sqlite3
from array import array

log = logging.getLogger(__name__)

_VEC_TABLE = "chunk_vectors"
_FALLBACK_TABLE = "chunk_vectors_fallback"
_warned = False


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
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.native = try_load(conn)

    @property
    def table(self) -> str:
        return _VEC_TABLE if self.native else _FALLBACK_TABLE

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
            self.conn.execute(
                f"CREATE VIRTUAL TABLE {_VEC_TABLE} USING vec0("
                f"chunk_id text primary key, embedding float[{dim}])"
            )
        else:
            self.conn.execute(
                f"CREATE TABLE {_FALLBACK_TABLE} "
                "(chunk_id TEXT PRIMARY KEY, embedding BLOB NOT NULL)"
            )
        self.conn.execute(
            "INSERT OR REPLACE INTO notebook_meta (key, value) VALUES ('embedding_dim', ?)",
            (str(dim),),
        )

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
