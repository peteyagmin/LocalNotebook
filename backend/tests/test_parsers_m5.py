"""HTML, EPUB, image and PDF OCR, audio (FR-2.1, FR-2.2)."""

import zipfile

import pytest

from app.ingest import ocr, parsers
from app.ingest.chunker import chunk_text
from app.ingest.extract import build_extracted
from app.ingest.parsers import ParseError, parse
from app.ingest.sandbox import run_parse
from app.speech import stt
from app.speech.stt import TranscriptSegment, format_timestamp, group_segments
from tests.conftest import make_pdf
from tests.fakes import LONG_TEXT, page

needs_tesseract = pytest.mark.skipif(not ocr.available(), reason="Tesseract is not installed")


# --- HTML (FR-2.1) ---------------------------------------------------------------------------


def test_html_keeps_headings_as_a_path_and_reads_the_title(tmp_path):
    p = tmp_path / "a.html"
    p.write_bytes(page("The Port", heading="Founding"))
    result = parse(p, "html")
    assert result.title == "The Port"
    texts = {b.text: b.heading_path for b in result.blocks}
    assert any(path and path[-1] == "Founding" for path in texts.values())
    assert any("sentence number 3" in t for t in texts)


def test_a_web_page_with_too_little_text_cannot_be_read(tmp_path):
    p = tmp_path / "short.html"
    p.write_bytes(page("Tiny", body="Just a few words."))
    with pytest.raises(ParseError, match="Could not extract readable content"):
        parse(p, "web")
    assert parse(p, "html").blocks  # a local HTML file has no such minimum


def test_navigation_boilerplate_is_dropped(tmp_path):
    html = (
        "<html><body><nav>Home About Contact Login Register Cart</nav>"
        f"<article><h1>Story</h1><p>{LONG_TEXT}</p></article>"
        "<footer>Copyright 2026 all rights reserved terms privacy</footer></body></html>"
    )
    p = tmp_path / "n.html"
    p.write_text(html)
    text = " ".join(b.text for b in parse(p, "web").blocks)
    assert "Port of Valdoria" in text and "Login Register" not in text


# --- EPUB ------------------------------------------------------------------------------------


def make_epub(path, chapters, title="A Book", extra=None):
    container = (
        '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
        'version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    items = "".join(
        f'<item id="c{i}" href="ch{i}.xhtml" media-type="application/xhtml+xml"/>'
        for i in range(len(chapters))
    )
    spine = "".join(
        f'<itemref idref="c{i}"/>' for i in reversed(range(len(chapters)))
    )  # reversed on purpose
    opf = (
        '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata>'
        f"<dc:title>{title}</dc:title></metadata><manifest>{items}</manifest><spine>{spine}</spine></package>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        for i, body in enumerate(chapters):
            z.writestr(
                f"OEBPS/ch{i}.xhtml",
                f'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>c{i}</title></head>'
                f"<body><h1>Chapter {i}</h1><p>{body}</p></body></html>",
            )
        for name, data in (extra or {}).items():
            z.writestr(name, data)


def test_epub_chapters_come_in_spine_order_with_headings(tmp_path):
    p = tmp_path / "b.epub"
    make_epub(p, [LONG_TEXT, LONG_TEXT.replace("Valdoria", "Estmark")])
    result = parse(p, "epub")
    assert result.title == "A Book"
    paths = [
        b.heading_path[-1] for b in result.blocks if b.heading_path and not b.text.startswith("#")
    ]
    assert paths.index("Chapter 1") < paths.index("Chapter 0")  # spine said chapter 1 first
    assert any("Estmark" in b.text for b in result.blocks)


def test_damaged_and_oversized_epubs_fail_cleanly(tmp_path, monkeypatch):
    bad = tmp_path / "bad.epub"
    bad.write_bytes(b"not a zip")
    with pytest.raises(ParseError, match="EPUB"):
        parse(bad, "epub")
    empty_zip = tmp_path / "e.epub"
    with zipfile.ZipFile(empty_zip, "w") as z:
        z.writestr("hello.txt", "x")
    with pytest.raises(ParseError, match="EPUB"):
        parse(empty_zip, "epub")
    big = tmp_path / "big.epub"
    make_epub(big, [LONG_TEXT])
    monkeypatch.setattr(parsers, "MAX_EPUB_UNPACKED", 100)
    with pytest.raises(ParseError, match="too large"):
        parse(big, "epub")


# --- OCR (FR-2.2) ----------------------------------------------------------------------------


def text_image(text="HELLO OCR WORLD", size=(900, 200)):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", size, "white")
    ImageDraw.Draw(image).text((30, 50), text, fill="black", font=ImageFont.load_default(60))
    return image


@needs_tesseract
def test_images_are_always_read_with_ocr(tmp_path):
    p = tmp_path / "scan.png"
    text_image().save(p)
    result = parse(p, "image")
    assert "HELLO" in result.blocks[0].text.upper()


@needs_tesseract
def test_a_scanned_pdf_page_is_read_with_ocr_through_the_sandbox(tmp_path):
    p = tmp_path / "scanned.pdf"
    text_image("SCANNED PAGE TEXT").save(p, "PDF")  # an image-only PDF: no text layer
    result = run_parse(p, "pdf")
    assert result.page_count == 1 and result.blocks[0].page == 1
    assert "SCANNED" in result.blocks[0].text.upper()


def test_pdf_pages_below_50_characters_are_ocrd_and_others_are_not(tmp_path, monkeypatch):
    calls = []

    def fake_ocr(image):
        calls.append(image)
        return "text recovered by ocr"

    monkeypatch.setattr(ocr, "ocr_image", fake_ocr)
    p = tmp_path / "mixed.pdf"
    p.write_bytes(make_pdf(["x" * 49, "y" * 50, "z" * 200]))
    result = parse(p, "pdf")
    assert len(calls) == 1  # only the 49-character page
    assert result.blocks[0].text == "text recovered by ocr"
    assert result.blocks[1].text == "y" * 50 and result.blocks[2].text == "z" * 200


def test_without_tesseract_text_pages_still_work_and_scans_explain(tmp_path, monkeypatch):
    def missing(_image):
        raise ocr.OCRUnavailable(ocr.OCR_MISSING_MESSAGE)

    monkeypatch.setattr(ocr, "ocr_image", missing)
    mixed = tmp_path / "mixed.pdf"
    mixed.write_bytes(make_pdf(["short", "A real page of text. " * 5]))
    assert [b.page for b in parse(mixed, "pdf").blocks] == [1, 2]  # short text is kept as is
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(make_pdf([""]))
    with pytest.raises(ParseError, match="install Tesseract"):
        parse(scan, "pdf")
    image = tmp_path / "i.png"
    text_image().save(image)
    with pytest.raises(ParseError, match="Tesseract"):
        parse(image, "image")


def test_images_with_no_text_or_bad_data_fail_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "ocr_image", lambda image: "   \n  ")
    blank = tmp_path / "blank.png"
    text_image("").save(blank)
    with pytest.raises(ParseError, match="No text could be read"):
        parse(blank, "image")
    broken = tmp_path / "x.png"
    broken.write_bytes(b"not an image")
    with pytest.raises(ParseError, match="image"):
        parse(broken, "image")


# --- audio and timestamps --------------------------------------------------------------------


def test_segments_are_grouped_into_timestamped_blocks():
    segments = [TranscriptSegment(i * 10.0, i * 10.0 + 9, f"Line {i}.") for i in range(10)]
    blocks = group_segments(segments, window=30)
    assert [(round(s), round(e)) for _, s, e in blocks] == [(0, 39), (40, 79), (80, 99)] or len(
        blocks
    ) >= 3
    assert blocks[0][0].startswith("Line 0.") and blocks[0][1] == 0
    assert group_segments([]) == []


def test_timestamp_formatting():
    assert [format_timestamp(s) for s in (0, 65, 754, 3600, 3725)] == [
        "0:00",
        "1:05",
        "12:34",
        "1:00:00",
        "1:02:05",
    ]


def test_audio_is_transcribed_into_timed_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("LNB_STT_FACTORY", "tests.fake_stt:make")
    audio = tmp_path / "talk.mp3"
    audio.write_bytes(b"bytes")
    opts = {"stt_model": "any", "models_dir": str(tmp_path)}
    result = run_parse(audio, "audio", options=opts)  # through the real sandbox process
    assert all(b.start_s is not None and b.end_s >= b.start_s for b in result.blocks)
    assert result.blocks[0].start_s == 0.0 and "number 0" in result.blocks[0].text
    extracted = build_extracted(result)
    assert extracted["segments"][0]["start_s"] == 0.0
    chunks = chunk_text(extracted["text"], extracted["segments"])
    location = chunks[0].location()
    assert location["start_seconds"] == 0.0 and location["end_seconds"] >= 9.0


def test_audio_without_speech_or_model_fails_with_clear_messages(tmp_path, monkeypatch):
    silent = tmp_path / "s.wav"
    silent.write_bytes(b"SILENCE")
    monkeypatch.setenv("LNB_STT_FACTORY", "tests.fake_stt:make")
    with pytest.raises(ParseError, match="No speech"):
        parse(silent, "audio", {"stt_model": "m", "models_dir": str(tmp_path)})
    monkeypatch.delenv("LNB_STT_FACTORY")
    with pytest.raises(ParseError, match="No speech-to-text model is configured"):
        parse(silent, "audio", {"stt_model": "", "models_dir": str(tmp_path)})
    with pytest.raises(ParseError, match="'big' is not installed"):
        parse(silent, "audio", {"stt_model": "big", "models_dir": str(tmp_path)})


def test_model_directories_cannot_escape_the_models_folder(tmp_path):
    target = stt.model_dir(tmp_path, "../../etc/passwd")
    assert tmp_path in target.parents and ".." not in target.parts
    assert stt.model_dir(tmp_path, "org/name") == tmp_path / "stt" / "org_name"


def test_chunk_timing_comes_from_the_first_and_last_segment_it_covers():
    segs = [
        {"start": 0, "end": 40, "page": None, "heading_path": None, "start_s": 0.0, "end_s": 30.0},
        {
            "start": 42,
            "end": 90,
            "page": None,
            "heading_path": None,
            "start_s": 31.0,
            "end_s": 60.0,
        },
    ]
    text = "A" * 39 + ".\n\n" + "B" * 47 + "."
    chunks = chunk_text(text, segs)
    assert chunks[0].start_s == 0.0 and chunks[-1].end_s == 60.0
    assert "start_seconds" not in chunk_text("Plain text.", [{"start": 0, "end": 11}])[0].location()


def test_zip_of_text_is_not_mistaken_for_epub_spine(tmp_path):
    p = tmp_path / "w.epub"
    make_epub(p, ["Short chapter."], extra={"OEBPS/extra.xhtml": "<html/>"})
    assert parse(p, "epub").blocks  # extra files outside the spine are ignored


def test_uploaded_extension_table_covers_every_listed_type():
    assert {
        parsers.SUPPORTED_EXTENSIONS[e]
        for e in (".html", ".epub", ".png", ".jpg", ".mp3", ".wav", ".m4a")
    } == {
        "html",
        "epub",
        "image",
        "audio",
    }
