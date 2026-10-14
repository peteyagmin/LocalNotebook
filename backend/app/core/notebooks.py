"""Notebook registry (app.db) and on-disk notebook folders (FR-1.1, FR-1.2, FR-1.4, DR-1)."""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.core import db
from app.core.config import MIGRATIONS_DIR
from app.core.ids import new_id, now_iso


class NotFound(Exception):
    pass


@dataclass
class NotebookStore:
    data_root: Path

    @property
    def app_db_path(self) -> Path:
        return self.data_root / "app.db"

    def folder(self, notebook_id: str) -> Path:
        return self.data_root / "notebooks" / notebook_id

    def db_path(self, notebook_id: str) -> Path:
        return self.folder(notebook_id) / "notebook.db"

    def source_dir(self, notebook_id: str, source_id: str) -> Path:
        return self.folder(notebook_id) / "sources" / source_id

    def _app(self) -> sqlite3.Connection:
        return db.connect(self.app_db_path)

    def open(self, notebook_id: str) -> sqlite3.Connection:
        """Connection to a notebook's database. Raises NotFound if it is not registered."""
        self.get(notebook_id)
        return db.connect(self.db_path(notebook_id))

    # --- registry -------------------------------------------------------------------------

    def _row(self, conn: sqlite3.Connection, notebook_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM notebooks WHERE id = ?", (notebook_id,)).fetchone()
        if row is None:
            raise NotFound(notebook_id)
        return row

    def get(self, notebook_id: str) -> dict:
        conn = self._app()
        try:
            return self._describe(dict(self._row(conn, notebook_id)))
        finally:
            conn.close()

    def list(self) -> list[dict]:
        conn = self._app()
        try:
            rows = conn.execute("SELECT * FROM notebooks ORDER BY updated_at DESC").fetchall()
            return [self._describe(dict(r)) for r in rows]
        finally:
            conn.close()

    def ids(self) -> list[str]:
        conn = self._app()
        try:
            return [r["id"] for r in conn.execute("SELECT id FROM notebooks")]
        finally:
            conn.close()

    def _describe(self, row: dict) -> dict:
        """Add FR-1.4 metadata: source count and storage size on disk."""
        row["source_count"] = self._source_count(row["id"])
        row["size_bytes"] = self._folder_size(self.folder(row["id"]))
        return row

    def _source_count(self, notebook_id: str) -> int:
        path = self.db_path(notebook_id)
        if not path.exists():
            return 0
        conn = db.connect(path)
        try:
            return conn.execute("SELECT COUNT(*) AS n FROM sources").fetchone()["n"]
        finally:
            conn.close()

    @staticmethod
    def _folder_size(folder: Path) -> int:
        return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())

    def create(self, name: str) -> dict:
        notebook_id = new_id()
        self.folder(notebook_id).mkdir(parents=True)
        db.migrate(self.db_path(notebook_id), MIGRATIONS_DIR / "notebook")
        now = now_iso()
        conn = self._app()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO notebooks (id, name, created_at, updated_at) VALUES (?,?,?,?)",
                    (notebook_id, name, now, now),
                )
        finally:
            conn.close()
        return self.get(notebook_id)

    def rename(self, notebook_id: str, name: str) -> dict:
        conn = self._app()
        try:
            self._row(conn, notebook_id)
            with conn:
                conn.execute(
                    "UPDATE notebooks SET name = ?, updated_at = ? WHERE id = ?",
                    (name, now_iso(), notebook_id),
                )
        finally:
            conn.close()
        return self.get(notebook_id)

    def touch(self, notebook_id: str) -> None:
        """Bump last-modified (the home screen sorts by it)."""
        conn = self._app()
        try:
            with conn:
                conn.execute(
                    "UPDATE notebooks SET updated_at = ? WHERE id = ?", (now_iso(), notebook_id)
                )
        finally:
            conn.close()

    def duplicate(self, notebook_id: str) -> dict:
        source = self.get(notebook_id)
        new_nb = new_id()
        dest = self.folder(new_nb)
        (dest).mkdir(parents=True)
        # Consistent snapshot of the database even while it is in use.
        src_conn = db.connect(self.db_path(notebook_id))
        dst_conn = db.connect(dest / "notebook.db")
        try:
            src_conn.backup(dst_conn)
            with dst_conn:
                # Work that was in flight cannot continue in the copy; offer Retry instead.
                dst_conn.execute(
                    "UPDATE sources SET state='failed', stage=NULL, "
                    "error='Interrupted: the notebook was duplicated during processing.' "
                    "WHERE state IN ('queued','processing')"
                )
                dst_conn.execute("DELETE FROM jobs WHERE state IN ('queued','running')")
        finally:
            src_conn.close()
            dst_conn.close()
        src_sources = self.folder(notebook_id) / "sources"
        if src_sources.exists():
            shutil.copytree(src_sources, dest / "sources")
        now = now_iso()
        conn = self._app()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO notebooks (id, name, created_at, updated_at) VALUES (?,?,?,?)",
                    (new_nb, f"{source['name']} (copy)", now, now),
                )
        finally:
            conn.close()
        return self.get(new_nb)

    def delete(self, notebook_id: str) -> None:
        conn = self._app()
        try:
            self._row(conn, notebook_id)
            with conn:
                conn.execute("DELETE FROM notebooks WHERE id = ?", (notebook_id,))
        finally:
            conn.close()
        shutil.rmtree(self.folder(notebook_id), ignore_errors=True)
