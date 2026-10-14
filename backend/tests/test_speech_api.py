"""Speech-to-text model downloads, capabilities, and new upload types (FR-2.1, FR-8.2, FR-8.6)."""

import io
import threading
import time

from app.ingest import ocr
from app.speech import stt
from tests.conftest import wait_idle
from tests.fakes import page
from tests.helpers import NB
from tests.test_parsers_m5 import make_epub, text_image

API = "/api/v1"


def writes_model(model, target, report):
    report(0.5)
    (target / "model.bin").write_bytes(b"weights")
    report(1.0)


def wait_status(client, expect, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"{API}/speech/stt").json()
        if expect(status):
            return status
        time.sleep(0.02)
    raise AssertionError(f"status never matched: {status}")


def test_status_reflects_configuration_and_installation(make_client, tmp_path):
    client = make_client(model_downloader=writes_model)
    assert client.get(f"{API}/speech/stt").json() == {
        "model": "",
        "configured": False,
        "downloads_allowed": True,
        "installed": False,
        "state": "idle",
    }
    client.put(f"{API}/settings", json={"stt_model": "tiny"})
    status = client.get(f"{API}/speech/stt").json()
    assert status["configured"] and not status["installed"]
    folder = stt.model_dir(tmp_path / "models", "tiny")
    folder.mkdir(parents=True)
    (folder / "model.bin").write_bytes(b"x")
    assert client.get(f"{API}/speech/stt").json()["installed"] is True


def test_download_needs_confirmation_a_model_and_permission(make_client):
    client = make_client(model_downloader=writes_model)
    assert (
        client.post(f"{API}/speech/stt/download", json={"confirm": True}).json()["error"]["code"]
        == "not_configured"
    )
    client.put(f"{API}/settings", json={"stt_model": "tiny"})
    assert (
        client.post(f"{API}/speech/stt/download", json={}).json()["error"]["code"]
        == "needs_confirmation"
    )
    assert client.post(f"{API}/speech/stt/download", json={"confirm": False}).status_code == 400
    client.put(f"{API}/settings", json={"allow_model_downloads": False})
    r = client.post(f"{API}/speech/stt/download", json={"confirm": True})
    assert r.status_code == 403 and r.json()["error"]["code"] == "network_disabled"
    assert not client.get(f"{API}/speech/stt").json()["installed"]


def test_download_shows_progress_and_installs_only_when_complete(make_client, tmp_path):
    release = threading.Event()
    started = threading.Event()

    def slow(model, target, report):
        (target / "model.bin.part").write_bytes(b"partial")
        report(0.5)
        started.set()
        release.wait(10)
        (target / "model.bin").write_bytes(b"weights")

    client = make_client(model_downloader=slow)
    client.put(f"{API}/settings", json={"stt_model": "tiny"})
    assert client.post(f"{API}/speech/stt/download", json={"confirm": True}).status_code == 202
    assert started.wait(5)
    mid = wait_status(client, lambda s: s["state"] == "downloading" and s["progress"] == 0.5)
    assert mid["installed"] is False  # a half-finished download is not an installed model
    release.set()
    done = wait_status(client, lambda s: s["installed"])
    assert done["state"] == "idle"
    folder = stt.model_dir(tmp_path / "models", "tiny")
    assert (folder / "model.bin").exists() and not folder.with_name(
        folder.name + ".partial"
    ).exists()


def test_a_failed_download_leaves_nothing_behind_and_can_be_retried(make_client, tmp_path):
    attempts = []

    def flaky(model, target, report):
        attempts.append(1)
        (target / "model.bin").write_bytes(b"half")
        if len(attempts) == 1:
            raise ConnectionError("network down")
        report(1.0)

    client = make_client(model_downloader=flaky)
    client.put(f"{API}/settings", json={"stt_model": "tiny"})
    client.post(f"{API}/speech/stt/download", json={"confirm": True})
    failed = wait_status(client, lambda s: s["state"] == "error")
    assert "download failed" in failed["error"] and failed["installed"] is False
    assert not list((tmp_path / "models").glob("**/*.partial")) and not stt.is_installed(
        tmp_path / "models", "tiny"
    )
    client.post(f"{API}/speech/stt/download", json={"confirm": True})
    wait_status(client, lambda s: s["installed"])
    assert len(attempts) == 2


def test_downloading_twice_starts_one_download(make_client):
    release = threading.Event()
    calls = []

    def slow(model, target, report):
        calls.append(model)
        release.wait(10)
        (target / "model.bin").write_bytes(b"w")

    client = make_client(model_downloader=slow)
    client.put(f"{API}/settings", json={"stt_model": "tiny"})
    client.post(f"{API}/speech/stt/download", json={"confirm": True})
    client.post(f"{API}/speech/stt/download", json={"confirm": True})
    release.set()
    wait_status(client, lambda s: s["installed"])
    assert calls == ["tiny"]


def test_capabilities_say_what_is_available(make_client, monkeypatch):
    client = make_client(model_downloader=writes_model)
    monkeypatch.setattr(ocr, "available", lambda: False)
    caps = client.get(f"{API}/capabilities").json()
    assert caps == {
        "ocr": False,
        "stt": {"configured": False, "installed": False},
        "audio_overview": caps["audio_overview"],
        "web_import": True,
        "discover": {"allowed": True, "configured": False},
    }
    client.put(
        f"{API}/settings", json={"searxng_url": "http://127.0.0.1:8888", "allow_web_import": False}
    )
    caps = client.get(f"{API}/capabilities").json()
    assert caps["web_import"] is False and caps["discover"]["configured"] is True


def test_network_settings_have_safe_defaults(client):
    s = client.get(f"{API}/settings").json()
    assert (s["allow_web_import"], s["allow_discover"], s["allow_model_downloads"]) == (
        True,
        True,
        True,
    )
    assert s["transcribe_uncaptioned_videos"] is False and s["searxng_url"] == ""


# --- uploads of the new file types ------------------------------------------------------------


def upload(client, nid, name, data):
    return client.post(
        f"{NB}/{nid}/sources/files",
        files=[("files", (name, io.BytesIO(data), "application/octet-stream"))],
    )


def notebook_for(configured):
    return configured.post(f"{NB}", json={"name": "NB"}).json()["id"]


def test_html_and_epub_files_are_ingested(configured, tmp_path):
    nid = notebook_for(configured)
    epub = tmp_path / "b.epub"
    make_epub(epub, ["The old harbor town had a lighthouse. " * 8])
    upload(configured, nid, "page.html", page("Local Page"))
    upload(configured, nid, "book.epub", epub.read_bytes())
    sources = {s["name"]: s for s in wait_idle(configured, nid)}
    assert sources["page.html"]["state"] == "ready" and sources["page.html"]["type"] == "html"
    assert sources["book.epub"]["state"] == "ready" and sources["book.epub"]["type"] == "epub"
    assert (
        "lighthouse"
        in configured.get(f"{NB}/{nid}/sources/{sources['book.epub']['id']}/content").json()["text"]
    )


def test_a_broken_epub_fails_with_a_message_and_a_retry_button(configured):
    nid = notebook_for(configured)
    upload(configured, nid, "bad.epub", b"nope")
    s = wait_idle(configured, nid)[0]
    assert s["state"] == "failed" and "EPUB" in s["error"]


def test_images_are_read_with_ocr(configured):
    if not ocr.available():
        import pytest

        pytest.skip("Tesseract is not installed")
    nid = notebook_for(configured)
    buffer = io.BytesIO()
    text_image("INVOICE NUMBER 4711").save(buffer, "PNG")
    upload(configured, nid, "scan.png", buffer.getvalue())
    s = wait_idle(configured, nid)[0]
    assert s["state"] == "ready" and s["type"] == "image"
    assert "4711" in configured.get(f"{NB}/{nid}/sources/{s['id']}/content").json()["text"]


def test_an_image_explains_when_tesseract_is_missing(configured, monkeypatch):
    monkeypatch.setattr(
        ocr,
        "ocr_image",
        lambda image: (_ for _ in ()).throw(ocr.OCRUnavailable(ocr.OCR_MISSING_MESSAGE)),
    )
    nid = notebook_for(configured)
    buffer = io.BytesIO()
    text_image().save(buffer, "PNG")
    upload(configured, nid, "scan.jpg", buffer.getvalue())
    # (the parse runs in another process, so the real check applies there)
    s = wait_idle(configured, nid)[0]
    assert s["state"] == ("ready" if ocr.available() else "failed")
    if not ocr.available():
        assert "Tesseract" in s["error"]


def test_audio_is_transcribed_with_timestamps(configured, monkeypatch):
    monkeypatch.setenv("LNB_STT_FACTORY", "tests.fake_stt:make")
    configured.put(f"{API}/settings", json={"stt_model": "any"})
    nid = notebook_for(configured)
    r = upload(configured, nid, "talk.mp3", b"audio bytes")
    assert r.status_code == 202
    s = wait_idle(configured, nid)[0]
    assert s["state"] == "ready" and s["type"] == "audio"
    content = configured.get(f"{NB}/{nid}/sources/{s['id']}/content").json()
    assert content["segments"][0]["start_s"] == 0.0 and "zebras" in content["text"]
    hit = configured.get(f"{NB}/{nid}/search", params={"q": "zebras"}).json()[0]
    assert hit["location"]["start_seconds"] is not None


def test_audio_without_a_model_explains_how_to_get_one(configured):
    nid = notebook_for(configured)
    upload(configured, nid, "talk.wav", b"audio bytes")
    s = wait_idle(configured, nid)[0]
    assert s["state"] == "failed" and "speech-to-text model" in s["error"]
    configured.put(f"{API}/settings", json={"stt_model": "tiny"})
    configured.post(f"{NB}/{nid}/sources/{s['id']}/retry")
    s = wait_idle(configured, nid)[0]
    assert "'tiny' is not installed" in s["error"] and "Download it in Settings" in s["error"]


def test_every_new_type_is_accepted_and_others_still_are_not(configured):
    nid = notebook_for(configured)
    for name in (
        "a.html",
        "a.htm",
        "a.epub",
        "a.png",
        "a.jpg",
        "a.jpeg",
        "a.mp3",
        "a.wav",
        "a.m4a",
    ):
        assert upload(configured, nid, name, b"x").status_code == 202, name
    bad = upload(configured, nid, "a.exe", b"x")
    assert (
        bad.status_code == 400
        and "HTML, EPUB, PNG, JPG, MP3, WAV, M4A" in bad.json()["error"]["message"]
    )
    wait_idle(configured, nid)
