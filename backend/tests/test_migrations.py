import sqlite3

import pytest

from app.core import db


def _write(d, name, sql):
    (d / name).write_text(sql)


def test_apply_and_idempotent(tmp_path):
    mig = tmp_path / "m"
    mig.mkdir()
    _write(mig, "0001_a.sql", "CREATE TABLE a (x INTEGER);")
    path = tmp_path / "t.db"
    assert db.migrate(path, mig) == 1
    assert db.migrate(path, mig) == 1
    assert not list(tmp_path.glob("*.bak-*"))


def test_backup_before_upgrade(tmp_path):
    mig = tmp_path / "m"
    mig.mkdir()
    _write(mig, "0001_a.sql", "CREATE TABLE a (x INTEGER);")
    path = tmp_path / "t.db"
    db.migrate(path, mig)
    _write(mig, "0002_b.sql", "CREATE TABLE b (y INTEGER);")
    assert db.migrate(path, mig) == 2
    assert (tmp_path / "t.db.bak-v1").exists()


def test_failed_migration_rolls_back(tmp_path):
    mig = tmp_path / "m"
    mig.mkdir()
    _write(mig, "0001_a.sql", "CREATE TABLE a (x INTEGER);")
    path = tmp_path / "t.db"
    db.migrate(path, mig)
    _write(mig, "0002_bad.sql", "CREATE TABLE b (y INTEGER); THIS IS NOT SQL;")
    with pytest.raises(sqlite3.Error):
        db.migrate(path, mig)
    conn = db.connect(path)
    try:
        assert db.current_version(conn) == 1
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master")}
        assert "b" not in tables
    finally:
        conn.close()


def test_real_app_migrations_apply(tmp_path):
    from app.core.config import MIGRATIONS_DIR

    assert db.migrate(tmp_path / "app.db", MIGRATIONS_DIR / "app") >= 1
