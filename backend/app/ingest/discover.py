"""Discover sources (FR-2.11): search -> fetch and extract candidates -> model ranks them.
Nothing is imported here; the user picks what to import."""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import BaseModel, field_validator

from app.ingest.parsers import _html_to_markdown
from app.ingest.safe_fetch import FetchError, FetchResult
from app.ingest.youtube import is_youtube_url
from app.llm.base import LLMClient
from app.llm.prompts import render_prompt
from app.llm.structured import generate_json

MAX_RESULTS = 30
MAX_SUGGESTIONS = 10
CANDIDATE_TIMEOUT_S = 15.0
PARALLEL_FETCHES = 8
EXCERPT_CHARS = 700
MIN_CANDIDATE_CHARS = 200


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str = ""


class SearchProvider(Protocol):
    async def search(self, query: str, limit: int) -> list[SearchHit]: ...


class SearxngProvider:
    """A SearXNG instance the user runs themselves (its JSON output must be enabled)."""

    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None):
        self._base = base_url.rstrip("/")
        self._transport = transport

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        try:
            async with httpx.AsyncClient(timeout=20, transport=self._transport) as client:
                response = await client.get(
                    f"{self._base}/search", params={"q": query, "format": "json"}
                )
                response.raise_for_status()
                results = response.json().get("results", [])
        except (httpx.HTTPError, ValueError) as e:
            raise FetchError(
                "Could not get results from the search provider. Check its address in Settings "
                "and that it allows JSON output."
            ) from e
        hits = []
        for item in results:
            if item.get("url"):
                hits.append(
                    SearchHit(
                        title=str(item.get("title") or item["url"]),
                        url=item["url"],
                        snippet=str(item.get("content") or ""),
                    )
                )
        return hits[:limit]


def make_searxng(settings: dict) -> SearchProvider | None:
    url = (settings.get("searxng_url") or "").strip()
    return SearxngProvider(url) if url else None


class _Ranked(BaseModel):
    index: int
    note: str

    @field_validator("note")
    @classmethod
    def _note(cls, v: str) -> str:
        return " ".join(v.split())


class _Ranking(BaseModel):
    results: list[_Ranked]


@dataclass
class Candidate:
    title: str
    url: str
    excerpt: str
    kind: str  # web | youtube


async def _load_candidate(hit: SearchHit, fetch, semaphore: asyncio.Semaphore) -> Candidate | None:
    if is_youtube_url(hit.url):
        text = " ".join(hit.snippet.split())
        return Candidate(hit.title, hit.url, text[:EXCERPT_CHARS], "youtube") if text else None
    async with semaphore:
        try:
            result: FetchResult = await asyncio.wait_for(fetch(hit.url), CANDIDATE_TIMEOUT_S)
            text, title = await asyncio.wait_for(
                asyncio.to_thread(_html_to_markdown, result.content), CANDIDATE_TIMEOUT_S
            )
        except Exception:  # unreachable, unsafe, too slow, or unreadable: not a candidate
            return None
    text = " ".join(text.split())
    if len(text) < MIN_CANDIDATE_CHARS:
        return None
    return Candidate(title or hit.title, hit.url, text[:EXCERPT_CHARS], "web")


async def discover(
    topic: str,
    provider: SearchProvider,
    fetch,
    llm: LLMClient,
    model: str,
) -> list[dict]:
    """Up to 10 suggestions: [{title, url, note, kind}], most relevant first."""
    hits = await provider.search(topic, MAX_RESULTS)
    seen: set[str] = set()
    unique = [h for h in hits if not (h.url in seen or seen.add(h.url))]
    semaphore = asyncio.Semaphore(PARALLEL_FETCHES)
    loaded = await asyncio.gather(*(_load_candidate(h, fetch, semaphore) for h in unique))
    candidates = [c for c in loaded if c is not None]
    if not candidates:
        return []

    nonce = secrets.token_hex(8)
    listing = "\n\n".join(
        f"[{i}] {c.title}\n{c.url}\n{c.excerpt}" for i, c in enumerate(candidates, start=1)
    )
    prompt = render_prompt(
        "discover_rank",
        topic=topic,
        open=f"<<<CANDIDATES {nonce}>>>",
        close=f"<<<END CANDIDATES {nonce}>>>",
        candidates=listing,
        limit=str(MAX_SUGGESTIONS),
    )
    ranking = await generate_json(llm, model, [{"role": "user", "content": prompt}], _Ranking)
    suggestions: list[dict] = []
    used: set[int] = set()
    for item in ranking.results:
        if 1 <= item.index <= len(candidates) and item.index not in used:
            used.add(item.index)
            c = candidates[item.index - 1]
            suggestions.append({"title": c.title, "url": c.url, "note": item.note, "kind": c.kind})
        if len(suggestions) == MAX_SUGGESTIONS:
            break
    return suggestions
