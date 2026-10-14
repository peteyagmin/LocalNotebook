"""Draw a mind map as a PNG with Pillow (FR-5.11). The whole tree is shown expanded."""

from __future__ import annotations

import io
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_FILES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]
FILLS = ["#1d4ed8", "#2563eb", "#dbeafe", "#eff6ff"]
TEXT = ["#ffffff", "#ffffff", "#1e293b", "#1e293b"]
PAD_X, PAD_Y, GAP_X, GAP_Y, MARGIN = 14, 8, 56, 12, 32
WRAP_CHARS = 26


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for path in FONT_FILES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


class _Box:
    def __init__(self, node: dict, depth: int, font):
        self.depth = depth
        self.lines = textwrap.wrap(node["label"], WRAP_CHARS) or [node["label"]]
        widths = [font.getlength(line) for line in self.lines]
        self.line_h = font.getbbox("Ag")[3] + 4
        self.w = int(max(widths)) + 2 * PAD_X
        self.h = self.line_h * len(self.lines) + 2 * PAD_Y
        self.children = [_Box(c, depth + 1, font) for c in node["children"]]
        self.x = self.y = 0  # top-left, set by layout


def _layout(root: _Box) -> tuple[int, int]:
    col_w: dict[int, int] = {}

    def widths(b: _Box) -> None:
        col_w[b.depth] = max(col_w.get(b.depth, 0), b.w)
        for c in b.children:
            widths(c)

    widths(root)
    col_x = {}
    x = MARGIN
    for depth in sorted(col_w):
        col_x[depth] = x
        x += col_w[depth] + GAP_X
    cursor = [MARGIN]

    def place(b: _Box) -> None:
        b.x = col_x[b.depth]
        if not b.children:
            b.y = cursor[0]
            cursor[0] += b.h + GAP_Y
            return
        for c in b.children:
            place(c)
        mid = (b.children[0].y + b.children[0].h / 2 + b.children[-1].y + b.children[-1].h / 2) / 2
        b.y = int(mid - b.h / 2)

    place(root)
    return x - GAP_X + MARGIN, cursor[0] - GAP_Y + MARGIN


def render_png(title: str, data: dict) -> bytes:
    font = _font(15)
    root = _Box(data["root"], 0, font)
    width, height = _layout(root)
    image = Image.new("RGB", (max(width, 200), max(height, 120)), "white")
    draw = ImageDraw.Draw(image)

    def edges(b: _Box) -> None:
        for c in b.children:
            x1, y1 = b.x + b.w, b.y + b.h / 2
            x2, y2 = c.x, c.y + c.h / 2
            mid = (x1 + x2) / 2
            draw.line([(x1, y1), (mid, y1), (mid, y2), (x2, y2)], fill="#94a3b8", width=2)
            edges(c)

    def boxes(b: _Box) -> None:
        level = min(b.depth, len(FILLS) - 1)
        draw.rounded_rectangle(
            [b.x, b.y, b.x + b.w, b.y + b.h], radius=8, fill=FILLS[level], outline="#3b82f6"
        )
        for i, line in enumerate(b.lines):
            draw.text((b.x + PAD_X, b.y + PAD_Y + i * b.line_h), line, fill=TEXT[level], font=font)
        for c in b.children:
            boxes(c)

    edges(root)
    boxes(root)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()
