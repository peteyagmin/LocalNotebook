import pytest

from app.ingest.extract import build_extracted
from app.ingest.normalize import decode_bytes, normalize, unwrap
from app.ingest.parsers import ParseError, parse
from app.ingest.sandbox import run_parse
from tests.conftest import make_docx, make_pdf


def test_normalize():
    assert normalize("a  b\t\tc\r\n\r\n\r\n\r\nd\x00 e  ") == "a b c\n\nd e"
    assert normalize("é") == "é"  # NFC


def test_unwrap_joins_lines_inside_paragraphs():
    assert unwrap("one\ntwo\n\nthree\nfour") == "one two\n\nthree four"


def test_decode_bytes():
    assert decode_bytes("héllo".encode()) == "héllo"
    assert decode_bytes("héllo".encode("cp1252")) == "héllo"
    assert decode_bytes("héllo".encode("utf-16")) == "héllo"
    assert decode_bytes(b"\xef\xbb\xbfhi") == "hi"


def test_txt_paragraphs(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("First para.\n\nSecond para.\n\n\n\nThird.", encoding="utf-8")
    assert [b.text for b in parse(p, "txt").blocks] == ["First para.", "Second para.", "Third."]


def test_markdown_heading_paths_and_fences(tmp_path):
    p = tmp_path / "a.md"
    p.write_text(
        "# Top\n\nIntro text.\n\n## Sub\n\nSub text.\n\n"
        "```\n# not a heading\n```\n\n# Next\n\nEnd.",
        encoding="utf-8",
    )
    blocks = parse(p, "md").blocks
    by_text = {b.text: b.heading_path for b in blocks}
    assert by_text["# Top"] == ["Top"]
    assert by_text["Intro text."] == ["Top"]
    assert by_text["Sub text."] == ["Top", "Sub"]
    assert by_text["```\n# not a heading\n```"] == ["Top", "Sub"]
    assert by_text["End."] == ["Next"]


def test_docx_headings_and_tables(tmp_path):
    p = tmp_path / "a.docx"
    make_docx(
        p,
        [
            ("Heading 1", "Chapter"),
            ("Normal", "Body one."),
            ("Heading 2", "Part"),
            ("Normal", "Body two."),
        ],
        table=[["a", "b"], ["c", "d"]],
    )
    blocks = parse(p, "docx").blocks
    by_text = {b.text: b.heading_path for b in blocks}
    assert by_text["Body one."] == ["Chapter"]
    assert by_text["Body two."] == ["Chapter", "Part"]
    assert by_text["a | b\nc | d"] == ["Chapter", "Part"]


def test_pdf_pages(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(make_pdf(["Hello page one.", "Second page here."]))
    result = parse(p, "pdf")
    assert result.page_count == 2
    assert [(b.page, b.text) for b in result.blocks] == [
        (1, "Hello page one."),
        (2, "Second page here."),
    ]


def test_empty_and_corrupt_inputs_fail_cleanly(tmp_path):
    empty = tmp_path / "e.txt"
    empty.write_text("   \n\n  ")
    with pytest.raises(ParseError, match="No readable text"):
        parse(empty, "txt")
    bad_pdf = tmp_path / "b.pdf"
    bad_pdf.write_bytes(b"not a pdf")
    with pytest.raises(ParseError):
        parse(bad_pdf, "pdf")
    bad_docx = tmp_path / "b.docx"
    bad_docx.write_bytes(b"not a docx")
    with pytest.raises(ParseError):
        parse(bad_docx, "docx")


def test_build_extracted_segments_index_the_text(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(make_pdf(["Alpha text.", "Beta text."]))
    ex = build_extracted(parse(p, "pdf"))
    for s in ex["segments"]:
        assert ex["text"][s["start"] : s["end"]] in ("Alpha text.", "Beta text.")
    assert [s["page"] for s in ex["segments"]] == [1, 2]


def test_sandbox_runs_parser_in_subprocess(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(make_pdf(["Sandboxed."]))
    assert run_parse(p, "pdf").blocks[0].text == "Sandboxed."


def test_sandbox_reports_parse_errors_and_timeouts(tmp_path):
    bad = tmp_path / "b.pdf"
    bad.write_bytes(b"junk")
    with pytest.raises(ParseError, match="Could not read this PDF"):
        run_parse(bad, "pdf")
    good = tmp_path / "g.txt"
    good.write_text("hello")
    with pytest.raises(ParseError, match="too long"):
        run_parse(good, "txt", timeout=0.0)
