"""Notebook export/import (FR-1.3) and index rebuild after an embedding-model change (FR-8.5)."""

import io
import json
import time
import zipfile

from app.core import db
from app.core.notebooks import NotebookStore
from app.retrieval.vectors import index_model
from tests.helpers import NB, generate, ready_notebook

TEXTS = {"zebras.txt": "Zebras graze on grass in herds across the savanna."}


def export_bytes(client, nid) -> bytes:
    r = client.get(f"{NB}/{nid}/export")
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith('attachment; filename="')
    return r.content


def import_bytes(client, data: bytes):
    return client.post(
        f"{NB}/import", files={"file": ("x.lnb", io.BytesIO(data), "application/zip")}
    )


def make_lnb(members: dict[str, bytes | str], manifest: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if manifest is not None:
            zf.writestr("manifest.json", json.dumps(manifest))
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


MANIFEST = {
    "format": "lnb",
    "format_version": 1,
    "notebook": {"id": "n-x", "name": "X", "created_at": "2026-01-01T00:00:00Z"},
}


def test_export_contains_manifest_database_sources_and_artifacts(make_client):
    client, _, nid = ready_notebook(make_client, TEXTS)
    generate(client, nid, "summary")
    with zipfile.ZipFile(io.BytesIO(export_bytes(client, nid))) as zf:
        names = zf.namelist()
        manifest = json.loads(zf.read("manifest.json"))
    assert names[0] == "manifest.json"
    assert "notebook.db" in names
    assert any(n.startswith("sources/") and n.endswith("/original.txt") for n in names)
    assert any(n.startswith("sources/") and n.endswith("/extracted.json") for n in names)
    assert any(n.startswith("artifacts/") and n.endswith("/content.md") for n in names)
    assert not any(".bak" in n or n.endswith("-wal") for n in names)
    assert manifest["format"] == "lnb"
    assert manifest["notebook"]["id"] == nid
    assert manifest["notebook"]["name"] == "NB"
    assert manifest["source_count"] == 1
    assert manifest["embedding_model"] == "e"


def test_notebook_exported_on_one_machine_imports_cleanly_on_another(make_client, tmp_path):
    client, fake, nid = ready_notebook(make_client, TEXTS)
    summary = generate(client, nid, "summary")
    data = export_bytes(client, nid)

    other = make_client(fake, root=tmp_path / "other-machine")
    other.put("/api/v1/settings", json={"chat_model": "c", "embedding_model": "e"})
    r = import_bytes(other, data)
    assert r.status_code == 201, r.text
    imported = r.json()
    assert imported["id"] == nid and imported["name"] == "NB"  # no conflict: same identity
    assert imported["source_count"] == 1
    assert imported["index_stale"] is False

    sources = other.get(f"{NB}/{nid}/sources").json()
    assert [s["state"] for s in sources] == ["ready"]
    assert (
        "Zebras graze" in other.get(f"{NB}/{nid}/sources/{sources[0]['id']}/content").json()["text"]
    )
    hits = other.get(f"{NB}/{nid}/search", params={"q": "savanna"}).json()
    assert hits and "savanna" in hits[0]["excerpt"]
    again = other.get(f"{NB}/{nid}/artifacts/{summary['id']}").json()
    assert again["content"] == summary["content"]
    assert [n["id"] for n in other.get(NB).json()] == [nid]


def test_import_never_overwrites_and_copies_on_id_conflict(make_client):
    client, _, nid = ready_notebook(make_client, TEXTS)
    data = export_bytes(client, nid)
    r = import_bytes(client, data)
    assert r.status_code == 201
    copy = r.json()
    assert copy["id"] != nid
    assert copy["name"] == "NB (copy)"
    assert copy["source_count"] == 1
    assert client.get(f"{NB}/{nid}").json()["name"] == "NB"  # the original is untouched
    assert len(client.get(NB).json()) == 2
    # the copy has its own files
    sid = client.get(f"{NB}/{copy['id']}/sources").json()[0]["id"]
    assert client.get(f"{NB}/{copy['id']}/sources/{sid}/content").status_code == 200


def test_export_during_processing_marks_unfinished_sources_failed(make_client, tmp_path):
    client, _, nid = ready_notebook(make_client, TEXTS)
    store = NotebookStore(tmp_path)
    conn = db.connect(store.db_path(nid))
    with conn:
        conn.execute("UPDATE sources SET state = 'processing'")
    conn.close()
    other = make_client(root=tmp_path / "m2")
    imported = import_bytes(other, export_bytes(client, nid)).json()
    source = other.get(f"{NB}/{imported['id']}/sources").json()[0]
    assert source["state"] == "failed" and "Interrupted" in source["error"]


def test_import_rejects_files_that_are_not_valid_notebooks(make_client):
    client = make_client()
    bad = {
        "not a zip": b"hello",
        "no manifest": make_lnb({"notebook.db": b"x"}),
        "wrong format": make_lnb({"notebook.db": b"x"}, {**MANIFEST, "format": "other"}),
        "newer format": make_lnb({"notebook.db": b"x"}, {**MANIFEST, "format_version": 99}),
        "no database": make_lnb({"sources/a/original.txt": b"x"}, MANIFEST),
        "path traversal": make_lnb({"notebook.db": b"x", "sources/../../evil": b"x"}, MANIFEST),
        "absolute path": make_lnb({"notebook.db": b"x", "/etc/evil": b"x"}, MANIFEST),
        "unexpected entry": make_lnb({"notebook.db": b"x", "other/file": b"x"}, MANIFEST),
        "damaged database": make_lnb({"notebook.db": b"this is not sqlite"}, MANIFEST),
    }
    for label, data in bad.items():
        r = import_bytes(client, data)
        assert r.status_code == 422, label
        assert r.json()["error"]["code"] == "invalid_notebook_file", label
    assert client.get(NB).json() == []


def test_import_rejects_a_notebook_from_a_newer_version(make_client, tmp_path):
    client, _, nid = ready_notebook(make_client, TEXTS)
    path = NotebookStore(tmp_path).db_path(nid)
    conn = db.connect(path)
    with conn:
        conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (999, 'now')")
    conn.close()
    r = import_bytes(make_client(root=tmp_path / "m2"), export_bytes(client, nid))
    assert r.status_code == 422
    assert "newer version" in r.json()["error"]["message"]


def test_import_leaves_no_partial_folder_after_a_failure(make_client, tmp_path):
    client = make_client()
    import_bytes(client, make_lnb({"notebook.db": b"junk"}, MANIFEST))
    names = [p.name for p in (tmp_path / "notebooks").iterdir()]
    assert names == []


def wait_reindexed(client, nid, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = client.get(f"{NB}/{nid}").json()
        if not info["reindexing"]:
            return info
        time.sleep(0.05)
    raise AssertionError("still reindexing")


def test_changing_the_embedding_model_marks_indexes_stale_until_rebuilt(make_client, tmp_path):
    client, fake, nid = ready_notebook(make_client, TEXTS)
    client.post(f"{NB}/{nid}/notes", json={})  # a note is rebuilt too
    assert client.get(f"{NB}/{nid}").json()["index_stale"] is False

    client.put("/api/v1/settings", json={"embedding_model": "e2"})
    assert client.get(f"{NB}/{nid}").json()["index_stale"] is True
    assert [n["index_stale"] for n in client.get(NB).json()] == [True]

    fake._embed_dim = 12  # the new model has a different vector size
    r = client.post(f"{NB}/{nid}/rebuild-index")
    assert r.status_code == 202
    info = wait_reindexed(client, nid)
    assert info["index_stale"] is False
    conn = db.connect(NotebookStore(tmp_path).db_path(nid))
    try:
        assert index_model(conn) == "e2"
        dim = conn.execute("SELECT value FROM notebook_meta WHERE key='embedding_dim'").fetchone()
        assert dim["value"] == "12"
    finally:
        conn.close()
    hits = client.get(f"{NB}/{nid}/search", params={"q": "savanna"}).json()
    assert hits and "savanna" in hits[0]["excerpt"]
    assert client.get(f"{NB}/{nid}/sources").json()[0]["state"] == "ready"


def test_a_failed_rebuild_keeps_the_index_marked_out_of_date(make_client):
    client, fake, nid = ready_notebook(make_client, TEXTS)
    client.put("/api/v1/settings", json={"embedding_model": "e2"})
    fake._unreachable = True
    client.post(f"{NB}/{nid}/rebuild-index")
    info = wait_reindexed(client, nid)
    assert info["index_stale"] is True
    fake._unreachable = False
    client.post(f"{NB}/{nid}/rebuild-index")
    assert wait_reindexed(client, nid)["index_stale"] is False


def test_rebuild_needs_an_embedding_model(make_client):
    client, _, nid = ready_notebook(make_client, TEXTS)
    client.put("/api/v1/settings", json={"embedding_model": ""})
    r = client.post(f"{NB}/{nid}/rebuild-index")
    assert r.status_code == 409
    assert client.get(f"{NB}/{nid}").json()["index_stale"] is False
