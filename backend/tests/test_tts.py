"""The Kokoro ONNX engine's moving parts, and the TTS model download API."""

import threading
import time

import numpy as np
import pytest

from app.speech import tts
from app.speech.tts import KokoroOnnxEngine, TTSUnavailable

API = "/api/v1"


class FakeInput:
    def __init__(self, name, type_, shape):
        self.name, self.type, self.shape = name, type_, shape


class FakeSession:
    """Stands in for onnxruntime: records what it was given, returns a ramp of samples."""

    def __init__(self, inputs=None):
        self.inputs = inputs or [
            FakeInput("input_ids", "tensor(int64)", [1, "n"]),
            FakeInput("style", "tensor(float)", [1, 256]),
            FakeInput("speed", "tensor(float)", [1]),
        ]
        self.feeds = []

    def get_inputs(self):
        return self.inputs

    def run(self, _outputs, feed):
        self.feeds.append(feed)
        return [np.linspace(-0.5, 0.5, 2400, dtype=np.float32).reshape(1, -1)]


VOCAB = {"h": 1, "ə": 2, "l": 3, "o": 4, "ʊ": 5, " ": 6, ".": 7}


def engine(tmp_path, session=None, phonemizer=lambda text, lang: "həloʊ"):
    folder = tmp_path / "model"
    (folder / "voices").mkdir(parents=True)
    table = np.arange(10 * 256, dtype=np.float32).reshape(10, 1, 256)
    table.tofile(folder / "voices" / "af_test.bin")
    return KokoroOnnxEngine(session or FakeSession(), VOCAB, folder, phonemizer), table


def test_text_becomes_tokens_and_the_style_row_matching_their_count(tmp_path):
    e, table = engine(tmp_path)
    audio = e.synthesize("Hello.", "af_test")
    feed = e._session.feeds[0]
    ids = feed["input_ids"]
    assert ids.dtype == np.int64 and ids.tolist() == [
        [0, 1, 2, 3, 4, 5, 0]
    ]  # padded with 0 at both ends
    assert np.array_equal(feed["style"], table[5])  # row = number of tokens, without the padding
    assert feed["speed"].tolist() == [1.0]
    assert audio.dtype == np.float32 and audio.size == 2400 and np.abs(audio).max() <= 1.0


def test_unknown_symbols_are_dropped_and_long_text_is_clipped(tmp_path):
    e, _ = engine(tmp_path, phonemizer=lambda text, lang: "h✗ə" + "l" * 800)
    e.synthesize("x.", "af_test")
    ids = e._session.feeds[0]["input_ids"][0]
    assert 99 not in ids and len(ids) == tts.MAX_TOKENS + 2


def test_sentences_are_spoken_separately_with_a_short_gap(tmp_path):
    e, _ = engine(tmp_path)
    audio = e.synthesize("One sentence. Another sentence! A third?", "af_test")
    assert len(e._session.feeds) == 3
    gap = int(tts.SAMPLE_RATE * tts.SENTENCE_PAUSE_S)
    assert audio.size == 3 * 2400 + 2 * gap


def test_input_names_are_discovered_not_assumed(tmp_path):
    session = FakeSession(
        [
            FakeInput("tokens", "tensor(int64)", [1, "n"]),
            FakeInput("speed", "tensor(int32)", [1]),
            FakeInput("style", "tensor(float)", [1, 256]),
        ]
    )
    e, _ = engine(tmp_path, session)
    e.synthesize("Hi.", "af_test")
    assert set(session.feeds[0]) == {"tokens", "style", "speed"}
    assert session.feeds[0]["speed"].dtype == np.int32


def test_a_missing_voice_or_empty_speech_is_explained(tmp_path):
    e, _ = engine(tmp_path)
    with pytest.raises(TTSUnavailable, match="voice 'nobody' is not installed"):
        e.synthesize("Hello.", "nobody")
    silent, _ = engine(tmp_path / "x", phonemizer=lambda text, lang: "✗✗")
    assert silent.synthesize("Hello.", "af_test").size == 0


def test_sentence_splitting_keeps_pieces_short_without_losing_words():
    long_sentence = ", ".join(f"word{i}" for i in range(80)) + "."
    pieces = tts.split_sentences(f"Short one. {long_sentence} Last?")
    assert pieces[0] == "Short one." and pieces[-1] == "Last?"
    assert all(len(p) <= 220 for p in pieces)
    assert " ".join(pieces[1:-1]).replace(", ", " ").replace(",", " ").count("word") == 80
    assert tts.split_sentences("   ") == []


def test_phonemes_come_from_the_espeak_program(monkeypatch):
    monkeypatch.setattr(
        tts.shutil, "which", lambda name: "/usr/bin/espeak-ng" if name == "espeak-ng" else None
    )
    seen = {}

    class Result:
        returncode, stdout = 0, "hɚ_ɹ\n ɐ͡b\n"

    def runner(cmd, **kwargs):
        seen["cmd"] = cmd
        return Result()

    assert (
        tts.phonemize("hello there", "en-gb", runner) == "həɹ ɹ əb"
    )  # joined, ties removed, fixes applied
    assert seen["cmd"] == ["/usr/bin/espeak-ng", "-q", "--ipa", "-v", "en-gb", "--", "hello there"]
    monkeypatch.setattr(tts.shutil, "which", lambda name: None)
    with pytest.raises(TTSUnavailable, match="espeak-ng is not installed"):
        tts.phonemize("hi", "en-us", runner)


def test_voices_pick_the_espeak_language():
    voices = ("af_heart", "bm_george", "ef_dora", "zf_xx", "qq")
    assert [tts.language_for_voice(v) for v in voices] == ["en-us", "en-gb", "es", "cmn", "en-us"]


def test_the_engine_factory_explains_every_missing_piece(tmp_path, monkeypatch):
    monkeypatch.delenv("LNB_TTS_FACTORY", raising=False)
    settings = {"tts_model": "", "tts_voice_a": "", "tts_voice_b": ""}
    with pytest.raises(TTSUnavailable, match="No text-to-speech model is configured"):
        tts.create_engine(settings, tmp_path)
    settings["tts_model"] = "org/tts"
    with pytest.raises(TTSUnavailable, match="voice for Host A and Host B"):
        tts.create_engine(settings, tmp_path)
    settings.update(tts_voice_a="va", tts_voice_b="vb")
    with pytest.raises(TTSUnavailable, match="not installed"):
        tts.create_engine(settings, tmp_path)
    folder = tts.tts_dir(tmp_path, "org/tts")
    (folder / "onnx").mkdir(parents=True)
    (folder / "voices").mkdir()
    (folder / "onnx" / "model.onnx").write_bytes(b"x")
    (folder / "tokenizer.json").write_text("{}")
    assert not tts.is_installed(tmp_path, "org/tts", ["va", "vb"])  # voices are still missing
    for voice in ("va", "vb"):
        (folder / "voices" / f"{voice}.bin").write_bytes(b"x")
    assert tts.is_installed(tmp_path, "org/tts", ["va", "vb"])
    monkeypatch.setattr(tts.shutil, "which", lambda name: None)
    with pytest.raises(TTSUnavailable, match="espeak-ng is not installed"):
        tts.create_engine(settings, tmp_path)


def test_the_factory_hook_swaps_the_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("LNB_TTS_FACTORY", "tests.fake_tts:make")
    assert tts.create_engine({}, tmp_path).sample_rate == 24000


def test_model_folders_cannot_escape_and_the_model_file_is_found(tmp_path):
    folder = tts.tts_dir(tmp_path, "../../etc")
    assert tmp_path in folder.parents and ".." not in folder.parts
    assert tts.model_file(folder) is None
    (folder / "nested").mkdir(parents=True)
    (folder / "nested" / "other.onnx").write_bytes(b"x")
    assert tts.model_file(folder).name == "other.onnx"
    (folder / "onnx").mkdir()
    (folder / "onnx" / "model.onnx").write_bytes(b"x")
    assert tts.model_file(folder).name == "model.onnx"  # the standard name wins


# --- downloads and status ---------------------------------------------------------------------


def writes_files(repo, target, report, extra):
    report(0.5)
    (target / "onnx").mkdir(parents=True, exist_ok=True)
    (target / "voices").mkdir(exist_ok=True)
    (target / "onnx" / "model.onnx").write_bytes(b"weights")
    (target / "tokenizer.json").write_text("{}")
    for voice in extra["voices"]:
        (target / "voices" / f"{voice}.bin").write_bytes(b"v")
    report(1.0)


def wait_tts(client, expect, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"{API}/speech/tts").json()
        if expect(status):
            return status
        time.sleep(0.02)
    raise AssertionError(f"never matched: {status}")


def configure(client, **extra):
    client.put(
        f"{API}/settings",
        json={"tts_model": "org/tts", "tts_voice_a": "va", "tts_voice_b": "vb", **extra},
    )


def test_status_download_and_installed(make_client, tmp_path, monkeypatch):
    monkeypatch.setattr(tts.shutil, "which", lambda name: f"/usr/bin/{name}")
    client = make_client(tts_downloader=writes_files)
    first = client.get(f"{API}/speech/tts").json()
    assert first["configured"] is False and first["installed"] is False and first["model"] == ""
    configure(client)
    status = client.get(f"{API}/speech/tts").json()
    assert status["configured"] and not status["installed"] and status["voices"] == ["va", "vb"]
    assert status["espeak"] is True and status["downloads_allowed"] is True
    assert (
        client.post(f"{API}/speech/tts/download", json={}).json()["error"]["code"]
        == "needs_confirmation"
    )
    assert client.post(f"{API}/speech/tts/download", json={"confirm": True}).status_code == 202
    done = wait_tts(client, lambda s: s["installed"])
    assert done["state"] == "idle"
    assert tts.is_installed(tmp_path / "models", "org/tts", ["va", "vb"])


def test_download_needs_a_model_voices_and_permission(make_client):
    client = make_client(tts_downloader=writes_files)
    assert (
        client.post(f"{API}/speech/tts/download", json={"confirm": True}).json()["error"]["code"]
        == "not_configured"
    )
    configure(client, allow_model_downloads=False)
    r = client.post(f"{API}/speech/tts/download", json={"confirm": True})
    assert r.status_code == 403 and r.json()["error"]["code"] == "network_disabled"


def test_a_download_that_lacks_the_expected_files_is_an_error_with_a_retry(make_client):
    attempts = []

    def wrong_repo(repo, target, report, extra):
        attempts.append(1)
        if len(attempts) > 1:
            return writes_files(repo, target, report, extra)
        (target / "readme.md").write_text("not a model")

    client = make_client(tts_downloader=wrong_repo)
    configure(client)
    client.post(f"{API}/speech/tts/download", json={"confirm": True})
    failed = wait_tts(client, lambda s: s["state"] == "error")
    assert "download failed" in failed["error"] and failed["installed"] is False
    client.post(f"{API}/speech/tts/download", json={"confirm": True})
    wait_tts(client, lambda s: s["installed"])


def test_adding_a_voice_downloads_only_what_is_needed(make_client, tmp_path):
    seen = []

    def record(repo, target, report, extra):
        seen.append(list(extra["voices"]))
        writes_files(repo, target, report, extra)

    client = make_client(tts_downloader=record)
    configure(client)
    client.post(f"{API}/speech/tts/download", json={"confirm": True})
    wait_tts(client, lambda s: s["installed"])
    configure(client, tts_voice_b="vc")  # a new voice: the model is there, the voice is not
    assert client.get(f"{API}/speech/tts").json()["installed"] is False
    client.post(f"{API}/speech/tts/download", json={"confirm": True})
    wait_tts(client, lambda s: s["installed"])
    assert seen == [["va", "vb"], ["va", "vc"]]
    assert (
        tts.tts_dir(tmp_path / "models", "org/tts") / "voices" / "va.bin"
    ).exists()  # nothing was removed


def test_progress_is_reported_while_downloading(make_client):
    release, started = threading.Event(), threading.Event()

    def slow(repo, target, report, extra):
        report(0.4)
        started.set()
        release.wait(10)
        writes_files(repo, target, report, extra)

    client = make_client(tts_downloader=slow)
    configure(client)
    client.post(f"{API}/speech/tts/download", json={"confirm": True})
    assert started.wait(5)
    mid = wait_tts(client, lambda s: s["state"] == "downloading" and s["progress"] == 0.4)
    assert mid["installed"] is False
    release.set()
    wait_tts(client, lambda s: s["installed"])


def test_capabilities_list_what_an_audio_overview_still_needs(make_client, monkeypatch):
    monkeypatch.setattr(tts.shutil, "which", lambda name: None)
    client = make_client(tts_downloader=writes_files)
    caps = client.get(f"{API}/capabilities").json()["audio_overview"]
    assert caps["ready"] is False
    assert any("chat model" in p for p in caps["problems"]) and any(
        "text-to-speech model" in p for p in caps["problems"]
    )
    assert any("espeak-ng" in p for p in caps["problems"]) and any(
        "ffmpeg" in p for p in caps["problems"]
    )
    monkeypatch.setattr(tts.shutil, "which", lambda name: f"/usr/bin/{name}")
    import app.api.speech as speech_api

    monkeypatch.setattr(speech_api.shutil, "which", lambda name: f"/usr/bin/{name}")
    configure(client, chat_model="c")
    caps = client.get(f"{API}/capabilities").json()["audio_overview"]
    assert caps["problems"] == ["Download the text-to-speech model and voices in Settings."]
    client.post(f"{API}/speech/tts/download", json={"confirm": True})
    wait_tts(client, lambda s: s["installed"])
    assert client.get(f"{API}/capabilities").json()["audio_overview"] == {
        "ready": True,
        "problems": [],
    }
