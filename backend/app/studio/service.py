"""Artifact records (FR-5.1 to FR-5.4, FR-5.12, FR-5.13)."""

from __future__ import annotations

import json
import shutil
import sqlite3

from app.core.errors import AppError
from app.core.ids import new_id, now_iso
from app.core.notebooks import NotebookStore, NotFound
from app.studio.generate import JSON_KINDS, KINDS, MAX_FOCUS_CHARS, artifact_dir

ACTIVE_STATES = ("queued", "running")


def _stale(conn: sqlite3.Connection, source_ids: list[str]) -> bool:
    """True if a source the artifact was built from was deleted or disabled (FR-5.13)."""
    if not source_ids:
        return False
    marks = ",".join("?" * len(source_ids))
    enabled = conn.execute(
        f"SELECT COUNT(*) AS n FROM sources WHERE enabled = 1 AND id IN ({marks})", source_ids
    ).fetchone()["n"]
    return enabled < len(source_ids)


def _to_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    source_ids = json.loads(row["source_ids"])
    return {
        "id": row["id"],
        "kind": row["kind"],
        "title": row["title"],
        "state": row["state"],
        "stage": row["stage"],
        "progress": row["progress"],
        "error": row["error"],
        "focus": row["focus"],
        "has_content": bool(row["has_content"]),
        "stale": bool(row["has_content"]) and _stale(conn, source_ids),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_artifacts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM artifacts ORDER BY created_at DESC, id").fetchall()
    return [_to_dict(conn, r) for r in rows]


def get_row(conn: sqlite3.Connection, artifact_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
    if row is None:
        raise NotFound(artifact_id)
    return row


def get_artifact(
    store: NotebookStore, notebook_id: str, conn: sqlite3.Connection, artifact_id: str
) -> dict:
    """The artifact with its Markdown and citations (chips for removed chunks are flagged)."""
    row = get_row(conn, artifact_id)
    data = _to_dict(conn, row)
    json_kind = row["kind"] in JSON_KINDS
    data["format"] = "json" if json_kind else "markdown"
    data["content"] = ""  # Markdown artifacts
    data["data"] = None  # structured artifacts
    data["citations"] = []
    if row["has_content"]:
        filename = "content.json" if json_kind else "content.md"
        path = artifact_dir(store, notebook_id, artifact_id) / filename
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if json_kind:
            data["data"] = json.loads(text) if text else None
        else:
            data["content"] = text
        citations = json.loads(row["citations"])
        ids = [c["chunk_id"] for c in citations]
        existing: set[str] = set()
        if ids:
            marks = ",".join("?" * len(ids))
            existing = {
                r["id"] for r in conn.execute(f"SELECT id FROM chunks WHERE id IN ({marks})", ids)
            }
        for c in citations:
            c["removed"] = c["chunk_id"] not in existing
        data["citations"] = citations
    return data


def validate_focus(focus: str | None) -> str:
    focus = (focus or "").strip()
    if len(focus) > MAX_FOCUS_CHARS:
        raise AppError(
            422, "focus_too_long", f"The focus can be at most {MAX_FOCUS_CHARS} characters."
        )
    return focus


def create_artifact(conn: sqlite3.Connection, kind: str, focus: str) -> str:
    if kind not in KINDS:
        raise AppError(422, "unknown_kind", f"Unknown artifact type '{kind}'.")
    artifact_id, now = new_id(), now_iso()
    with conn:
        conn.execute(
            "INSERT INTO artifacts (id, kind, title, state, focus, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (artifact_id, kind, KINDS[kind], "queued", focus, now, now),
        )
    return artifact_id


def delete_artifact(
    store: NotebookStore, notebook_id: str, conn: sqlite3.Connection, artifact_id: str
) -> None:
    get_row(conn, artifact_id)
    with conn:
        conn.execute("DELETE FROM jobs WHERE target_id = ?", (artifact_id,))
        conn.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
    shutil.rmtree(artifact_dir(store, notebook_id, artifact_id), ignore_errors=True)
