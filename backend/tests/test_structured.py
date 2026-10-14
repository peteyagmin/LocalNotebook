import csv
import io
import json

import pytest

from app.llm.fake import FakeLLMClient
from app.studio import structured
from app.studio.mindmap_image import render_png
from tests.helpers import (
    NB,
    QUIZ,
    brain,
    generate,
    original_prompt,
    ready_notebook,
)


def detail(client, nid, a):
    return client.get(f"{NB}/{nid}/artifacts/{a['id']}").json()


def prompts(fake, needle):
    return [m for _, m in fake.calls if needle in m[-1]["content"]]


# --- timeline (FR-5.5) -----------------------------------------------------------------------


def test_timeline_is_sorted_cited_and_stripped_of_unsupported_items(make_client, tmp_path):
    client, fake, nid = ready_notebook(make_client)
    a = generate(client, nid, "timeline")
    assert a["state"] == "ready" and a["title"] == "Timeline"
    full = detail(client, nid, a)
    assert full["format"] == "json" and full["content"] == ""
    events = full["data"]["events"]
    # chronological, BCE first, partial dates before finer ones of the same year
    assert [e["iso_date"] for e in events] == ["-44", "1874", "1874-03", "1902"]
    assert all(e["sources"] and 99 not in e["sources"] for e in events)  # "Unsupported" dropped
    assert [m["name"] for m in full["data"]["cast"]] == ["Henrik Aldane"]  # "Ghost" dropped
    assert [c["label"] for c in full["citations"]] == [1]
    assert (tmp_path / "notebooks" / nid / "artifacts" / a["id"] / "content.json").exists()
    system = prompts(fake, "Extract a timeline")[-1][0]["content"]
    assert "JSON object only" in system and "untrusted data" in system


def test_timeline_with_no_dated_events_is_valid(make_client):
    empty = json.dumps({"events": [], "cast": []})

    def model(m, msgs):
        return empty if "Extract a timeline" in msgs[-1]["content"] else brain(m, msgs)

    client, _f, nid = ready_notebook(make_client, fake=FakeLLMClient(default_reply=model))
    a = generate(client, nid, "timeline")
    assert a["state"] == "ready" and detail(client, nid, a)["data"] == {"events": [], "cast": []}
    md = client.get(f"{NB}/{nid}/artifacts/{a['id']}/export", params={"format": "md"})
    assert "No dated events found." in md.content.decode()


# --- mind map (FR-5.6) -----------------------------------------------------------------------


def depth(node):
    return 1 + max([depth(c) for c in node["children"]], default=0)


def test_mind_map_depth_is_capped_at_four_levels(make_client):
    client, _f, nid = ready_notebook(make_client)
    a = generate(client, nid, "mind_map")
    root = detail(client, nid, a)["data"]["root"]
    assert root["label"] == "Zebras" and depth(root) == 4
    assert root["children"][0]["sources"] == [1]  # invented [99] removed
    assert "Way too deep" not in json.dumps(root)


def test_mind_map_is_trimmed_to_a_readable_size():
    def wide(level):
        kids = [] if level == 4 else [structured.MindNode(label=f"n{level}-{i}") for i in range(8)]
        for k in kids:
            k.children = wide(level + 1)
        return kids

    root = structured.MindNode(label="root", children=wide(2))
    data = structured.clean("mind_map", [structured.MindMap(root=root)], set())["root"]
    assert structured._count(data) <= structured.MIND_MAP_MAX_NODES and data["children"]


# --- flashcards and quiz (FR-5.7) ------------------------------------------------------------


def test_flashcards_and_quiz_are_two_validated_parts_of_one_artifact(make_client):
    client, fake, nid = ready_notebook(make_client)
    a = generate(client, nid, "flashcards")
    assert a["title"] == "Flashcards & quiz"
    data = detail(client, nid, a)["data"]
    assert len(data["flashcards"]) == 6 and "Unsupported" not in json.dumps(data["flashcards"])
    assert len(data["quiz"]) == 3  # a tiny notebook gets a short quiz (see the sizing tests below)
    q = data["quiz"][2]
    assert len(q["options"]) == 4 and q["correct_index"] == 2 and q["explanation"] and q["sources"]
    assert len(prompts(fake, "flashcards that help")) == 1
    assert len(prompts(fake, "multiple-choice questions")) == 1


# --- validation and retry (FR-5.10) ----------------------------------------------------------


BIG = {"big.txt": " ".join(f"Sentence number {i} is about zebras and herds." for i in range(400))}


def test_a_full_size_notebook_gets_the_full_ten_question_quiz(make_client):
    client, fake, nid = ready_notebook(make_client, BIG)
    client.put("/api/v1/settings", json={"context_window_tokens": 200_000})
    a = generate(client, nid, "flashcards")
    assert len(detail(client, nid, a)["data"]["quiz"]) == 10
    assert (
        "exactly 10 multiple-choice questions"
        in prompts(fake, "multiple-choice questions")[-1][-1]["content"]
    )
    assert "about 15 flashcards" in prompts(fake, "flashcards that help")[-1][-1]["content"]


def test_small_notebooks_get_shorter_quizzes_and_fewer_cards():
    sizes = {
        t: (structured.quiz_count(t), structured.flashcard_target(t))
        for t in (5, 300, 600, 900, 1500, 50_000)
    }
    assert sizes[5] == (3, 4)  # never fewer than 3 questions
    assert sizes[300] == (3, 5) and sizes[600] == (4, 10) and sizes[900] == (6, 15)
    assert sizes[1500] == (10, 15) and sizes[50_000] == (
        10,
        15,
    )  # the spec's 10 from 1500 tokens up


def test_the_requested_quiz_length_is_what_validation_enforces(make_client):
    short = json.dumps({"quiz": QUIZ["quiz"][:2]})  # asked for 3
    fake2 = scripted([short], "multiple-choice questions")
    client2, fake2, nid2 = ready_notebook(make_client, fake=fake2)
    assert generate(client2, nid2, "flashcards")["state"] == "ready"
    assert any("write exactly 3 questions" in m[-1]["content"] for _, m in fake2.calls)


def scripted(first_replies, key):
    """Model that returns `first_replies` in order for the `key` prompt, then the normal answer."""
    queue = list(first_replies)

    def model(m, msgs):
        if key in original_prompt(msgs) and queue:
            return queue.pop(0)
        return brain(m, msgs)

    return FakeLLMClient(default_reply=model)


def test_invalid_json_is_retried_with_the_validation_error(make_client):
    bad_schema = json.dumps({"events": [{"date": "x", "iso_date": "last Tuesday", "title": "t"}]})
    fake = scripted(["not json at all", bad_schema], "Extract a timeline")
    client, fake, nid = ready_notebook(make_client, fake=fake)
    a = generate(client, nid, "timeline")
    assert a["state"] == "ready"
    calls = prompts(fake, "Extract a timeline")
    assert len(calls) == 1  # the first prompt; retries append to a longer conversation
    retries = [
        m for _, m in fake.calls if m[0]["role"] == "system" and "not valid" in m[-1]["content"]
    ]
    assert len(retries) == 2
    assert "iso_date" in retries[1][-1]["content"]  # the validation error is quoted back


def test_three_invalid_answers_fail_with_a_clear_message(make_client):
    fake = scripted(["nope", "still nope", "nope again", "too late"], "Extract a timeline")
    client, _f, nid = ready_notebook(make_client, fake=fake)
    a = generate(client, nid, "timeline")
    assert a["state"] == "failed" and "did not return a valid answer" in a["error"]
    assert not a["has_content"]


def test_quiz_with_wrong_option_count_is_rejected_and_retried(make_client):
    broken = json.dumps({"quiz": [{**QUIZ["quiz"][0], "options": ["A", "B", "C"]}] * 10})
    fake = scripted([broken], "multiple-choice questions")
    client, fake, nid = ready_notebook(make_client, fake=fake)
    a = generate(client, nid, "flashcards")
    assert a["state"] == "ready"
    retry = [m for _, m in fake.calls if "exactly 4 non-empty options" in m[-1]["content"]]
    assert retry


def test_quiz_with_too_few_questions_is_retried(make_client):
    short = json.dumps({"quiz": QUIZ["quiz"][:4]})
    fake = scripted([short], "multiple-choice questions")
    client, fake, nid = ready_notebook(make_client, BIG, fake=fake)
    client.put("/api/v1/settings", json={"context_window_tokens": 200_000})
    assert generate(client, nid, "flashcards")["state"] == "ready"
    assert any("write exactly 10 questions" in m[-1]["content"] for _, m in fake.calls)


def test_nothing_supported_by_the_sources_fails(make_client):
    all_bad = json.dumps({"flashcards": [{"front": "a", "back": "b", "sources": [99]}] * 6})

    def model(m, msgs):
        return all_bad if "flashcards that help" in msgs[-1]["content"] else brain(m, msgs)

    client, _f, nid = ready_notebook(make_client, fake=FakeLLMClient(default_reply=model))
    a = generate(client, nid, "flashcards")
    assert a["state"] == "failed" and "nothing the sources support" in a["error"]


def test_structured_kinds_use_map_reduce_for_large_notebooks(make_client):
    texts = {
        f"d{i}.txt": " ".join(f"Sentence {i}-{j} about zebras." for j in range(120))
        for i in range(3)
    }
    client, fake, nid = ready_notebook(make_client, texts)
    client.put("/api/v1/settings", json={"context_window_tokens": 1000})
    a = generate(client, nid, "timeline")
    assert a["state"] == "ready"
    assert prompts(fake, "working notes")
    assert "Notes from part 1:" in prompts(fake, "Extract a timeline")[-1][-1]["content"]


# --- clean() ---------------------------------------------------------------------------------


def test_used_labels_and_sort_keys():
    assert structured.used_labels({"a": [{"sources": [3, 1]}, {"x": {"sources": [2]}}]}) == {
        1,
        2,
        3,
    }
    keys = [structured._date_key(d) for d in ["-44", "1874", "1874-03", "1874-03-14", "1900"]]
    assert keys == sorted(keys)


# --- exports (FR-5.11) -----------------------------------------------------------------------


def export(client, nid, a, fmt):
    return client.get(f"{NB}/{nid}/artifacts/{a['id']}/export", params={"format": fmt})


def test_timeline_exports(make_client):
    client, _f, nid = ready_notebook(make_client)
    a = generate(client, nid, "timeline")
    doc = json.loads(export(client, nid, a, "json").content)
    assert doc["kind"] == "timeline" and doc["sources"][0]["source"] == "zebras.txt"
    assert doc["data"]["events"][0]["iso_date"] == "-44"
    md = export(client, nid, a, "md").content.decode()
    assert "- **March 1874** - Port founded: By Aldane. [1]" in md
    assert "## Key people and entities" in md and "## Sources" in md
    assert export(client, nid, a, "docx").content[:2] == b"PK"
    assert export(client, nid, a, "pdf").content.startswith(b"%PDF")
    assert export(client, nid, a, "csv-quiz").status_code == 422


def test_mind_map_exports_png_and_json(make_client):
    client, _f, nid = ready_notebook(make_client)
    a = generate(client, nid, "mind_map")
    png = export(client, nid, a, "png")
    assert png.headers["content-type"] == "image/png"
    from PIL import Image

    image = Image.open(io.BytesIO(png.content))
    assert image.format == "PNG" and image.width > 200 and image.height > 100
    doc = json.loads(export(client, nid, a, "json").content)
    assert doc["data"]["root"]["label"] == "Zebras"
    assert export(client, nid, a, "md").status_code == 422


def test_flashcards_and_quiz_export_csv_and_json(make_client):
    client, _f, nid = ready_notebook(make_client)
    a = generate(client, nid, "flashcards")
    cards = export(client, nid, a, "csv-flashcards")
    assert cards.headers["content-type"].startswith("text/csv")
    assert "flashcards.csv" in cards.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(cards.content.decode("utf-8-sig"))))
    assert rows[0] == ["front", "back", "source"] and len(rows) == 7
    assert rows[1] == ["Front 0", "Back 0", "zebras.txt"]
    quiz = list(
        csv.reader(io.StringIO(export(client, nid, a, "csv-quiz").content.decode("utf-8-sig")))
    )
    assert quiz[0][:6] == ["question", "option_a", "option_b", "option_c", "option_d", "correct"]
    assert len(quiz) == 4 and quiz[3][5] == "C" and quiz[3][6] == "Because."  # header + 3 questions
    doc = json.loads(export(client, nid, a, "json").content)
    assert len(doc["data"]["quiz"]) == 3 and len(doc["data"]["flashcards"]) == 6
    assert export(client, nid, a, "pdf").status_code == 422


def test_markdown_artifacts_reject_structured_formats(make_client):
    client, _f, nid = ready_notebook(make_client)
    a = generate(client, nid, "summary")
    assert export(client, nid, a, "json").status_code == 422
    assert export(client, nid, a, "md").status_code == 200


def test_render_png_handles_long_labels_and_many_leaves():
    leaf = {"label": "word " * 30, "sources": [], "children": []}
    root = {
        "label": "Root",
        "sources": [],
        "children": [{"label": f"B{i}", "sources": [], "children": [leaf] * 4} for i in range(5)],
    }
    from PIL import Image

    image = Image.open(io.BytesIO(render_png("t", {"root": root})))
    assert image.height > 500 and image.width < 4000


@pytest.mark.parametrize("kind", ["timeline", "mind_map", "flashcards"])
def test_regeneration_keeps_structured_content_readable_on_failure(make_client, kind):
    client, fake, nid = ready_notebook(make_client)
    a = generate(client, nid, kind)
    fake._unreachable = True
    client.post(f"{NB}/{nid}/artifacts/{a['id']}/regenerate")
    from tests.helpers import wait_artifact

    failed = wait_artifact(client, nid, a["id"])
    assert failed["state"] == "ready" and failed["error"]
    assert detail(client, nid, a)["data"] is not None
