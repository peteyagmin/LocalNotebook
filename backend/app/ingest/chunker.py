"""Split extracted text into ~500-token chunks with ~80-token overlap (FR-2.3).

Rules:
- Boundaries fall on sentence ends; a chunk prefers to end at a paragraph boundary when that
  still fills at least half the target.
- A sentence is never split unless that single sentence exceeds the target size.
- Overlap is made of whole trailing sentences, at most OVERLAP_TOKENS in total.
Tokens are estimated as characters / 4; no tokenizer dependency.
"""

from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass

TARGET_TOKENS = 500
OVERLAP_TOKENS = 80
CHARS_PER_TOKEN = 4

_SENTENCE = re.compile(r"""\S.*?(?:[.!?]+["')\]]*(?=\s)|\Z)""", re.DOTALL)


def est_tokens(char_count: int) -> int:
    return max(1, math.ceil(char_count / CHARS_PER_TOKEN))


@dataclass
class Chunk:
    ordinal: int
    text: str
    char_start: int
    char_end: int
    page: int | None
    heading_path: list[str] | None
    start_s: float | None = None
    end_s: float | None = None

    def location(self) -> dict:
        location = {
            "page": self.page,
            "heading_path": self.heading_path,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }
        if self.start_s is not None:
            location["start_seconds"] = self.start_s
            location["end_seconds"] = self.end_s
        return location


@dataclass
class _Unit:
    start: int
    end: int
    para_end: bool


def _split_long(text: str, start: int, end: int, limit: int) -> list[tuple[int, int]]:
    """Break one oversized sentence at whitespace (hard cut if there is none)."""
    pieces = []
    pos = start
    while end - pos > limit:
        cut = text.rfind(" ", pos, pos + limit)
        cut = cut if cut > pos else pos + limit
        pieces.append((pos, cut))
        pos = cut
        while pos < end and text[pos].isspace():
            pos += 1
    pieces.append((pos, end))
    return pieces


def _units(text: str) -> list[_Unit]:
    limit_chars = TARGET_TOKENS * CHARS_PER_TOKEN
    units: list[_Unit] = []
    offset = 0
    for paragraph in text.split("\n\n"):
        sentences = [(offset + m.start(), offset + m.end()) for m in _SENTENCE.finditer(paragraph)]
        offset += len(paragraph) + 2
        spans: list[tuple[int, int]] = []
        for s, e in sentences:
            if e - s > limit_chars:
                spans.extend(_split_long(text, s, e, limit_chars))
            else:
                spans.append((s, e))
        for i, (s, e) in enumerate(spans):
            units.append(_Unit(s, e, para_end=i == len(spans) - 1))
    return units


def chunk_text(text: str, segments: list[dict]) -> list[Chunk]:
    units = _units(text)
    seg_starts = [s["start"] for s in segments]
    chunks: list[Chunk] = []
    i, n = 0, len(units)
    while i < n:
        j, last_para = i, None
        while j < n:
            if j > i and est_tokens(units[j].end - units[i].start) > TARGET_TOKENS:
                break
            j += 1
            if units[j - 1].para_end:
                last_para = j
        if (
            j < n
            and last_para
            and last_para > i
            and est_tokens(units[last_para - 1].end - units[i].start) >= TARGET_TOKENS / 2
        ):
            j = last_para
        start, end = units[i].start, units[j - 1].end
        seg = segments[max(0, bisect.bisect_right(seg_starts, start) - 1)] if segments else {}
        last = segments[max(0, bisect.bisect_right(seg_starts, end - 1) - 1)] if segments else {}
        chunks.append(
            Chunk(
                ordinal=len(chunks),
                text=text[start:end],
                char_start=start,
                char_end=end,
                page=seg.get("page"),
                heading_path=seg.get("heading_path"),
                start_s=seg.get("start_s"),
                end_s=last.get("end_s"),
            )
        )
        if j >= n:
            break
        k = j
        while k - 1 > i and est_tokens(units[j - 1].end - units[k - 1].start) <= OVERLAP_TOKENS:
            k -= 1
        i = k
    return chunks
