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
    ".html": "html",
    ".htm": "html",
    ".epub": "epub",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
}
PDF_OCR_MIN_CHARS = 50  # a PDF page with less text than this is read with OCR (FR-2.2)
WEB_MIN_CHARS = 200  # a web page yielding less than this could not be read (FR-2.9)
MAX_EPUB_UNPACKED = 200 * 1024 * 1024
MAX_IMAGE_PIXELS = 100_000_000


class ParseError(Exception):
    """The file could not be read. The message is user-readable."""


@dataclass
class Block:
    text: str
    page: int | None = None
    heading_path: list[str] | None = None
    start_s: float | None = None  # audio and video: where this text starts, in seconds
    end_s: float | None = None


@dataclass
class ParseResult:
    blocks: list[Block] = field(default_factory=list)
    page_count: int | None = None
    title: str | None = None


def _paragraph_blocks(text: str) -> list[Block]:
    return [Block(p) for p in re.split(r"\n\s*\n", normalize(text)) if p.strip()]


def parse_txt(path: Path) -> ParseResult:
    return ParseResult(_paragraph_blocks(decode_bytes(path.read_bytes())))


_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def markdown_blocks(text: str) -> list[Block]:
    """Paragraph blocks; each heading line is its own block and updates the heading path."""
    blocks: list[Block] = []
    path_stack: list[str] = []
    paragraph: list[str] = []
    in_fence = False

    def flush() -> None:
        if paragraph:
            blocks.append(Block("\n".join(paragraph), heading_path=list(path_stack) or None))
            paragraph.clear()

    for line in normalize(text).split("\n"):
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
    return blocks


def parse_md(path: Path) -> ParseResult:
    return ParseResult(markdown_blocks(decode_bytes(path.read_bytes())))


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

    from app.ingest.ocr import OCRUnavailable, ocr_image

    try:
        pdf = pdfium.PdfDocument(str(path))
    except Exception as e:
        raise ParseError("Could not read this PDF. It may be damaged or password-protected.") from e
    blocks: list[Block] = []
    ocr_missing = False
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
                text = unwrap(normalize(raw))
                if len(text) < PDF_OCR_MIN_CHARS and not ocr_missing:
                    try:
                        scanned = ocr_image(page.render(scale=2).to_pil())
                    except OCRUnavailable:
                        ocr_missing = True
                    else:
                        text = unwrap(normalize(scanned)) if scanned.strip() else text
            finally:
                page.close()
            if text:
                blocks.append(Block(text, page=index + 1))
    finally:
        pdf.close()
    if not blocks and ocr_missing:
        raise ParseError(
            "No readable text was found. If this is a scanned document, install Tesseract "
            "so it can be read with OCR."
        )
    return ParseResult(blocks, page_count=page_count)


def _html_to_markdown(data: bytes) -> tuple[str, str | None]:
    import trafilatura

    text = trafilatura.extract(
        data, output_format="markdown", include_comments=False, include_tables=True
    )
    meta = trafilatura.extract_metadata(data)
    return text or "", (meta.title if meta and meta.title else None)


def parse_html(path: Path, min_chars: int = 1) -> ParseResult:
    text, title = _html_to_markdown(path.read_bytes())
    if len(text.strip()) < min_chars:
        raise ParseError("Could not extract readable content from this page.")
    return ParseResult(markdown_blocks(text), title=title)


def parse_web(path: Path) -> ParseResult:
    return parse_html(path, min_chars=WEB_MIN_CHARS)


def _chapter_title(xhtml: bytes) -> str | None:
    from lxml import etree, html

    try:
        tree = html.fromstring(xhtml)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        return None
    for expression in ("//h1", "//h2", "//title"):
        for node in tree.xpath(expression):
            text = " ".join(node.text_content().split())
            if text:
                return text
    return None


def parse_epub(path: Path) -> ParseResult:
    """An EPUB is a ZIP of XHTML chapters; read them in spine order with the HTML extractor."""
    import posixpath
    import zipfile

    from defusedxml import ElementTree

    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise ParseError("Could not read this EPUB. It may be damaged.") from e
    with archive:
        infos = archive.infolist()
        if sum(i.file_size for i in infos) > MAX_EPUB_UNPACKED or len(infos) > 20_000:
            raise ParseError("This EPUB is too large to read safely.")
        try:
            container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
            rootfile = next(e for e in container.iter() if e.tag.endswith("rootfile"))
            opf_path = rootfile.attrib["full-path"]
            opf = ElementTree.fromstring(archive.read(opf_path))
        except (KeyError, StopIteration, ElementTree.ParseError) as e:
            raise ParseError("Could not read this EPUB. It may be damaged.") from e
        base = posixpath.dirname(opf_path)
        manifest = {
            e.attrib["id"]: e.attrib["href"]
            for e in opf.iter()
            if e.tag.endswith("}item") and "id" in e.attrib and "href" in e.attrib
        }
        spine = [e.attrib["idref"] for e in opf.iter() if e.tag.endswith("}itemref")]
        title = next((e.text for e in opf.iter() if e.tag.endswith("}title") and e.text), None)
        blocks: list[Block] = []
        for idref in spine:
            href = manifest.get(idref)
            if not href:
                continue
            name = posixpath.normpath(posixpath.join(base, href.split("#")[0]))
            if not name.lower().endswith((".xhtml", ".html", ".htm", ".xml")):
                continue
            try:
                chapter = archive.read(name)
            except KeyError:
                continue
            text, _ = _html_to_markdown(chapter)
            heading = _chapter_title(chapter)
            if heading and not any(
                line.lstrip("# ").strip().lower() == heading.lower()
                for line in text.split("\n")[:3]
            ):
                text = f"# {heading}\n\n{text}"  # the extractor drops a chapter's own title
            blocks += markdown_blocks(text)
    return ParseResult(blocks, title=title.strip() if title else None)


def parse_image(path: Path) -> ParseResult:
    from PIL import Image, ImageOps

    from app.ingest.ocr import OCRUnavailable, ocr_image

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
    except Exception as e:
        raise ParseError("Could not read this image. It may be damaged.") from e
    try:
        text = ocr_image(image)
    except OCRUnavailable as e:
        raise ParseError(str(e)) from e
    blocks = _paragraph_blocks(text)
    if not blocks:
        raise ParseError("No text could be read from this image.")
    return ParseResult(blocks)


def parse_audio(path: Path, options: dict) -> ParseResult:
    from pathlib import Path as _Path

    from app.speech.stt import STTUnavailable, create_engine, group_segments

    try:
        engine = create_engine(options.get("stt_model", ""), _Path(options["models_dir"]))
    except STTUnavailable as e:
        raise ParseError(str(e)) from e
    segments = engine.transcribe(path)
    blocks = [
        Block(text, start_s=start, end_s=end) for text, start, end in group_segments(segments)
    ]
    if not blocks:
        raise ParseError("No speech was found in this recording.")
    return ParseResult(blocks)


_PARSERS = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "txt": parse_txt,
    "text": parse_txt,  # pasted text
    "md": parse_md,
    "html": parse_html,
    "web": parse_web,
    "epub": parse_epub,
    "image": parse_image,
}


def parse(path: Path, source_type: str, options: dict | None = None) -> ParseResult:
    if source_type == "audio":
        result = parse_audio(path, options or {})
    else:
        result = _PARSERS[source_type](path)
    if not any(b.text.strip() for b in result.blocks):
        raise ParseError("No readable text was found in this file.")
    return result
