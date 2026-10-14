"""Export and import of a notebook as one `.lnb` file (FR-1.3): a ZIP of the notebook folder
(`notebook.db`, `sources/`, `artifacts/`) plus `manifest.json`."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from app.core import db
from app.core.config import MIGRATIONS_DIR
from app.core.errors import AppError
from app.core.ids import new_id, now_iso
from app.core.notebooks import NotebookStore
from app.retrieval.vectors import index_model

FORMAT = "lnb"
FORMAT_VERSION = 1
MAX_UNPACKED_BYTES = 50 * 1024**3  # refuse archives that claim to unpack to more than this
MAX_RATIO = 1000  # ... or that compress more than this (zip bombs)
_STORED = {".mp3", ".zip", ".epub", ".docx", ".png", ".jpg", ".jpeg", ".pdf"}
_TOP_LEVEL = {"manifest.json", "notebook.db"}
_FOLDERS = {"sources", "artifacts"}


def latest_schema_version() -> int:
    return max(int(p.name.split("_", 1)[0]) for p in (MIGRATIONS_DIR / "notebook").glob("*.sql"))


def export_notebook(store: NotebookStore, notebook_id: str, dest: Path) -> None:
    """Write `<dest>` as a .lnb file. Safe while the notebook is in use."""
    info = store.get(notebook_id)
    folder = store.folder(notebook_id)
    with tempfile.TemporaryDirectory(dir=store.data_root) as tmp:
        snapshot = Path(tmp) / "notebook.db"
        store.snapshot_db(notebook_id, snapshot)
        conn = db.connect(snapshot)
        try:
            manifest = {
                "format": FORMAT,
                "format_version": FORMAT_VERSION,
                "exported_at": now_iso(),
                "schema_version": db.current_version(conn),
                "embedding_model": index_model(conn),
                "notebook": {
                    "id": notebook_id,
                    "name": info["name"],
                    "created_at": info["created_at"],
                    "updated_at": info["updated_at"],
                },
                "source_count": conn.execute("SELECT COUNT(*) AS n FROM sources").fetchone()["n"],
            }
            conn.execute("PRAGMA journal_mode = DELETE")
        finally:
            conn.close()
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            zf.write(snapshot, "notebook.db")
            for name in sorted(_FOLDERS):
                root = folder / name
                if not root.exists():
                    continue
                for path in sorted(root.rglob("*")):
                    if not path.is_file() or path.is_symlink():
                        continue
                    arcname = path.relative_to(folder).as_posix()
                    stored = path.suffix.lower() in _STORED
                    zf.write(
                        path,
                        arcname,
                        compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED,
                    )


def _bad(message: str) -> AppError:
    return AppError(422, "invalid_notebook_file", message)


def _check_member(info: zipfile.ZipInfo) -> PurePosixPath | None:
    """The safe relative path of a member, or None for a directory entry."""
    name = info.filename
    if "\\" in name or name.startswith("/") or ":" in name.split("/")[0]:
        raise _bad("This is not a valid notebook file (unsafe file name).")
    path = PurePosixPath(name)
    if ".." in path.parts or not path.parts:
        raise _bad("This is not a valid notebook file (unsafe file name).")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise _bad("This is not a valid notebook file (it contains a link).")
    if info.is_dir():
        return None
    top = path.parts[0]
    if not (len(path.parts) == 1 and top in _TOP_LEVEL) and top not in _FOLDERS:
        raise _bad(f"This is not a valid notebook file (unexpected entry “{name}”).")
    return path


def import_notebook(store: NotebookStore, source: Path) -> dict:
    """Add the notebook in a .lnb file. Never overwrites: if its id is already in use it is
    imported as a copy under a new id."""
    if not zipfile.is_zipfile(source):
        raise _bad("This is not a notebook file.")
    notebooks_dir = store.data_root / "notebooks"
    notebooks_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".import-", dir=notebooks_dir))
    try:
        with zipfile.ZipFile(source) as zf:
            try:
                manifest = json.loads(zf.read("manifest.json"))
                original = manifest["notebook"]
                name = str(original["name"]).strip()[:200] or "Imported notebook"
                created_at = str(original.get("created_at") or now_iso())
                original_id = str(original["id"])
            except (KeyError, ValueError, TypeError):
                raise _bad("This is not a notebook file (the manifest is missing).") from None
            if manifest.get("format") != FORMAT:
                raise _bad("This is not a notebook file.")
            if int(manifest.get("format_version", 0)) > FORMAT_VERSION:
                raise _bad("This file was made by a newer version of the app.")
            members = [(m, _check_member(m)) for m in zf.infolist()]
            files = [(m, p) for m, p in members if p is not None]
            if "notebook.db" not in {p.as_posix() for _, p in files}:
                raise _bad("This is not a valid notebook file (the database is missing).")
            total = sum(m.file_size for m, _ in files)
            packed = sum(m.compress_size for m, _ in files) or 1
            if total > MAX_UNPACKED_BYTES or total / packed > MAX_RATIO:
                raise _bad("This notebook file is too large or not valid.")
            for member, path in files:
                target = staging / Path(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)

        db_path = staging / "notebook.db"
        _check_database(db_path)
        db.migrate(db_path, MIGRATIONS_DIR / "notebook")
        for backup in staging.glob("notebook.db.bak-v*"):
            backup.unlink()
        _settle(db_path)

        conflict = original_id in store.ids() or store.folder(original_id).exists()
        notebook_id = new_id() if conflict else original_id
        if conflict:
            name = f"{name} (copy)"[:200]
        os.replace(staging, store.folder(notebook_id))
        now = now_iso()
        conn = db.connect(store.app_db_path)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO notebooks (id, name, created_at, updated_at) VALUES (?,?,?,?)",
                    (notebook_id, name, created_at, now),
                )
        except Exception:
            shutil.rmtree(store.folder(notebook_id), ignore_errors=True)
            raise
        finally:
            conn.close()
        return store.get(notebook_id)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _check_database(path: Path) -> None:
    try:
        conn = sqlite3.connect(path)
        try:
            ok = conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
            version = (
                conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
                if "schema_version" in tables
                else 0
            )
        finally:
            conn.close()
    except sqlite3.Error:
        raise _bad("This notebook file is damaged.") from None
    if not ok or not {"sources", "chunks", "schema_version"} <= tables:
        raise _bad("This notebook file is damaged.")
    if (version or 0) > latest_schema_version():
        raise _bad("This file was made by a newer version of the app. Update the app to open it.")


def _settle(path: Path) -> None:
    """Nothing is processing in a freshly imported notebook."""
    conn = db.connect(path)
    try:
        with conn:
            conn.execute(
                "UPDATE sources SET state='failed', stage=NULL, "
                "error='Interrupted: the notebook was copied during processing.' "
                "WHERE state IN ('queued','processing')"
            )
            conn.execute("DELETE FROM jobs WHERE state IN ('queued','running')")
    finally:
        conn.close()
