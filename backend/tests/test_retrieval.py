import io

import pytest

from app.core import db
from app.core.config import MIGRATIONS_DIR
from app.retrieval import vectors
from app.retrieval.hybrid import fts_search, rrf_merge
from tests.conftest import wait_idle

NB = "/api/v1/notebooks"


def test_rrf_merge_rewards_agreement():
    merged = rrf_merge([["a", "b", "c"], ["c", "a", "d"]], top_k=3)
    assert [cid for cid, _ in merged][:2] == ["a", "c"]
    assert len(merged) == 3
    assert merged[0][1] > merged[1][1] > merged[2][1]


def test_rrf_top_k_limit():
    assert len(rrf_merge([["a", "b", "c", "d"]], top_k=2)) == 2


def upload_text(client, nid, name, text):
    return client.post(
        f"{NB}/{nid}/sources/files",
        files=[("files", (name, io.BytesIO(text.encode()), "text/plain"))],
    )


def test_fts_only_returns_enabled_sources(configured, notebook, tmp_path):
    nid = notebook["id"]
    upload_text(configured, nid, "a.txt", "Zebras graze on the savanna.")
    upload_text(configured, nid, "b.txt", "Zebras are also found in zoos.")
    a, b = wait_idle(configured, nid)
    store = configured.app.state.store
    conn = store.open(nid)
    assert len(fts_search(conn, "zebras?")) == 2
    configured.patch(f"{NB}/{nid}/sources/{b['id']}", json={"enabled": False})
    hits = fts_search(conn, "zebras")
    assert len(hits) == 1
    owner = conn.execute("SELECT source_id FROM chunks WHERE id = ?", (hits[0],)).fetchone()
    assert owner["source_id"] == a["id"]
    assert fts_search(conn, "?!") == []  # nothing searchable in the query
    conn.close()


def make_index(tmp_path, native=True):
    path = tmp_path / "n.db"
    db.migrate(path, MIGRATIONS_DIR / "notebook")
    conn = db.connect(path)
    idx = vectors.VectorIndex(conn)
    if not native:
        idx.native = False
    with conn:
        for sid, enabled in (("s1", 1), ("s2", 0)):
            conn.execute(
                "INSERT INTO sources (id,name,type,size_bytes,state,enabled,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (sid, sid, "txt", 1, "ready", enabled, "t", "t"),
            )
        rows = [("c1", "s1", [1, 0, 0]), ("c2", "s1", [0, 1, 0]), ("c3", "s2", [1, 0.1, 0])]
        for i, (cid, sid, _v) in enumerate(rows):
            conn.execute(
                "INSERT INTO chunks (id,source_id,ordinal,text,char_start,char_end,location)"
                " VALUES (?,?,?,?,?,?,?)",
                (cid, sid, i, cid, 0, 1, "{}"),
            )
        idx.ensure(3)
        idx.add([r[0] for r in rows], [r[2] for r in rows])
    return conn, idx


@pytest.mark.parametrize("native", [True, False])
def test_vector_search_is_cosine_and_skips_disabled_sources(tmp_path, native):
    conn, idx = make_index(tmp_path, native)
    if native and not idx.native:
        pytest.skip("sqlite-vec unavailable")
    hits = idx.search([2.0, 0.0, 0.0], limit=5)  # unnormalized query: cosine ignores length
    assert [cid for cid, _ in hits] == ["c1", "c2"]  # c3 (disabled source) excluded
    assert hits[0][1] == pytest.approx(1.0, abs=1e-5)
    assert hits[1][1] == pytest.approx(0.0, abs=1e-5)
    assert idx.search([2.0, 0.0, 0.0], limit=1)[0][0] == "c1"


def test_native_search_falls_back_to_brute_force_when_k_too_large(tmp_path, monkeypatch):
    conn, idx = make_index(tmp_path)
    if not idx.native:
        pytest.skip("sqlite-vec unavailable")
    monkeypatch.setattr(vectors, "_VEC0_MAX_K", 2)  # limit + excluded(1) > 2 -> brute force
    assert [c for c, _ in idx.search([1.0, 0.0, 0.0], limit=2)] == ["c1", "c2"]


def test_l2_tables_from_m1_are_upgraded_to_cosine(tmp_path):
    path = tmp_path / "n.db"
    db.migrate(path, MIGRATIONS_DIR / "notebook")
    conn = db.connect(path)
    idx = vectors.VectorIndex(conn)
    if not idx.native:
        pytest.skip("sqlite-vec unavailable")
    with conn:  # what M1 created: L2 table, no metric recorded
        conn.execute(
            "CREATE VIRTUAL TABLE chunk_vectors "
            "USING vec0(chunk_id text primary key, embedding float[2])"
        )
        conn.execute("INSERT INTO notebook_meta VALUES ('embedding_dim', '2')")
        conn.execute(
            "INSERT INTO sources (id,name,type,size_bytes,state,enabled,created_at,updated_at)"
            " VALUES ('s','s','txt',1,'ready',1,'t','t')"
        )
        for i, (cid, vec) in enumerate({"near": [10, 1], "far": [0, 1]}.items()):
            conn.execute(
                "INSERT INTO chunks VALUES (?,?,?,?,?,?,?)", (cid, "s", i, cid, 0, 1, "{}")
            )
            idx.add([cid], [vec])
    assert [c for c, _ in idx.search([1.0, 0.0], 2)] == ["near", "far"]
    meta = conn.execute("SELECT value FROM notebook_meta WHERE key='vector_metric'").fetchone()
    assert meta["value"] == "cosine" and idx.count() == 2
