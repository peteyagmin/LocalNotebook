import re

from app.ingest.chunker import OVERLAP_TOKENS, TARGET_TOKENS, chunk_text, est_tokens


def sentences(n, prefix="Sentence"):
    return " ".join(f"{prefix} number {i} has a few words in it." for i in range(n))


def seg(start, end, page=None, heading=None):
    return {"start": start, "end": end, "page": page, "heading_path": heading}


def test_empty_text():
    assert chunk_text("", []) == []


def test_short_text_is_one_chunk():
    text = "One sentence. Another sentence."
    chunks = chunk_text(text, [seg(0, len(text), page=3)])
    assert len(chunks) == 1
    assert chunks[0].text == text and chunks[0].page == 3 and chunks[0].ordinal == 0


def test_offsets_slice_back_to_text():
    text = sentences(200)
    for c in chunk_text(text, [seg(0, len(text))]):
        assert text[c.char_start : c.char_end] == c.text


def test_chunks_respect_target_and_end_on_sentence_boundaries():
    text = sentences(300)
    chunks = chunk_text(text, [seg(0, len(text))])
    assert len(chunks) > 1
    for c in chunks:
        assert est_tokens(len(c.text)) <= TARGET_TOKENS
        assert c.text.endswith(".") and c.text.startswith("Sentence")


def test_overlap_is_whole_sentences_within_budget():
    text = sentences(300)
    chunks = chunk_text(text, [seg(0, len(text))])
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        assert nxt.char_start < prev.char_end  # they overlap
        overlap = text[nxt.char_start : prev.char_end]
        assert est_tokens(len(overlap)) <= OVERLAP_TOKENS
        assert overlap.startswith("Sentence")  # starts on a sentence boundary
    assert chunks[1].char_start > chunks[0].char_start  # always makes progress


def test_prefers_paragraph_boundary():
    para = sentences(30)  # ~ 300 tokens
    text = "\n\n".join([para, para, para])
    chunks = chunk_text(text, [seg(0, len(text))])
    first_end = text.index("\n\n")
    assert chunks[0].char_end == first_end or chunks[0].char_end == text.index(
        "\n\n", first_end + 2
    )


def test_oversized_sentence_is_split_without_losing_text():
    long_sentence = " ".join(f"word{i}" for i in range(2000)) + "."
    chunks = chunk_text(long_sentence, [seg(0, len(long_sentence))])
    assert len(chunks) > 1
    for c in chunks:
        assert est_tokens(len(c.text)) <= TARGET_TOKENS
    covered = " ".join(c.text for c in chunks)
    assert "word0" in covered and "word1999." in covered


def test_short_sentences_not_split_mid_sentence():
    text = sentences(100)
    chunks = chunk_text(text, [seg(0, len(text))])
    for c in chunks:
        assert re.fullmatch(r"(Sentence number \d+ has a few words in it\.\s?)+", c.text)


def test_location_comes_from_segment_at_chunk_start():
    a, b = sentences(120, "Alpha"), sentences(120, "Beta")
    text = a + "\n\n" + b
    segs = [
        seg(0, len(a), page=1, heading=["A"]),
        seg(len(a) + 2, len(text), page=2, heading=["B"]),
    ]
    chunks = chunk_text(text, segs)
    assert chunks[0].page == 1 and chunks[0].heading_path == ["A"]
    assert chunks[-1].page == 2 and chunks[-1].heading_path == ["B"]
    assert chunks[0].location()["char_start"] == chunks[0].char_start
