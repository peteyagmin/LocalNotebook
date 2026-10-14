"""Assemble parser blocks into the normalized `extracted.json` document (DR-3)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.ingest.parsers import ParseResult

SEPARATOR = "\n\n"


def build_extracted(result: ParseResult) -> dict:
    """Full text plus segments: {start, end, page, heading_path} spans over that text."""
    parts: list[str] = []
    segments: list[dict] = []
    pos = 0
    for block in result.blocks:
        text = block.text.strip()
        if not text:
            continue
        if parts:
            pos += len(SEPARATOR)
        segments.append(
            {
                "start": pos,
                "end": pos + len(text),
                "page": block.page,
                "heading_path": block.heading_path,
                "start_s": block.start_s,
                "end_s": block.end_s,
            }
        )
        parts.append(text)
        pos += len(text)
    return {
        "version": 1,
        "text": SEPARATOR.join(parts),
        "segments": segments,
        "page_count": result.page_count,
    }


def write_extracted(path: Path, extracted: dict) -> None:
    """Atomic write so a crash never leaves a half-written file (DR-6)."""
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(extracted, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def read_extracted(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
