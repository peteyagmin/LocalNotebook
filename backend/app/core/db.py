"""SQLite helpers and numbered-SQL-file migrations (spec §3, DR-4, DR-6)."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    # A request's connection can be opened and closed on different worker threads (FastAPI runs
    # dependency setup and teardown separately); it is never used by two threads at once.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _migration_files(migrations_dir: Path) -> list[tuple[int, Path]]:
    files = []
    for p in sorted(migrations_dir.glob("*.sql")):
        files.append((int(p.name.split("_", 1)[0]), p))
    return files


def current_version(conn: sqlite3.Connection) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if not exists:
        return 0
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return row["v"] or 0


def migrate(db_path: Path, migrations_dir: Path) -> int:
    """Apply pending migrations, each in one transaction. Back up an existing db first (DR-4).

    Returns the resulting schema version.
    """
    pending_possible = _migration_files(migrations_dir)
    conn = connect(db_path)
    try:
        version = current_version(conn)
        pending = [(n, p) for n, p in pending_possible if n > version]
        if not pending:
            return version
        conn.close()
        if version > 0:
            shutil.copy2(db_path, db_path.with_name(f"{db_path.name}.bak-v{version}"))
        conn = connect(db_path)
        for number, path in pending:
            script = path.read_text(encoding="utf-8")
            try:
                conn.executescript(
                    "BEGIN;\n"
                    "CREATE TABLE IF NOT EXISTS schema_version "
                    "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);\n"
                    f"{script}\n"
                    f"INSERT INTO schema_version (version, applied_at) "
                    f"VALUES ({number}, strftime('%Y-%m-%dT%H:%M:%SZ','now'));\n"
                    "COMMIT;"
                )
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
        return current_version(conn)
    finally:
        conn.close()
