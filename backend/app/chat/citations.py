"""Citation handling for model output (FR-3.2).

Models cite with [n] labels. Only labels that were actually supplied survive; anything else is
dropped. The same filter runs while streaming, so the stored text equals what the user saw.
"""

from __future__ import annotations

import re

_MARKER = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
_PARTIAL = re.compile(r"\[[\d,\s]*")
_MAX_MARKER_LEN = 24
_NO_SPACE_BEFORE = ".,;:!?)"


class CitationFilter:
    def __init__(self, valid: set[int]):
        self.valid = valid
        self.used: list[int] = []  # labels in order of first appearance
        self._pending = ""
        self._held_space = ""
        self._space_owed = ""

    def _emit_plain(self, text: str, out: list[str]) -> None:
        if not text:
            return
        if self._space_owed:
            if text[0] not in _NO_SPACE_BEFORE and not text[0].isspace():
                out.append(self._space_owed)
            self._space_owed = ""
        out.append(text)

    def _push(self, text: str, out: list[str]) -> None:
        """Emit text, holding trailing spaces back until we know what follows them."""
        stripped = text.rstrip(" ")
        trailing = text[len(stripped) :]
        if stripped:
            self._emit_plain(self._held_space + stripped, out)
            self._held_space = trailing
        else:
            self._held_space += trailing

    def feed(self, text: str) -> str:
        buf = self._pending + text
        self._pending = ""
        out: list[str] = []
        i = 0
        while i < len(buf):
            start = buf.find("[", i)
            if start == -1:
                self._push(buf[i:], out)
                break
            self._push(buf[i:start], out)
            match = _MARKER.match(buf, start)
            if match:
                labels = []
                for n in (int(x) for x in re.split(r"\s*,\s*", match.group(1).strip())):
                    if n in self.valid and n not in labels:
                        labels.append(n)
                for n in labels:
                    if n not in self.used:
                        self.used.append(n)
                if labels:
                    out.append(self._held_space + "".join(f"[{n}]" for n in labels))
                else:
                    self._space_owed = self._held_space
                self._held_space = ""
                i = match.end()
                continue
            rest = buf[start:]
            if _PARTIAL.fullmatch(rest) and len(rest) < _MAX_MARKER_LEN:
                self._pending = rest  # might still become a marker
                break
            self._emit_plain(self._held_space + "[", out)
            self._held_space = ""
            i = start + 1
        return "".join(out)

    def flush(self) -> str:
        out: list[str] = []
        self._emit_plain(self._held_space + self._pending, out)
        self._held_space = self._pending = self._space_owed = ""
        return "".join(out)


def strip_citations(text: str) -> str:
    """Remove [n] markers (used when replaying earlier answers as chat history)."""
    return re.sub(r"\s*\[\d+(?:\s*,\s*\d+)*\]", "", text)
