"""YouTube import (FR-2.10): captions via youtube-transcript-api, metadata via yt-dlp, and, only
when the user allows it, audio download for local transcription."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

from app.ingest.safe_fetch import FetchError, UnsafeURL

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
_VIDEO_ID = re.compile(r"^[\w-]{11}$")

NO_CAPTIONS_MESSAGE = (
    "This video has no captions. Enable 'Transcribe videos without captions' in Settings to "
    "transcribe it locally."
)


@dataclass
class CaptionLine:
    start: float
    duration: float
    text: str


@dataclass
class Captions:
    lines: list[CaptionLine]
    language: str
    generated: bool


@dataclass
class VideoInfo:
    video_id: str
    title: str
    channel: str = ""
    description: str = ""
    duration: float | None = None
    url: str = ""
    extra: dict = field(default_factory=dict)


class YouTubeBackend(Protocol):
    def metadata(self, url: str, video_id: str) -> VideoInfo: ...

    def captions(self, video_id: str, languages: list[str]) -> Captions | None: ...

    def download_audio(self, url: str, folder: Path) -> Path: ...


def is_youtube_url(url: str) -> bool:
    try:
        return (urlsplit(url.strip()).hostname or "").lower() in YOUTUBE_HOSTS
    except ValueError:
        return False


def parse_video_id(url: str) -> str:
    """The 11-character video id, or UnsafeURL if this is not a YouTube video address."""
    try:
        parts = urlsplit(url.strip())
    except ValueError as e:
        raise UnsafeURL(f"'{url}' is not a valid web address.") from e
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or host not in YOUTUBE_HOSTS:
        raise UnsafeURL(f"'{url}' is not a YouTube video address.")
    candidate = None
    if host == "youtu.be":
        candidate = parts.path.strip("/").split("/")[0]
    elif parts.path == "/watch":
        candidate = (parse_qs(parts.query).get("v") or [""])[0]
    else:
        match = re.match(r"^/(?:shorts|embed|live|v)/([\w-]{11})", parts.path)
        candidate = match.group(1) if match else None
    if not candidate or not _VIDEO_ID.match(candidate):
        raise UnsafeURL(f"'{url}' is not a YouTube video address.")
    return candidate


def choose_language_order(accept_language: str | None) -> list[str]:
    """Language codes from an Accept-Language header, best first (the UI language, FR-2.10)."""
    codes: list[tuple[float, str]] = []
    for part in (accept_language or "en").split(","):
        piece = part.strip()
        if not piece:
            continue
        code, _, q = piece.partition(";q=")
        try:
            weight = float(q) if q else 1.0
        except ValueError:
            weight = 0.0
        if code != "*":
            codes.append((weight, code.lower()))
    ordered = [c for _, c in sorted(codes, key=lambda x: -x[0])]
    return ordered or ["en"]


def rank_transcripts(available: list[tuple[str, bool]], languages: list[str]) -> list[int]:
    """Indices of (language_code, is_generated) options, best first: human-made in the UI
    language, auto-generated in the UI language, then the same two for other languages."""

    def matches(code: str) -> int | None:
        for i, wanted in enumerate(languages):
            if code.lower() == wanted or code.lower().split("-")[0] == wanted.split("-")[0]:
                return i
        return None

    def key(item: tuple[int, tuple[str, bool]]):
        _, (code, generated) = item
        rank = matches(code)
        return (rank is None, rank if rank is not None else 0, generated)

    return [i for i, _ in sorted(enumerate(available), key=key)]


class RealYouTube:
    """Talks to YouTube through the libraries; network calls happen only here."""

    def metadata(self, url: str, video_id: str) -> VideoInfo:
        import yt_dlp

        options = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False
                )
        except Exception as e:
            raise FetchError("Could not read the video's details from YouTube.") from e
        return VideoInfo(
            video_id=video_id,
            title=info.get("title") or f"YouTube video {video_id}",
            channel=info.get("channel") or info.get("uploader") or "",
            description=info.get("description") or "",
            duration=info.get("duration"),
            url=f"https://www.youtube.com/watch?v={video_id}",
        )

    def captions(self, video_id: str, languages: list[str]) -> Captions | None:
        from youtube_transcript_api import (
            NoTranscriptFound,
            TranscriptsDisabled,
            YouTubeTranscriptApi,
        )
        from youtube_transcript_api._errors import YouTubeTranscriptApiException

        api = YouTubeTranscriptApi()
        try:
            transcripts = list(api.list(video_id))
        except (TranscriptsDisabled, NoTranscriptFound):
            return None
        except YouTubeTranscriptApiException as e:
            raise FetchError(
                "Could not read the video from YouTube. It may be private or unavailable."
            ) from e
        if not transcripts:
            return None
        order = rank_transcripts(
            [(t.language_code, t.is_generated) for t in transcripts], languages
        )
        chosen = transcripts[order[0]]
        try:
            fetched = chosen.fetch()
        except YouTubeTranscriptApiException as e:
            raise FetchError("Could not download the captions from YouTube.") from e
        lines = [CaptionLine(s.start, s.duration, s.text) for s in fetched]
        return Captions(lines, chosen.language_code, chosen.is_generated)

    def download_audio(self, url: str, folder: Path) -> Path:
        import yt_dlp

        video_id = parse_video_id(url)
        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bestaudio/best",
            "outtmpl": str(folder / f"{video_id}.%(ext)s"),
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        except Exception as e:
            raise FetchError("Could not download the video's audio from YouTube.") from e
        files = sorted(folder.glob(f"{video_id}.*"))
        if not files:
            raise FetchError("Could not download the video's audio from YouTube.")
        return files[0]


def caption_blocks(
    lines: list[CaptionLine], window: float = 30.0
) -> list[tuple[str, float, float]]:
    """Merge caption lines into ~30 second blocks: [(text, start, end)]."""
    from app.speech.stt import TranscriptSegment, group_segments

    segments = [
        TranscriptSegment(line.start, line.start + line.duration, " ".join(line.text.split()))
        for line in lines
        if line.text.strip()
    ]
    return group_segments(segments, window)
