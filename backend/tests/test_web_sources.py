"""Web pages, YouTube, refresh, and the network toggles (FR-2.9, FR-2.10, FR-2.12, FR-8.6)."""

import json

import pytest

from app.ingest import youtube
from app.ingest.safe_fetch import FetchError
from app.ingest.youtube import Captions
from app.llm.fake import FakeLLMClient
from tests.conftest import wait_idle
from tests.fakes import (
    VIDEO_INFO,
    FakeWeb,
    FakeYouTube,
    caption_lines,
    make_services,
    page,
)
from tests.helpers import brain

NB = "/api/v1/notebooks"


def setup(make_client, tmp_path, web=None, yt=None, **settings):
    services = make_services(tmp_path, web=web, youtube=yt)
    client = make_client(FakeLLMClient(default_reply=brain), services=services)
    client.put("/api/v1/settings", json={"chat_model": "c", "embedding_model": "e", **settings})
    nid = client.post(NB, json={"name": "NB"}).json()["id"]
    return client, nid, services


def urls(client, nid, *addresses, headers=None):
    return client.post(
        f"{NB}/{nid}/sources/urls", json={"urls": list(addresses)}, headers=headers or {}
    )


# --- web pages (FR-2.9, FR-2.12) -------------------------------------------------------------


def test_pages_are_fetched_once_extracted_and_described(make_client, tmp_path):
    web = FakeWeb(
        {
            "https://a.example/port": page("The Port of Valdoria"),
            "https://b.example/x": page("Second"),
        }
    )
    client, nid, _ = setup(make_client, tmp_path, web)
    r = urls(client, nid, "https://a.example/port", "https://b.example/x")
    assert r.status_code == 202 and [s["type"] for s in r.json()] == ["web", "web"]
    sources = wait_idle(client, nid)
    first = sources[0]
    assert first["state"] == "ready" and first["name"] == "The Port of Valdoria"
    assert (
        first["url"] == "https://a.example/port" and first["fetched_at"]
    )  # origin and capture date
    assert first["meta"]["title"] == "The Port of Valdoria"
    assert web.fetched.count("https://a.example/port") == 1  # fetched once
    content = client.get(f"{NB}/{nid}/sources/{first['id']}/content").json()
    assert "sentence number 3" in content["text"]
    folder = tmp_path / "notebooks" / nid / "sources" / first["id"]
    assert (folder / "original.html").exists()


def test_a_page_with_too_little_text_fails_with_the_right_message(make_client, tmp_path):
    web = FakeWeb({"https://a.example/short": page("Tiny", body="Hello.")})
    client, nid, _ = setup(make_client, tmp_path, web)
    urls(client, nid, "https://a.example/short")
    s = wait_idle(client, nid)[0]
    assert s["state"] == "failed" and "Could not extract readable content" in s["error"]


def test_fetch_errors_are_reported_and_retry_refetches(make_client, tmp_path):
    web = FakeWeb({"https://a.example/p": FetchError("The website took too long to respond.")})
    client, nid, _ = setup(make_client, tmp_path, web)
    urls(client, nid, "https://a.example/p")
    s = wait_idle(client, nid)[0]
    assert s["state"] == "failed" and "too long" in s["error"]
    web.pages["https://a.example/p"] = page("Recovered")
    client.post(f"{NB}/{nid}/sources/{s['id']}/retry")
    assert wait_idle(client, nid)[0]["state"] == "ready"
    assert web.fetched.count("https://a.example/p") == 2


@pytest.mark.parametrize(
    "bad",
    [
        "http://127.0.0.1:8000/api",
        "http://localhost/",
        "http://10.0.0.5/x",
        "file:///etc/passwd",
        "ftp://x.example/",
    ],
)
def test_private_and_non_web_addresses_are_refused_before_anything_is_created(
    make_client, tmp_path, bad
):
    web = FakeWeb({"https://ok.example/": page("Fine")})
    client, nid, _ = setup(make_client, tmp_path, web)
    r = urls(client, nid, "https://ok.example/", bad)
    assert r.status_code == 400 and r.json()["error"]["code"] == "unsafe_url"
    assert client.get(f"{NB}/{nid}/sources").json() == [] and web.fetched == []


def test_the_real_url_check_refuses_names_that_resolve_inside(make_client, tmp_path):
    """No fake: the production check, with name resolution stubbed to a private address."""
    from app.ingest import safe_fetch
    from app.ingest.services import Services

    async def inside(host):
        return ["192.168.1.20"]

    async def check(url):
        await safe_fetch.check_url(url, inside)

    client = make_client(
        FakeLLMClient(default_reply=brain), services=Services(models_dir=tmp_path, check_url=check)
    )
    nid = client.post(NB, json={"name": "NB"}).json()["id"]
    r = urls(client, nid, "http://sneaky.example/")
    assert r.status_code == 400 and "local network" in r.json()["error"]["message"]


def test_web_import_can_be_turned_off(make_client, tmp_path):
    client, nid, _ = setup(make_client, tmp_path, allow_web_import=False)
    r = urls(client, nid, "https://a.example/")
    assert r.status_code == 403 and r.json()["error"]["code"] == "network_disabled"


def test_import_respects_the_source_limit_and_dedupes(make_client, tmp_path):
    web = FakeWeb({"https://a.example/1": page("One"), "https://a.example/2": page("Two")})
    client, nid, _ = setup(make_client, tmp_path, web, max_sources_per_notebook=1)
    r = urls(client, nid, "https://a.example/1", "https://a.example/2")
    assert r.status_code == 400 and r.json()["error"]["code"] == "source_limit"
    client.put("/api/v1/settings", json={"max_sources_per_notebook": 5})
    assert (
        len(
            urls(
                client, nid, "https://a.example/1", "https://a.example/1\n", " https://a.example/1 "
            ).json()
        )
        == 1
    )


def test_web_sources_work_offline_after_import(make_client, tmp_path):
    """SR-5: once imported, no network is needed to chat or view."""
    web = FakeWeb({"https://a.example/p": page("Offline")})
    client, nid, _ = setup(make_client, tmp_path, web)
    urls(client, nid, "https://a.example/p")
    source = wait_idle(client, nid)[0]
    web.pages.clear()
    assert (
        "sentence number 1"
        in client.get(f"{NB}/{nid}/sources/{source['id']}/content").json()["text"]
    )
    assert client.get(f"{NB}/{nid}/search", params={"q": "valdoria"}).json()


# --- refresh creates a new version (FR-2.9) ---------------------------------


def test_refresh_keeps_the_previous_version_and_activates_the_new_one(make_client, tmp_path):
    web = FakeWeb(
        {"https://a.example/p": page("Edition One", body="The old text about harbors. " * 12)}
    )
    client, nid, _ = setup(make_client, tmp_path, web)
    urls(client, nid, "https://a.example/p")
    source = wait_idle(client, nid)[0]
    assert source["version_count"] == 0
    web.pages["https://a.example/p"] = page(
        "Edition Two", body="The brand new text about ships. " * 12
    )
    r = client.post(f"{NB}/{nid}/sources/{source['id']}/refresh")
    assert r.status_code == 202
    after = wait_idle(client, nid)[0]
    assert (
        after["state"] == "ready" and after["version_count"] == 1 and after["name"] == "Edition Two"
    )
    assert (
        "brand new text" in client.get(f"{NB}/{nid}/sources/{source['id']}/content").json()["text"]
    )
    old = tmp_path / "notebooks" / nid / "sources" / source["id"] / "versions" / "1"
    assert "old text about harbors" in json.loads((old / "extracted.json").read_text())["text"]
    assert b"Edition One" in (old / "original.html").read_bytes()
    # the index follows the active version
    hits = client.get(f"{NB}/{nid}/search", params={"q": "ships"}).json()
    assert hits and not client.get(f"{NB}/{nid}/search", params={"q": "harbors"}).json()[0:0]
    web.pages["https://a.example/p"] = page("Edition Three", body="Third text about tides. " * 12)
    client.post(f"{NB}/{nid}/sources/{source['id']}/refresh")
    assert wait_idle(client, nid)[0]["version_count"] == 2


def test_refresh_only_applies_to_web_sources_and_idle_ones(make_client, tmp_path):
    client, nid, _ = setup(make_client, tmp_path)
    text = client.post(
        f"{NB}/{nid}/sources/text", json={"name": "t", "text": "Hello there."}
    ).json()[0]
    wait_idle(client, nid)
    r = client.post(f"{NB}/{nid}/sources/{text['id']}/refresh")
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_refreshable"
    assert client.post(f"{NB}/{nid}/sources/nope/refresh").status_code == 404


def test_refresh_is_blocked_when_web_import_is_off(make_client, tmp_path):
    web = FakeWeb({"https://a.example/p": page("P")})
    client, nid, _ = setup(make_client, tmp_path, web)
    urls(client, nid, "https://a.example/p")
    source = wait_idle(client, nid)[0]
    client.put("/api/v1/settings", json={"allow_web_import": False})
    assert client.post(f"{NB}/{nid}/sources/{source['id']}/refresh").status_code == 403


# --- YouTube (FR-2.10) -----------------------------------------------------------------------

VIDEO = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
NO_CAPTIONS = (
    "This video has no captions. Enable 'Transcribe videos without captions' in Settings to "
    "transcribe it locally."
)


def test_captions_become_a_timestamped_source(make_client, tmp_path):
    yt = FakeYouTube(Captions(caption_lines(), "en", False), VIDEO_INFO)
    client, nid, _ = setup(make_client, tmp_path, yt=yt)
    r = urls(client, nid, "https://youtu.be/dQw4w9WgXcQ?t=5")  # any YouTube form
    assert r.json()[0]["type"] == "youtube" and r.json()[0]["url"] == VIDEO
    s = wait_idle(client, nid)[0]
    assert s["state"] == "ready" and s["name"] == "A Video About Harbors"
    assert s["meta"]["channel"] == "Harbor Channel" and s["meta"]["duration"] == 125.0
    assert s["meta"]["video_id"] == "dQw4w9WgXcQ" and s["meta"]["transcript"] == "captions"
    assert s["url"] == VIDEO and s["fetched_at"]
    content = client.get(f"{NB}/{nid}/sources/{s['id']}/content").json()
    assert content["segments"][0]["start_s"] == 0.0 and content["segments"][-1]["end_s"] > 90
    conn = client.app.state.store.open(nid)
    try:
        locations = [json.loads(r["location"]) for r in conn.execute("SELECT location FROM chunks")]
    finally:
        conn.close()
    assert (
        "start_seconds" in locations[0]
        and locations[0]["end_seconds"] > locations[0]["start_seconds"]
    )


def test_citations_to_videos_show_the_timestamp(make_client, tmp_path):
    from app.chat.service import describe_location

    assert describe_location({"start_seconds": 754.2, "end_seconds": 790}) == "12:34"
    assert describe_location({"page": 3}) == "page 3"


def test_metadata_failure_still_imports_the_transcript(make_client, tmp_path):
    yt = FakeYouTube(Captions(caption_lines(), "en", True), info=None)
    client, nid, _ = setup(make_client, tmp_path, yt=yt)
    urls(client, nid, VIDEO)
    s = wait_idle(client, nid)[0]
    assert s["state"] == "ready" and s["name"] == "YouTube video dQw4w9WgXcQ"


def test_a_video_without_captions_fails_with_the_exact_message_when_the_setting_is_off(
    make_client, tmp_path
):
    yt = FakeYouTube(None, VIDEO_INFO)
    client, nid, _ = setup(make_client, tmp_path, yt=yt)
    assert (
        client.get("/api/v1/settings").json()["transcribe_uncaptioned_videos"] is False
    )  # off by default
    urls(client, nid, VIDEO)
    s = wait_idle(client, nid)[0]
    assert s["state"] == "failed" and s["error"] == NO_CAPTIONS
    assert not any(call[0] == "download_audio" for call in yt.calls)  # nothing was downloaded


def test_a_video_without_captions_is_transcribed_locally_when_allowed(
    make_client, tmp_path, monkeypatch
):
    monkeypatch.setenv("LNB_STT_FACTORY", "tests.fake_stt:make")
    yt = FakeYouTube(None, VIDEO_INFO)
    client, nid, _ = setup(
        make_client, tmp_path, yt=yt, transcribe_uncaptioned_videos=True, stt_model="any"
    )
    urls(client, nid, VIDEO)
    s = wait_idle(client, nid)[0]
    assert s["state"] == "ready" and s["meta"]["transcript"] == "transcription"
    assert any(call[0] == "download_audio" for call in yt.calls)
    assert yt.audio_paths and not yt.audio_paths[0].exists()  # the audio is deleted afterwards
    assert not (tmp_path / "notebooks" / nid / "sources" / s["id"] / "audio_tmp").exists()
    content = client.get(f"{NB}/{nid}/sources/{s['id']}/content").json()
    assert (
        "Spoken sentence number 3" in content["text"] and content["segments"][0]["start_s"] == 0.0
    )


def test_local_transcription_needs_a_model_and_still_deletes_the_audio(make_client, tmp_path):
    yt = FakeYouTube(None, VIDEO_INFO)
    client, nid, _ = setup(make_client, tmp_path, yt=yt, transcribe_uncaptioned_videos=True)
    urls(client, nid, VIDEO)
    s = wait_idle(client, nid)[0]
    assert s["state"] == "failed" and "speech-to-text model" in s["error"]
    assert yt.audio_paths and not yt.audio_paths[0].exists()


def test_youtube_errors_and_non_video_addresses(make_client, tmp_path):
    class Blocked(FakeYouTube):
        def captions(self, video_id, languages):
            raise FetchError(
                "Could not read the video from YouTube. It may be private or unavailable."
            )

    client, nid, _ = setup(make_client, tmp_path, yt=Blocked(None, VIDEO_INFO))
    urls(client, nid, VIDEO)
    s = wait_idle(client, nid)[0]
    assert s["state"] == "failed" and "private or unavailable" in s["error"]
    r = urls(client, nid, "https://www.youtube.com/feed/subscriptions")
    assert r.status_code == 400 and "not a YouTube video" in r.json()["error"]["message"]


def test_the_browser_language_is_used_to_pick_captions(make_client, tmp_path):
    yt = FakeYouTube(Captions(caption_lines(), "de", False), VIDEO_INFO)
    client, nid, _ = setup(make_client, tmp_path, yt=yt)
    urls(client, nid, VIDEO, headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.5"})
    wait_idle(client, nid)
    asked = next(c for c in yt.calls if c[0] == "captions")
    assert asked[2][:2] == ["de-de", "de"]


def test_video_id_forms_and_rejections():
    ok = "dQw4w9WgXcQ"
    for url in (
        f"https://www.youtube.com/watch?v={ok}&t=3s",
        f"https://youtu.be/{ok}",
        f"https://m.youtube.com/watch?v={ok}",
        f"https://www.youtube.com/shorts/{ok}",
        f"https://www.youtube.com/embed/{ok}",
        f"http://music.youtube.com/watch?v={ok}",
    ):
        assert youtube.parse_video_id(url) == ok
    for url in (
        "https://evil.example/watch?v=" + ok,
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=short",
        "ftp://youtu.be/" + ok,
    ):
        with pytest.raises(Exception, match="not a YouTube|valid web"):
            youtube.parse_video_id(url)


def test_caption_preference_order():
    options = [("fr", False), ("en", True), ("en", False), ("de", True), ("fr", True)]
    # human-made in the UI language, then auto-generated in the UI language, then other languages
    assert youtube.rank_transcripts(options, ["en"]) == [2, 1, 0, 3, 4]
    assert youtube.rank_transcripts(options, ["fr", "en"])[:3] == [0, 4, 2]
    assert youtube.rank_transcripts([("en-GB", False), ("en", True)], ["en-us"]) == [0, 1]
    assert youtube.choose_language_order("de-DE,de;q=0.9,en;q=0.5,*;q=0.1") == ["de-de", "de", "en"]
    assert youtube.choose_language_order(None) == ["en"]


def test_captions_are_merged_into_half_minute_blocks():
    blocks = youtube.caption_blocks(caption_lines(20))  # 20 lines * 5 s = 100 s
    assert 3 <= len(blocks) <= 5 and blocks[0][1] == 0.0 and blocks[-1][2] > 90
