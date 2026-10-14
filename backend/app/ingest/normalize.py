"""Text normalization applied to every extracted block (FR-2.3)."""

from __future__ import annotations

import re
import unicodedata

_CONTROL = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")
_SPACE_RUN = re.compile(r"[ \t\f\v]+")
_NL_SPACES = re.compile(r" ?\n ?")
_BLANK_RUN = re.compile(r"\n{3,}")


def decode_bytes(data: bytes) -> str:
    """Decode uploaded text: BOM-aware, then UTF-8, then Windows-1252, then lossy UTF-8."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def normalize(text: str) -> str:
    """NFC, LF newlines, no control characters, collapsed whitespace, trimmed."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = _CONTROL.sub("", text)
    text = _SPACE_RUN.sub(" ", text)
    text = _NL_SPACES.sub("\n", text)
    return _BLANK_RUN.sub("\n\n", text).strip()


def unwrap(text: str) -> str:
    """Join hard-wrapped lines inside paragraphs (used for PDF page text)."""
    paragraphs = re.split(r"\n\s*\n", text)
    return "\n\n".join(re.sub(r"\s*\n\s*", " ", p).strip() for p in paragraphs if p.strip())
