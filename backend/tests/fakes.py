"""Fakes for the outside world: web fetching, YouTube, and the search provider."""

import asyncio
import math
import time
from pathlib import Path

import numpy as np

from app.ingest import safe_fetch
from app.ingest.discover import SearchHit
from app.ingest.services import Services
from app.ingest.youtube import CaptionLine, Captions, VideoInfo
from app.speech.tts import create_engine

LONG_TEXT = " ".join(
    f"This sentence number {i} explains something useful about the Port of Valdoria."
    for i in range(12)
)


def page(title: str, body: str = LONG_TEXT, heading: str = "History") -> bytes:
    return (
        f"<html><head><title>{title}</title></head><body><article><h1>{title}</h1>"
        f"<h2>{heading}</h2><p>{body}</p><p>{body}</p></article></body></html>"
    ).encode()


class FakeWeb:
    """url -> HTML bytes (or an exception to raise). Records what was fetched."""

    def __init__(self, pages: dict[str, bytes | Exception] | None = None):
        self.pages = pages or {}
        self.fetched: list[str] = []

    async def fetch(self, url: str) -> safe_fetch.FetchResult:
        self.fetched.append(url)
        value = self.pages.get(url)
        if value is None:
            raise safe_fetch.FetchError("The website returned an error (HTTP 404).")
        if isinstance(value, Exception):
            raise value
        return safe_fetch.FetchResult(url, value, "text/html")


class FakeYouTube:
    def __init__(self, captions: Captions | None = None, info: VideoInfo | None = None):
        self.caps = captions
        self.info = info
        self.calls: list[tuple] = []
        self.audio_paths: list[Path] = []

    def metadata(self, url: str, video_id: str) -> VideoInfo:
        self.calls.append(("metadata", video_id))
        if self.info is None:
            raise safe_fetch.FetchError("no details")
        return self.info

    def captions(self, video_id: str, languages: list[str]) -> Captions | None:
        self.calls.append(("captions", video_id, languages))
        return self.caps

    def download_audio(self, url: str, folder: Path) -> Path:
        self.calls.append(("download_audio", url))
        path = folder / "audio.m4a"
        path.write_bytes(b"fake audio bytes")
        self.audio_paths.append(path)
        return path


def caption_lines(count: int = 20) -> list[CaptionLine]:
    return [CaptionLine(i * 5.0, 4.5, f"Caption line {i} about the harbor.") for i in range(count)]


VIDEO_INFO = VideoInfo(
    video_id="dQw4w9WgXcQ",
    title="A Video About Harbors",
    channel="Harbor Channel",
    description="All about harbors.",
    duration=125.0,
    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
)


class FakeProvider:
    def __init__(self, hits: list[SearchHit]):
        self.hits = hits
        self.queries: list[tuple[str, int]] = []

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        self.queries.append((query, limit))
        return self.hits[:limit]


class FakeTTS:
    """A tone per turn, as long as the text is: 10 ms per character, 220 Hz for voice "...a"."""

    sample_rate = 24000

    def __init__(self, seconds_per_char: float = 0.01, delay: float = 0.0):
        self.seconds_per_char = seconds_per_char
        self.delay = delay
        self.calls: list[tuple[str, str]] = []

    def synthesize(self, text: str, voice: str) -> np.ndarray:
        self.calls.append((text, voice))
        if self.delay:
            time.sleep(self.delay)
        count = int(self.sample_rate * max(0.2, len(text) * self.seconds_per_char))
        t = np.arange(count) / self.sample_rate
        tone = 220 if voice.endswith("a") else 330
        return (0.3 * np.sin(2 * math.pi * tone * t)).astype(np.float32)


def make_services(
    tmp_path: Path, web: FakeWeb | None = None, youtube=None, provider=None, tts=None
) -> Services:
    web = web or FakeWeb()

    async def accept(url: str) -> None:  # real syntax rules, but no DNS in tests
        safe_fetch.check_syntax(url)

    return Services(
        models_dir=tmp_path / "models",
        fetch=web.fetch,
        check_url=accept,
        youtube=youtube or FakeYouTube(),
        search_provider=lambda settings: provider,
        tts=(lambda settings, models_dir: tts) if tts is not None else create_engine,
    )


async def sleep_forever(_url: str):
    await asyncio.Event().wait()
