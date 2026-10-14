import time

from app.notes.service import merge_notes, prune_citations, remap_markers
from app.retrieval.vectors import VectorIndex
from tests.conftest import wait_idle
from tests.helpers import NB, ready_notebook


def cite(label, chunk="c1", name="Doc"):
    return {
        "label": label,
        "chunk_id": chunk,
        "source_id": "s",
        "source_name": name,
        "excerpt": "x",
        "location": {"page": None, "heading_path": None, "char_start": 0, "char_end": 1},
    }


# --- pure helpers --------------------------------------------------------------------------


def test_remap_and_prune():
    assert remap_markers("A [1] B [2, 3] C [4]", {1: 5, 2: 6, 3: 5}) == "A [5] B [6][5] C "
    kept = prune_citations("Only [2] here", [cite(1), cite(2, "c2")])
    assert [c["label"] for c in kept] == [2]


def test_merge_notes_renumbers_and_dedupes_chunks():
    a = {"title": "A", "content": "x [1] y [2]", "citations": [cite(1, "c1"), cite(2, "c2")]}
    b = {"title": "B", "content": "z [1] w [2] q [9]", "citations": [cite(1, "c2"), cite(2, "c3")]}
    content, citations = merge_notes([a, b])
    assert [(c["label"], c["chunk_id"]) for c in citations] == [(1, "c1"), (2, "c2"), (3, "c3")]
    assert content == "## A\n\nx [1] y [2]\n\n## B\n\nz [2] w [3] q"  # [9] had no citation: dropped


# --- CRUD, indexing, search ----------------------------------------------------------------


def test_note_crud_and_default_title(make_client):
    client, _f, nid = ready_notebook(make_client)
    note = client.post(f"{NB}/{nid}/notes", json={}).json()
    assert note["title"] == "Untitled note" and note["content"] == "" and note["citations"] == []
    client.patch(
        f"{NB}/{nid}/notes/{note['id']}", json={"title": " Plan ", "content": "# Hi\n\nBody"}
    )
    got = client.get(f"{NB}/{nid}/notes/{note['id']}").json()
    assert got["title"] == "Plan" and got["content"].startswith("# Hi")
    listing = client.get(f"{NB}/{nid}/notes").json()
    assert listing[0]["id"] == note["id"] and "Body" in listing[0]["preview"]
    assert client.delete(f"{NB}/{nid}/notes/{note['id']}").status_code == 204
    assert client.get(f"{NB}/{nid}/notes/{note['id']}").status_code == 404
    assert client.get(f"{NB}/{nid}/notes").json() == []


def test_notes_survive_restart(make_client):
    client, _f, nid = ready_notebook(make_client)
    note = client.post(f"{NB}/{nid}/notes", json={"title": "Keep", "content": "Persistent"}).json()
    second = make_client()
    assert second.get(f"{NB}/{nid}/notes/{note['id']}").json()["content"] == "Persistent"


def test_save_chat_answer_to_note_keeps_citations(make_client):
    client, _f, nid = ready_notebook(make_client)
    with client.stream("POST", f"{NB}/{nid}/chat", json={"question": "What do zebras eat?"}) as r:
        list(r.iter_lines())
    messages = client.get(f"{NB}/{nid}/chat").json()
    answer = next(m for m in messages if m["role"] == "assistant")
    note = client.post(f"{NB}/{nid}/chat/messages/{answer['id']}/save-note").json()
    assert note["title"] == "What do zebras eat?" and note["content"] == answer["content"]
    assert [c["source_name"] for c in note["citations"]] == ["zebras.txt"]
    assert note["citations"][0]["chunk_id"] == answer["citations"][0]["chunk_id"]
    question = next(m for m in messages if m["role"] == "user")
    assert client.post(f"{NB}/{nid}/chat/messages/{question['id']}/save-note").status_code == 400
    assert client.post(f"{NB}/{nid}/chat/messages/nope/save-note").status_code == 404


def test_editing_a_note_drops_citations_no_longer_referenced(make_client):
    client, _f, nid = ready_notebook(make_client)
    with client.stream("POST", f"{NB}/{nid}/chat", json={"question": "q"}) as r:
        list(r.iter_lines())
    answer = next(m for m in client.get(f"{NB}/{nid}/chat").json() if m["role"] == "assistant")
    note = client.post(f"{NB}/{nid}/chat/messages/{answer['id']}/save-note").json()
    edited = client.patch(
        f"{NB}/{nid}/notes/{note['id']}", json={"content": "No markers now"}
    ).json()
    assert edited["citations"] == []


def test_note_citations_flag_removed_sources(make_client):
    client, _f, nid = ready_notebook(make_client)
    with client.stream("POST", f"{NB}/{nid}/chat", json={"question": "q"}) as r:
        list(r.iter_lines())
    answer = next(m for m in client.get(f"{NB}/{nid}/chat").json() if m["role"] == "assistant")
    note = client.post(f"{NB}/{nid}/chat/messages/{answer['id']}/save-note").json()
    src = client.get(f"{NB}/{nid}/sources").json()[0]
    client.delete(f"{NB}/{nid}/sources/{src['id']}")
    got = client.get(f"{NB}/{nid}/notes/{note['id']}").json()
    assert got["citations"][0]["removed"] is True and got["citations"][0]["excerpt"]


def wait_note_vectors(client, nid, tmp_path, note_id, expect=True, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        conn = client.app.state.store.open(nid)
        try:
            ids = [
                r["id"]
                for r in conn.execute("SELECT id FROM note_chunks WHERE note_id=?", (note_id,))
            ]
            idx = VectorIndex(conn, "notes")
            have = idx.exists() and idx.count() >= len(ids) > 0
        finally:
            conn.close()
        if have == expect:
            return
        time.sleep(0.05)
    raise AssertionError("note vectors not as expected")


def test_search_finds_notes_by_keyword_and_after_edit(make_client, tmp_path):
    client, _f, nid = ready_notebook(make_client)
    note = client.post(
        f"{NB}/{nid}/notes", json={"title": "Okapi plan", "content": "Study the okapi habitat."}
    ).json()
    hits = client.get(f"{NB}/{nid}/search", params={"q": "okapi"}).json()
    hit = next(h for h in hits if h["kind"] == "note")
    assert (
        hit["note_id"] == note["id"]
        and hit["source_name"] == "Okapi plan"
        and "okapi" in hit["excerpt"].lower()
    )
    wait_note_vectors(client, nid, tmp_path, note["id"])  # vectors arrive in the background
    client.patch(f"{NB}/{nid}/notes/{note['id']}", json={"content": "Now about giraffes."})
    old = [
        h
        for h in client.get(f"{NB}/{nid}/search", params={"q": "okapi"}).json()
        if h["kind"] == "note"
    ]
    assert all("habitat" not in h["excerpt"] for h in old)
    new = [
        h
        for h in client.get(f"{NB}/{nid}/search", params={"q": "giraffes"}).json()
        if h["kind"] == "note"
    ]
    assert new and new[0]["note_id"] == note["id"]


def test_search_mixes_sources_and_notes_and_respects_deletes(make_client, tmp_path):
    client, _f, nid = ready_notebook(make_client, {"z.txt": "The quokka is a marsupial."})
    note = client.post(
        f"{NB}/{nid}/notes", json={"title": "Quokka", "content": "quokka notes"}
    ).json()
    kinds = {h["kind"] for h in client.get(f"{NB}/{nid}/search", params={"q": "quokka"}).json()}
    assert kinds == {"source", "note"}
    client.delete(f"{NB}/{nid}/notes/{note['id']}")
    assert {h["kind"] for h in client.get(f"{NB}/{nid}/search", params={"q": "quokka"}).json()} == {
        "source"
    }
    conn = client.app.state.store.open(nid)
    try:
        for table in ("note_chunks", "note_chunks_fts"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert VectorIndex(conn, "notes").count() == 0
    finally:
        conn.close()


def test_search_keyword_fallback_includes_notes(make_client):
    client, fake, nid = ready_notebook(make_client)
    client.post(f"{NB}/{nid}/notes", json={"title": "T", "content": "numbat facts"})
    fake._unreachable = True
    hits = client.get(f"{NB}/{nid}/search", params={"q": "numbat"}).json()
    assert [h["kind"] for h in hits] == ["note"]


# --- multi-note actions (FR-4.2, FR-4.3) -------------------------------------------------------


def two_cited_notes(client, nid):
    notes = []
    for q in ("first?", "second?"):
        with client.stream("POST", f"{NB}/{nid}/chat", json={"question": q}) as r:
            list(r.iter_lines())
    answers = [m for m in client.get(f"{NB}/{nid}/chat").json() if m["role"] == "assistant"]
    for a in answers:
        notes.append(client.post(f"{NB}/{nid}/chat/messages/{a['id']}/save-note").json())
    return notes


def test_combine_makes_one_new_note_and_keeps_originals(make_client):
    client, _f, nid = ready_notebook(make_client)
    notes = two_cited_notes(client, nid)
    combined = client.post(
        f"{NB}/{nid}/notes/combine", json={"note_ids": [n["id"] for n in notes]}
    ).json()
    assert combined["title"] == "Combined notes"
    assert combined["content"].index("## first?") < combined["content"].index("## second?")
    assert [c["label"] for c in combined["citations"]] == [1]  # same chunk cited twice -> one label
    assert combined["content"].count("[1]") == 2
    assert len(client.get(f"{NB}/{nid}/notes").json()) == 3
    assert client.post(f"{NB}/{nid}/notes/combine", json={"note_ids": ["nope"]}).status_code == 404
    assert client.post(f"{NB}/{nid}/notes/combine", json={"note_ids": []}).status_code == 422


def test_summarize_notes_creates_a_new_note_with_valid_citations(make_client):
    client, fake, nid = ready_notebook(make_client)
    notes = two_cited_notes(client, nid)
    summary = client.post(
        f"{NB}/{nid}/notes/summarize", json={"note_ids": [n["id"] for n in notes]}
    ).json()
    assert summary["title"] == "Summary of 2 notes"
    assert summary["content"] == "The notes discuss zebras [1] and more."  # [42] was invented
    assert [c["label"] for c in summary["citations"]] == [1]
    prompt = [m for _, m in fake.calls if "the user's own notes" in m[-1]["content"]][-1]
    assert "<<<MATERIAL" in prompt[-1]["content"] and "## first?" in prompt[-1]["content"]
    assert len(client.get(f"{NB}/{nid}/notes").json()) == 3


def test_summarize_errors_are_clear(make_client):
    client, fake, nid = ready_notebook(make_client)
    note = client.post(f"{NB}/{nid}/notes", json={"title": "n", "content": "x" * 40_000}).json()
    r = client.post(f"{NB}/{nid}/notes/summarize", json={"note_ids": [note["id"]]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "too_long"
    small = client.post(f"{NB}/{nid}/notes", json={"title": "s", "content": "short"}).json()
    fake._unreachable = True
    r = client.post(f"{NB}/{nid}/notes/summarize", json={"note_ids": [small["id"]]})
    assert r.status_code == 502 and "model server" in r.json()["error"]["message"]


def test_convert_notes_to_sources(make_client):
    client, _f, nid = ready_notebook(make_client)
    notes = two_cited_notes(client, nid)
    r = client.post(
        f"{NB}/{nid}/notes/convert-to-source", json={"note_ids": [n["id"] for n in notes]}
    )
    assert r.status_code == 202 and len(r.json()) == 2
    sources = wait_idle(client, nid)
    assert len(sources) == 3 and all(s["state"] == "ready" for s in sources)
    converted = next(s for s in sources if s["name"] == "first?")
    assert converted["type"] == "text" and converted["enabled"]
    content = client.get(f"{NB}/{nid}/sources/{converted['id']}/content").json()["text"]
    assert content.startswith("first?") and "Zebras graze" in content and "[1]" not in content


def test_convert_respects_the_source_limit(make_client):
    client, _f, nid = ready_notebook(make_client)
    note = client.post(f"{NB}/{nid}/notes", json={"title": "n", "content": "text"}).json()
    client.put("/api/v1/settings", json={"max_sources_per_notebook": 1})
    r = client.post(f"{NB}/{nid}/notes/convert-to-source", json={"note_ids": [note["id"]]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "source_limit"
