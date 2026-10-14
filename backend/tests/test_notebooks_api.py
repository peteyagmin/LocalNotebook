import time

from tests.conftest import wait_idle

NB = "/api/v1/notebooks"


def test_create_list_rename_delete(client):
    a = client.post(NB, json={"name": "  Alpha "}).json()
    assert a["name"] == "Alpha" and a["source_count"] == 0
    time.sleep(0.01)
    b = client.post(NB, json={"name": "Beta"}).json()
    # sorted by last-modified, newest first
    assert [n["id"] for n in client.get(NB).json()] == [b["id"], a["id"]]
    time.sleep(0.01)
    client.patch(f"{NB}/{a['id']}", json={"name": "Alpha 2"})
    listing = client.get(NB).json()
    assert [n["name"] for n in listing] == ["Alpha 2", "Beta"]
    assert client.delete(f"{NB}/{a['id']}").status_code == 204
    assert [n["id"] for n in client.get(NB).json()] == [b["id"]]
    assert client.get(f"{NB}/{a['id']}").status_code == 404


def test_blank_name_rejected(client):
    assert client.post(NB, json={"name": "   "}).status_code == 422


def test_notebook_is_a_folder_with_its_own_db(client, tmp_path):
    nb = client.post(NB, json={"name": "X"}).json()
    assert (tmp_path / "notebooks" / nb["id"] / "notebook.db").exists()
    assert nb["size_bytes"] > 0
    client.delete(f"{NB}/{nb['id']}")
    assert not (tmp_path / "notebooks" / nb["id"]).exists()


def test_duplicate_copies_sources_and_index(configured, notebook, tmp_path):
    nid = notebook["id"]
    configured.post(
        f"{NB}/{nid}/sources/text", json={"name": "t", "text": "Hello there. It works."}
    )
    wait_idle(configured, nid)
    dup = configured.post(f"{NB}/{nid}/duplicate").json()
    assert dup["id"] != nid and dup["name"] == "NB (copy)" and dup["source_count"] == 1
    sources = configured.get(f"{NB}/{dup['id']}/sources").json()
    assert sources[0]["state"] == "ready"
    content = configured.get(f"{NB}/{dup['id']}/sources/{sources[0]['id']}/content").json()
    assert "Hello there." in content["text"]
    # independent: deleting the original does not touch the copy
    configured.delete(f"{NB}/{nid}")
    assert configured.get(f"{NB}/{dup['id']}/sources").status_code == 200


def test_unknown_notebook_is_404(client):
    assert client.get(f"{NB}/nope/sources").status_code == 404
    assert client.post(f"{NB}/nope/duplicate").status_code == 404
