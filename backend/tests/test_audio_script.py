"""Script editing and re-synthesis (FR-6.4), the audio endpoint, export."""

import shutil
import subprocess

import pytest

from tests.fakes import FakeTTS
from tests.helpers import wait_artifact
from tests.test_audio_overview import (
    NB,
    detail,
    folder,
    make,
    mp3_duration,
    needs_ffmpeg,
    setup,
)

pytestmark = needs_ffmpeg
SHORT = {"length": "short"}


def fast(make_client, tmp_path, **kwargs):
    client, fake, tts, nid = setup(
        make_client, tmp_path, tts=FakeTTS(seconds_per_char=0.002), **kwargs
    )
    return client, fake, tts, nid, make(client, nid, SHORT)


def put_script(client, nid, a, turns):
    return client.put(f"{NB}/{nid}/artifacts/{a['id']}/script", json={"turns": turns})


def as_input(turns):
    return [
        {"speaker": t["speaker"], "text": t["text"], "chunk_ids": t["chunk_ids"]} for t in turns
    ]


def test_editing_text_speakers_order_and_deleting_turns(make_client, tmp_path):
    client, fake, tts, nid, a = fast(make_client, tmp_path)
    turns = as_input(detail(client, nid, a)["data"]["turns"])
    edited = turns[:]
    edited[0] = {**edited[0], "text": "A brand new opening line."}
    edited[1] = {**edited[1], "speaker": "A"}  # change the speaker
    edited[2], edited[3] = edited[3], edited[2]  # reorder
    del edited[5]  # delete
    r = put_script(client, nid, a, edited)
    assert r.status_code == 200
    saved = r.json()["data"]
    assert saved["outdated"] is True and len(saved["turns"]) == len(turns) - 1
    assert saved["turns"][0]["text"] == "A brand new opening line."
    assert [t["speaker"] for t in saved["turns"][:2]] == ["A", "A"]
    assert saved["turns"][2]["text"] == turns[3]["text"]
    # the audio is untouched until it is rebuilt
    assert r.json()["state"] == "ready"


def test_unchanged_turns_keep_their_times_and_a_plain_resave_is_not_outdated(make_client, tmp_path):
    client, fake, tts, nid, a = fast(make_client, tmp_path)
    original = detail(client, nid, a)["data"]["turns"]
    same = put_script(client, nid, a, as_input(original)).json()["data"]
    assert same["outdated"] is False and [t["start"] for t in same["turns"]] == [
        t["start"] for t in original
    ]
    edited = as_input(original)
    edited[2]["text"] = "Changed."
    after = put_script(client, nid, a, edited).json()["data"]["turns"]
    assert (
        after[2]["start"] is None and after[2]["end"] is None
    )  # no longer lines up with the audio
    assert after[0]["start"] == original[0]["start"] and after[1]["start"] == original[1]["start"]


@pytest.mark.parametrize(
    ("turns", "code"),
    [
        ([], "empty_script"),
        ([{"speaker": "A", "text": "   "}], "empty_turn"),
        ([{"speaker": "C", "text": "Hi"}], "bad_speaker"),
        ([{"speaker": "A", "text": "x" * 2001}], "turn_too_long"),
        ([{"speaker": "A", "text": "Hi"}] * 601, "script_too_long"),
    ],
)
def test_bad_scripts_are_refused(make_client, tmp_path, turns, code):
    client, fake, tts, nid, a = fast(make_client, tmp_path)
    r = put_script(client, nid, a, turns)
    assert r.status_code == 422 and r.json()["error"]["code"] == code


def test_only_audio_overviews_have_scripts(make_client, tmp_path):
    client, fake, tts, nid, a = fast(make_client, tmp_path)
    summary = client.post(f"{NB}/{nid}/artifacts", json={"kind": "summary"}).json()
    wait_artifact(client, nid, summary["id"])
    r = put_script(client, nid, summary, [{"speaker": "A", "text": "Hi"}])
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_script"
    assert client.post(f"{NB}/{nid}/artifacts/{summary['id']}/resynthesize").status_code == 409
    assert (
        put_script(client, nid, {"id": "nope"}, [{"speaker": "A", "text": "Hi"}]).status_code == 404
    )


def test_resynthesis_rebuilds_the_audio_from_the_edited_script_without_a_new_script(
    make_client, tmp_path
):
    client, fake, tts, nid, a = fast(make_client, tmp_path)
    llm_calls = len(fake.calls)
    before = detail(client, nid, a)["data"]
    audio_before = (folder(tmp_path, nid, a) / "audio.mp3").read_bytes()
    edited = as_input(before["turns"])[:6]  # keep six turns
    edited[0]["text"] = (
        "This is a much longer opening line, written by the user, to change the length."
    )
    put_script(client, nid, a, edited)
    tts.calls.clear()

    r = client.post(f"{NB}/{nid}/artifacts/{a['id']}/resynthesize")
    assert r.status_code == 202
    done = wait_artifact(client, nid, a["id"])
    assert done["state"] == "ready" and done["error"] is None
    after = detail(client, nid, a)["data"]
    assert after["outdated"] is False and len(after["turns"]) == 6
    assert after["turns"][0]["text"].startswith("This is a much longer opening")
    assert all(t["start"] is not None for t in after["turns"])
    assert after["duration"] < before["duration"]
    assert (folder(tmp_path, nid, a) / "audio.mp3").read_bytes() != audio_before
    assert mp3_duration(folder(tmp_path, nid, a) / "audio.mp3") == pytest.approx(
        after["duration"], abs=0.5
    )
    assert len(fake.calls) == llm_calls  # no outline or script was written again
    assert len(tts.calls) == 6  # exactly the edited script was spoken
    assert after["title"] == before["title"] and after["options"] == before["options"]


def test_citations_follow_the_script_after_resynthesis(make_client, tmp_path):
    client, fake, tts, nid, a = fast(make_client, tmp_path)
    turns = as_input(detail(client, nid, a)["data"]["turns"])
    assert detail(client, nid, a)["citations"]
    uncited = [{**t, "chunk_ids": []} for t in turns]
    put_script(client, nid, a, uncited)
    client.post(f"{NB}/{nid}/artifacts/{a['id']}/resynthesize")
    wait_artifact(client, nid, a["id"])
    assert detail(client, nid, a)["citations"] == []


def test_a_failed_resynthesis_keeps_the_previous_audio(make_client, tmp_path, monkeypatch):
    client, fake, tts, nid, a = fast(make_client, tmp_path)
    before = (folder(tmp_path, nid, a) / "audio.mp3").read_bytes()
    turns = as_input(detail(client, nid, a)["data"]["turns"])
    turns[0]["text"] = "Edited."
    put_script(client, nid, a, turns)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    client.post(f"{NB}/{nid}/artifacts/{a['id']}/resynthesize")
    failed = wait_artifact(client, nid, a["id"])
    assert failed["state"] == "ready" and "ffmpeg" in failed["error"]
    assert (folder(tmp_path, nid, a) / "audio.mp3").read_bytes() == before
    assert detail(client, nid, a)["data"]["outdated"] is True  # still needs rebuilding


def test_cannot_edit_or_rebuild_while_it_is_running(make_client, tmp_path):
    client, fake, tts, nid, a = fast(make_client, tmp_path)
    conn = client.app.state.store.open(nid)
    with conn:
        conn.execute("UPDATE artifacts SET state='running' WHERE id = ?", (a["id"],))
    conn.close()
    assert put_script(client, nid, a, [{"speaker": "A", "text": "Hi"}]).status_code == 409
    assert client.post(f"{NB}/{nid}/artifacts/{a['id']}/resynthesize").status_code == 409


def test_regenerating_writes_a_new_script_with_new_options(make_client, tmp_path):
    client, fake, tts, nid, a = fast(make_client, tmp_path)
    client.post(
        f"{NB}/{nid}/artifacts/{a['id']}/regenerate", json={"options": {"format": "debate"}}
    )
    done = wait_artifact(client, nid, a["id"])
    assert done["options"] == {"length": "short", "format": "debate"}
    assert detail(client, nid, a)["data"]["options"]["format"] == "debate"


# --- the audio file ------------------------------------------------------------------------------


def test_audio_is_served_and_exported_as_mp3(make_client, tmp_path):
    client, fake, tts, nid, a = fast(make_client, tmp_path)
    played = client.get(f"{NB}/{nid}/artifacts/{a['id']}/audio")
    assert played.status_code == 200 and played.headers["content-type"] == "audio/mpeg"
    exported = client.get(f"{NB}/{nid}/artifacts/{a['id']}/export", params={"format": "mp3"})
    assert (
        exported.content == played.content
        and "Audio-overview.mp3" in exported.headers["content-disposition"]
    )
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", "-"],
        input=played.content, capture_output=True, check=True,
    )  # fmt: skip
    assert probe.stdout.strip() == b"mp3"
    for fmt in ("md", "json", "pdf"):
        assert (
            client.get(f"{NB}/{nid}/artifacts/{a['id']}/export", params={"format": fmt}).status_code
            == 422
        )


def test_no_audio_before_it_exists(make_client, tmp_path):
    client, fake, tts, nid, a = fast(make_client, tmp_path)
    summary = client.post(f"{NB}/{nid}/artifacts", json={"kind": "summary"}).json()
    wait_artifact(client, nid, summary["id"])
    assert client.get(f"{NB}/{nid}/artifacts/{summary['id']}/audio").status_code == 404
    assert client.get(f"{NB}/{nid}/artifacts/nope/audio").status_code == 404


def test_it_goes_stale_when_a_source_changes_like_any_artifact(make_client, tmp_path):
    client, fake, tts, nid, a = fast(make_client, tmp_path)
    source = client.get(f"{NB}/{nid}/sources").json()[0]
    client.patch(f"{NB}/{nid}/sources/{source['id']}", json={"enabled": False})
    assert detail(client, nid, a)["stale"] is True


def test_deleting_it_removes_its_audio(make_client, tmp_path):
    client, fake, tts, nid, a = fast(make_client, tmp_path)
    assert (folder(tmp_path, nid, a) / "audio.mp3").exists()
    client.delete(f"{NB}/{nid}/artifacts/{a['id']}")
    assert not folder(tmp_path, nid, a).exists()
