"""Source records: create, list, enable/disable, delete (FR-2.4, FR-2.7, DR-5)."""

from __future__ import annotations

import json
import shutil
import sqlite3

from app.core.ids import new_id, now_iso
from app.core.notebooks import NotebookStore, NotFound
from app.retrieval.vectors import VectorIndex

_SELECT = (
    "SELECT sources.*, (SELECT COUNT(*) FROM source_versions v WHERE v.source_id = sources.id) "
    "AS version_count FROM sources"
)


def _serialize(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["enabled"] = bool(d["enabled"])
    d["guide"] = json.loads(d["guide"]) if d["guide"] else None
    meta = json.loads(d["meta"]) if d.get("meta") else {}
    d["meta"] = {k: v for k, v in meta.items() if k != "languages"}  # internal
    return d


def list_sources(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(f"{_SELECT} ORDER BY created_at, id").fetchall()
    return [_serialize(r) for r in rows]


def get_source(conn: sqlite3.Connection, source_id: str) -> dict:
    row = conn.execute(f"{_SELECT} WHERE id = ?", (source_id,)).fetchone()
    if row is None:
        raise NotFound(source_id)
    return _serialize(row)


def source_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM sources").fetchone()["n"]


def create_source(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    name: str,
    source_type: str,
    original_name: str | None,
    size_bytes: int,
    url: str | None = None,
    meta: dict | None = None,
) -> None:
    """Insert a queued, enabled source (new sources are enabled by default, FR-2.7)."""
    now = now_iso()
    with conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, original_name, size_bytes, state, enabled, "
            "url, meta, created_at, updated_at) VALUES (?,?,?,?,?, 'queued', 1, ?, ?, ?, ?)",
            (
                source_id,
                name,
                source_type,
                original_name,
                size_bytes,
                url,
                json.dumps(meta) if meta else None,
                now,
                now,
            ),
        )


def set_enabled(conn: sqlite3.Connection, source_id: str, enabled: bool) -> None:
    get_source(conn, source_id)
    with conn:
        conn.execute(
            "UPDATE sources SET enabled = ?, updated_at = ? WHERE id = ?",
            (int(enabled), now_iso(), source_id),
        )


def set_all_enabled(conn: sqlite3.Connection, enabled: bool) -> None:
    with conn:
        conn.execute("UPDATE sources SET enabled = ?, updated_at = ?", (int(enabled), now_iso()))


def delete_source(
    store: NotebookStore, notebook_id: str, conn: sqlite3.Connection, source_id: str
) -> None:
    """Remove the source's chunks, FTS rows, vectors and files (DR-5)."""
    get_source(conn, source_id)
    index = VectorIndex(conn)
    with conn:
        chunk_ids = [
            r["id"] for r in conn.execute("SELECT id FROM chunks WHERE source_id = ?", (source_id,))
        ]
        index.delete(chunk_ids)
        conn.execute("DELETE FROM chunks_fts WHERE source_id = ?", (source_id,))
        conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
        conn.execute("DELETE FROM jobs WHERE target_id = ?", (source_id,))
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    shutil.rmtree(store.source_dir(notebook_id, source_id), ignore_errors=True)


def archive_current_version(
    store: NotebookStore, notebook_id: str, conn: sqlite3.Connection, source_id: str
) -> int:
    """Keep the current capture of a web source before it is replaced (FR-2.9). Returns the
    archived version number."""
    row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    last = conn.execute(
        "SELECT COALESCE(MAX(version), 0) AS v FROM source_versions WHERE source_id = ?",
        (source_id,),
    ).fetchone()["v"]
    version = last + 1
    folder = store.source_dir(notebook_id, source_id)
    target = folder / "versions" / str(version)
    target.mkdir(parents=True, exist_ok=True)
    for name in ("extracted.json", "original.html"):
        if (folder / name).exists():
            shutil.copy2(folder / name, target / name)
    with conn:
        conn.execute(
            "INSERT INTO source_versions "
            "(id, source_id, version, fetched_at, char_count, created_at) VALUES (?,?,?,?,?,?)",
            (new_id(), source_id, version, row["fetched_at"], row["char_count"], now_iso()),
        )
    return version
