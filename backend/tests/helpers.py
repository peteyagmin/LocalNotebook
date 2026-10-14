"""Shared helpers for tests that need ingested sources and a scripted model."""

import io
import json
import time

from app.llm.base import Message
from app.llm.fake import FakeLLMClient
from tests.conftest import GUIDE_JSON, wait_idle

NB = "/api/v1/notebooks"
MD_DOC = (
    "# Notebook summary\n\nZebras graze on grass [1]. Bogus claim [99].\n\n"
    "## Key points\n\n- Herds [1][2]\n"
)


def _node(label, sources, children=()):
    return {"label": label, "sources": sources, "children": list(children)}


TIMELINE = {
    "events": [
        {
            "date": "1902",
            "iso_date": "1902",
            "title": "Lighthouse built",
            "description": "Tall.",
            "sources": [1],
        },
        {
            "date": "44 BCE",
            "iso_date": "-44",
            "title": "Ancient event",
            "description": "",
            "sources": [1, 99],
        },
        {
            "date": "March 1874",
            "iso_date": "1874-03",
            "title": "Port founded",
            "description": "By Aldane.",
            "sources": [1],
        },
        {
            "date": "1874",
            "iso_date": "1874",
            "title": "Year of founding",
            "description": "",
            "sources": [1],
        },
        {
            "date": "Someday",
            "iso_date": "2000",
            "title": "Unsupported",
            "description": "",
            "sources": [99],
        },
    ],
    "cast": [
        {"name": "Henrik Aldane", "role": "founder", "sources": [1]},
        {"name": "Ghost", "role": "invented", "sources": [77]},
    ],
}
MIND_MAP = {
    "root": _node(
        "Zebras",
        [1],
        [
            _node(
                "Diet",
                [1, 99],
                [_node("Grass", [1], [_node("Too deep", [1], [_node("Way too deep", [1])])])],
            ),
            _node("Habitat", [], [_node("Savanna", [1])]),
        ],
    )
}
FLASHCARDS = {
    "flashcards": [{"front": f"Front {i}", "back": f"Back {i}", "sources": [1]} for i in range(6)]
    + [{"front": "Unsupported", "back": "x", "sources": [99]}]
}
QUIZ = {
    "quiz": [
        {
            "question": f"Question {i}?",
            "options": ["A", "B", "C", "D"],
            "correct_index": i % 4,
            "explanation": "Because.",
            "sources": [1],
        }
        for i in range(12)
    ]
}


def original_prompt(messages: list[Message]) -> str:
    """The task prompt, ignoring the "that reply was not valid" retry messages."""
    users = [m["content"] for m in messages if m["role"] == "user"]
    return next((c for c in reversed(users) if not c.startswith("That reply was not valid")), "")


def brain(_model: str, messages: list[Message]) -> str:
    """Scripted model that recognises each kind of prompt the app sends."""
    last = original_prompt(messages)
    if "Extract a timeline" in last:
        return json.dumps(TIMELINE)
    if "Build a mind map" in last:
        return json.dumps(MIND_MAP)
    if "flashcards that help" in last:
        return json.dumps(FLASHCARDS)
    if "multiple-choice questions" in last:
        return json.dumps(QUIZ)
    if "working notes" in last:
        return "- A note about zebras [1]."
    if "the user's own notes" in last:
        return "The notes discuss zebras [1] and more [42]."
    if "<<<MATERIAL" in last:
        return MD_DOC
    if "follow-up questions" in last:
        return json.dumps({"questions": ["Next?"]})
    if "PASSAGES" in last:
        return "Zebras graze [1]."
    return GUIDE_JSON


def add_text(client, nid, name, text):
    client.post(
        f"{NB}/{nid}/sources/files",
        files=[("files", (name, io.BytesIO(text.encode()), "text/plain"))],
    )


def ready_notebook(make_client, texts=None, fake=None):
    fake = fake or FakeLLMClient(default_reply=brain)
    client = make_client(fake)
    client.put("/api/v1/settings", json={"chat_model": "c", "embedding_model": "e"})
    nid = client.post(NB, json={"name": "NB"}).json()["id"]
    for name, text in (texts or {"zebras.txt": "Zebras graze on grass in herds."}).items():
        add_text(client, nid, name, text)
    wait_idle(client, nid)
    return client, fake, nid


def wait_artifact(client, nid, artifact_id, states=("ready", "failed", "cancelled"), timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        a = client.get(f"{NB}/{nid}/artifacts/{artifact_id}").json()
        if a["state"] in states:
            return a
        time.sleep(0.05)
    raise AssertionError(f"artifact stuck in {a['state']}")


def generate(client, nid, kind="summary", focus=None):
    body = {"kind": kind, **({"focus": focus} if focus is not None else {})}
    r = client.post(f"{NB}/{nid}/artifacts", json=body)
    assert r.status_code == 202, r.text
    return wait_artifact(client, nid, r.json()["id"])
