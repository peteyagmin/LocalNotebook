"""Format parsers. Each returns blocks of text with location metadata (FR-2.1, FR-2.3).

Parsers run inside the sandbox worker (see sandbox.py). They never touch the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.ingest.normalize import decode_bytes, normalize, unwrap

SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
}


class ParseError(Exception):
    """The file could not be read. The message is user-readable."""


@dataclass
class Block:
    text: str
    page: int | None = None
    heading_path: list[str] | None = None


@dataclass
class ParseResult:
    blocks: list[Block] = field(default_factory=list)
    page_count: int | None = None


def _paragraph_blocks(text: str) -> list[Block]:
    return [Block(p) for p in re.split(r"\n\s*\n", normalize(text)) if p.strip()]


def parse_txt(path: Path) -> ParseResult:
    return ParseResult(_paragraph_blocks(decode_bytes(path.read_bytes())))


_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def parse_md(path: Path) -> ParseResult:
    """Paragraph blocks; each heading line is its own block and updates the heading path."""
    text = normalize(decode_bytes(path.read_bytes()))
    blocks: list[Block] = []
    path_stack: list[str] = []
    paragraph: list[str] = []
    in_fence = False

    def flush() -> None:
        if paragraph:
            blocks.append(Block("\n".join(paragraph), heading_path=list(path_stack) or None))
            paragraph.clear()

    for line in text.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            del path_stack[level - 1 :]
            path_stack.append(heading.group(2).strip())
            blocks.append(Block(line.strip(), heading_path=list(path_stack)))
        elif not line.strip() and not in_fence:
            flush()
        else:
            paragraph.append(line)
    flush()
    return ParseResult(blocks)


def parse_docx(path: Path) -> ParseResult:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(str(path))
    except Exception as e:
        raise ParseError("Could not read this Word document. It may be damaged.") from e

    blocks: list[Block] = []
    path_stack: list[str] = []
    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            text = normalize(item.text)
            if not text:
                continue
            style = (item.style.name if item.style is not None else "") or ""
            match = re.fullmatch(r"Heading (\d)", style)
            if match or style == "Title":
                level = int(match.group(1)) if match else 1
                del path_stack[level - 1 :]
                path_stack.append(text)
            blocks.append(Block(text, heading_path=list(path_stack) or None))
        elif isinstance(item, Table):
            rows = []
            for row in item.rows:
                cells = [normalize(c.text).replace("\n", " ") for c in row.cells]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                blocks.append(Block("\n".join(rows), heading_path=list(path_stack) or None))
    return ParseResult(blocks)


def parse_pdf(path: Path) -> ParseResult:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(str(path))
    except Exception as e:
        raise ParseError("Could not read this PDF. It may be damaged or password-protected.") from e
    blocks: list[Block] = []
    try:
        page_count = len(pdf)
        for index in range(page_count):
            page = pdf[index]
            try:
                textpage = page.get_textpage()
                try:
                    raw = textpage.get_text_range()
                finally:
                    textpage.close()
            finally:
                page.close()
            text = unwrap(normalize(raw))
            if text:
                blocks.append(Block(text, page=index + 1))
    finally:
        pdf.close()
    return ParseResult(blocks, page_count=page_count)


_PARSERS = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "txt": parse_txt,
    "text": parse_txt,  # pasted text
    "md": parse_md,
}


def parse(path: Path, source_type: str) -> ParseResult:
    result = _PARSERS[source_type](path)
    if not any(b.text.strip() for b in result.blocks):
        raise ParseError("No readable text was found in this file.")
    return result
