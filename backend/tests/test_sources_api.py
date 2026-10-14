import io
import json
import sqlite3

from app.core.config import RuntimeConfig  # noqa: F401
from app.llm.fake import FakeLLMClient
from tests.conftest import make_docx, make_pdf, wait_idle

NB = "/api/v1/notebooks"


def upload(client, nid, files):
    return client.post(
        f"{NB}/{nid}/sources/files",
        files=[
            ("files", (name, io.BytesIO(data), "application/octet-stream")) for name, data in files
        ],
    )


def paste(client, nid, text, name="Notes"):
    return client.post(f"{NB}/{nid}/sources/text", json={"name": name, "text": text})


def db_of(tmp_path, nid):
    conn = sqlite3.connect(tmp_path / "notebooks" / nid / "notebook.db")
    conn.row_factory = sqlite3.Row
    return conn


def test_every_supported_type_is_ingested_and_viewable(configured, notebook, tmp_path):
    nid = notebook["id"]
    docx_path = tmp_path / "d.docx"
    make_docx(docx_path, [("Heading 1", "Title"), ("Normal", "Docx body text here.")])
    r = upload(
        configured,
        nid,
        [
            ("a.pdf", make_pdf(["Pdf page one text.", "Pdf page two text."])),
            ("b.docx", docx_path.read_bytes()),
            ("c.txt", b"Plain text content."),
            ("d.md", b"# Head\n\nMarkdown content."),
        ],
    )
    assert r.status_code == 202
    paste(configured, nid, "Pasted words go here.")
    sources = wait_idle(configured, nid)
    assert [s["state"] for s in sources] == ["ready"] * 5
    assert {s["type"] for s in sources} == {"pdf", "docx", "txt", "md", "text"}
    assert all(s["enabled"] for s in sources)  # enabled by default (FR-2.7)
    assert all(
        s["guide"] == {"summary": "A short summary.", "topics": ["one", "two", "three"]}
        for s in sources
    )
    pdf = sources[0]
    assert pdf["page_count"] == 2 and pdf["char_count"] > 0
    content = configured.get(f"{NB}/{nid}/sources/{pdf['id']}/content").json()
    assert "Pdf page one text." in content["text"]
    assert [s["page"] for s in content["segments"]] == [1, 2]


def test_chunks_fts_and_vectors_written(configured, notebook, tmp_path):
    nid = notebook["id"]
    paste(configured, nid, "Zebras are striped animals. " * 5)
    wait_idle(configured, nid)
    conn = db_of(tmp_path, nid)
    chunk = conn.execute("SELECT * FROM chunks").fetchone()
    assert json.loads(chunk["location"])["char_start"] == chunk["char_start"]
    hits = conn.execute(
        "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH 'zebras'"
    ).fetchall()
    assert [h["chunk_id"] for h in hits] == [chunk["id"]]
    from app.retrieval.vectors import VectorIndex

    assert VectorIndex(conn).count() == conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]


def test_original_file_kept_unmodified(configured, notebook, tmp_path):
    nid = notebook["id"]
    payload = b"Exact bytes\r\nkept as-is.  "
    s = upload(configured, nid, [("keep.txt", payload)]).json()[0]
    wait_idle(configured, nid)
    folder = tmp_path / "notebooks" / nid / "sources" / s["id"]
    assert (folder / "original.txt").read_bytes() == payload
    assert (folder / "extracted.json").exists()


def test_failure_shows_error_and_retry_recovers(make_client, tmp_path):
    client = make_client()
    nid = client.post(NB, json={"name": "NB"}).json()["id"]
    paste(client, nid, "Some text to ingest.")
    failed = wait_idle(client, nid)[0]
    assert failed["state"] == "failed" and "embedding model" in failed["error"]
    client.put("/api/v1/settings", json={"chat_model": "c", "embedding_model": "e"})
    assert client.post(f"{NB}/{nid}/sources/{failed['id']}/retry").status_code == 202
    assert wait_idle(client, nid)[0]["state"] == "ready"
    # only failed sources can be retried
    assert client.post(f"{NB}/{nid}/sources/{failed['id']}/retry").status_code == 409


def test_parse_failure_is_isolated_to_that_source(configured, notebook):
    nid = notebook["id"]
    upload(configured, nid, [("bad.pdf", b"not really a pdf"), ("ok.txt", b"Fine content.")])
    by_name = {s["name"]: s for s in wait_idle(configured, nid)}
    assert by_name["bad.pdf"]["state"] == "failed" and "PDF" in by_name["bad.pdf"]["error"]
    assert by_name["ok.txt"]["state"] == "ready"


def test_llm_outage_fails_source_with_message(make_client):
    client = make_client(FakeLLMClient(unreachable=True))
    client.put("/api/v1/settings", json={"chat_model": "c", "embedding_model": "e"})
    nid = client.post(NB, json={"name": "NB"}).json()["id"]
    paste(client, nid, "Text.")
    s = wait_idle(client, nid)[0]
    assert s["state"] == "failed" and "model server" in s["error"]


def test_invalid_guide_json_retries_then_fails(make_client):
    client = make_client(FakeLLMClient(default_reply="not json"))
    client.put("/api/v1/settings", json={"chat_model": "c", "embedding_model": "e"})
    nid = client.post(NB, json={"name": "NB"}).json()["id"]
    paste(client, nid, "Text.")
    s = wait_idle(client, nid)[0]
    assert s["state"] == "failed" and "valid answer" in s["error"]


def test_enable_disable_and_select_all_none(configured, notebook):
    nid = notebook["id"]
    paste(configured, nid, "One.", "a")
    paste(configured, nid, "Two.", "b")
    a, b = wait_idle(configured, nid)
    r = configured.patch(f"{NB}/{nid}/sources/{a['id']}", json={"enabled": False})
    assert r.json()["enabled"] is False
    states = {s["name"]: s["enabled"] for s in configured.get(f"{NB}/{nid}/sources").json()}
    assert states == {"a": False, "b": True}
    none = configured.post(f"{NB}/{nid}/sources/enabled", json={"enabled": False}).json()
    assert not any(s["enabled"] for s in none)
    all_ = configured.post(f"{NB}/{nid}/sources/enabled", json={"enabled": True}).json()
    assert all(s["enabled"] for s in all_)


def test_unsupported_type_and_limits_rejected_before_work(configured, notebook):
    nid = notebook["id"]
    r = upload(configured, nid, [("ok.txt", b"x"), ("pic.png", b"x")])
    assert r.status_code == 400 and r.json()["error"]["code"] == "unsupported_type"
    configured.put("/api/v1/settings", json={"max_upload_mb": 1})
    r = upload(configured, nid, [("big.txt", b"a" * (1024 * 1024 + 1))])
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"
    configured.put("/api/v1/settings", json={"max_sources_per_notebook": 2})
    paste(configured, nid, "1")
    paste(configured, nid, "2")
    r = paste(configured, nid, "3")
    assert r.status_code == 400 and r.json()["error"]["code"] == "source_limit"
    r = upload(configured, nid, [("x.txt", b"x")])
    assert r.json()["error"]["code"] == "source_limit"
    # nothing from the rejected requests was created
    assert len(wait_idle(configured, nid)) == 2


def test_empty_paste_rejected(configured, notebook):
    assert paste(configured, notebook["id"], "   ").status_code == 400


def test_delete_source_removes_everything(configured, notebook, tmp_path):
    nid = notebook["id"]
    s = paste(configured, nid, "Delete me please. " * 10).json()[0]
    wait_idle(configured, nid)
    assert configured.delete(f"{NB}/{nid}/sources/{s['id']}").status_code == 204
    conn = db_of(tmp_path, nid)
    for table in ("sources", "chunks", "chunks_fts", "jobs"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    from app.retrieval.vectors import VectorIndex

    assert VectorIndex(conn).count() == 0
    assert not (tmp_path / "notebooks" / nid / "sources" / s["id"]).exists()
    assert configured.get(f"{NB}/{nid}/sources/{s['id']}").status_code == 404


def test_everything_survives_restart(make_client, tmp_path):
    first = make_client()
    first.put("/api/v1/settings", json={"chat_model": "c", "embedding_model": "e"})
    nid = first.post(NB, json={"name": "Keep"}).json()["id"]
    paste(first, nid, "Persistent text.")
    before = wait_idle(first, nid)
    first.patch(f"{NB}/{nid}/sources/{before[0]['id']}", json={"enabled": False})
    second = make_client()  # fresh app on the same data root
    assert [n["name"] for n in second.get(NB).json()] == ["Keep"]
    after = second.get(f"{NB}/{nid}/sources").json()
    assert after[0]["id"] == before[0]["id"] and after[0]["state"] == "ready"
    assert after[0]["enabled"] is False and after[0]["guide"]["topics"]
    assert (
        "Persistent text."
        in second.get(f"{NB}/{nid}/sources/{after[0]['id']}/content").json()["text"]
    )


def test_unfinished_work_marked_interrupted_on_restart(make_client, tmp_path):
    first = make_client()
    nid = first.post(NB, json={"name": "NB"}).json()["id"]
    conn = db_of(tmp_path, nid)
    with conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, size_bytes, state, created_at, updated_at) "
            "VALUES ('s1', 'x', 'txt', 1, 'processing', 't', 't')"
        )
        conn.execute(
            "INSERT INTO jobs (id, kind, target_id, state, created_at, updated_at) "
            "VALUES ('j1', 'ingest', 's1', 'running', 't', 't')"
        )
    conn.close()
    second = make_client()
    s = second.get(f"{NB}/{nid}/sources").json()[0]
    assert s["state"] == "failed" and "Interrupted" in s["error"]
    conn = db_of(tmp_path, nid)
    assert conn.execute("SELECT state FROM jobs").fetchone()[0] == "interrupted"


def test_sources_stream_sends_snapshot_and_ends(configured, notebook):
    nid = notebook["id"]
    paste(configured, nid, "Stream me.")
    with configured.stream("GET", f"{NB}/{nid}/sources/stream") as r:
        events = [line[6:] for line in r.iter_lines() if line.startswith("data: ")]
    assert events, "expected at least one snapshot"
    assert json.loads(events[-1])[0]["state"] == "ready"


def test_index_rebuilds_from_extracted_json_only(configured, notebook, tmp_path):
    """DR-3"""
    import asyncio

    from app.ingest.pipeline import reindex_source

    nid = notebook["id"]
    s = paste(configured, nid, "Rebuildable sentence one. Rebuildable sentence two.").json()[0]
    wait_idle(configured, nid)
    conn = db_of(tmp_path, nid)
    before = [tuple(r) for r in conn.execute("SELECT ordinal, text, char_start FROM chunks")]
    with conn:
        conn.execute("DELETE FROM chunks_fts")
        conn.execute("DELETE FROM chunks")
    conn.close()
    store = configured.app.state.store
    n = asyncio.run(reindex_source(store, nid, s["id"], FakeLLMClient(), "emb"))
    conn = db_of(tmp_path, nid)
    after = [tuple(r) for r in conn.execute("SELECT ordinal, text, char_start FROM chunks")]
    assert n == len(before) and after == before
    assert conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0] == len(before)


def test_vector_fallback_when_extension_unavailable(monkeypatch, tmp_path):
    from app.core import db
    from app.core.config import MIGRATIONS_DIR
    from app.retrieval import vectors

    monkeypatch.setattr(vectors, "try_load", lambda conn: False)
    path = tmp_path / "n.db"
    db.migrate(path, MIGRATIONS_DIR / "notebook")
    conn = db.connect(path)
    idx = vectors.VectorIndex(conn)
    with conn:
        idx.ensure(3)
        idx.add(["a", "b"], [[1, 2, 3], [4, 5, 6]])
    assert idx.table == "chunk_vectors_fallback" and idx.count() == 2
    idx.delete(["a"])
    assert idx.count() == 1
    import pytest

    with pytest.raises(ValueError, match="Rebuild"):
        idx.ensure(5)
