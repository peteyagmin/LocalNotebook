"""The outside world as seen by ingestion, so tests can substitute it."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.ingest import safe_fetch
from app.ingest.discover import SearchProvider, make_searxng
from app.ingest.youtube import RealYouTube, YouTubeBackend
from app.speech.tts import TTSEngine, create_engine

Fetcher = Callable[[str], Awaitable[safe_fetch.FetchResult]]
ProviderFactory = Callable[[dict], SearchProvider | None]
TTSFactory = Callable[[dict, Path], TTSEngine]


@dataclass
class Services:
    models_dir: Path
    fetch: Fetcher = safe_fetch.fetch
    check_url: Callable[[str], Awaitable[None]] = safe_fetch.check_url
    youtube: YouTubeBackend = field(default_factory=RealYouTube)
    search_provider: ProviderFactory = make_searxng
    tts: TTSFactory = create_engine
