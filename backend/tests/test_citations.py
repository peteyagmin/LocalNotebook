from app.chat.citations import CitationFilter, strip_citations


def run(chunks, valid):
    f = CitationFilter(set(valid))
    out = "".join(f.feed(c) for c in chunks) + f.flush()
    return out, f.used


def test_valid_labels_kept_invalid_dropped():
    assert run(["Cats purr [1] and sleep [9]."], [1, 2]) == ("Cats purr [1] and sleep.", [1])


def test_comma_lists_are_normalized_and_filtered():
    assert run(["Both [1, 3] agree [2, 7]."], [1, 2, 3]) == ("Both [1][3] agree [2].", [1, 3, 2])


def test_markers_split_across_stream_chunks():
    pieces = ["Fact [", "1", "] and [", "9", "] done", " [2", ", 1] end"]
    assert run(pieces, [1, 2]) == ("Fact [1] and done [2][1] end", [1, 2])


def test_streaming_equals_one_shot():
    text = "A [1] b [2, 5] c [x] d [3] e [10] f."
    one, used = run([text], [1, 2, 3])
    for size in (1, 2, 3, 5):
        pieces = [text[i : i + size] for i in range(0, len(text), size)]
        assert run(pieces, [1, 2, 3]) == (one, used)


def test_non_citation_brackets_survive():
    assert run(["see [note] and [", "ab", "c]"], [1]) == (
        "see [note] and [abc]",
        [],
    )


def test_trailing_partial_marker_flushed_as_text():
    assert run(["end ["], [1]) == ("end [", [])


def test_dropped_marker_before_punctuation_leaves_no_stray_space():
    assert run(["Claim [9]. Next"], [1])[0] == "Claim. Next"


def test_strip_citations():
    assert strip_citations("One [1] two [2, 3][4]. Three") == "One two. Three"
