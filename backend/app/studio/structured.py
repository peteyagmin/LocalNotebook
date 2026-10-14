"""Structured artifacts (timeline, mind map, flashcards and quiz): JSON validated against Pydantic
schemas, with retries that quote the validation error (FR-5.5 to FR-5.7, FR-5.10)."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator

from app.llm.base import LLMClient, Message
from app.llm.structured import generate_json

MIND_MAP_MAX_DEPTH = 4
MIND_MAP_MAX_CHILDREN = 12
MIND_MAP_MAX_NODES = 120
MAX_FLASHCARDS = 20
QUIZ_QUESTIONS = 10
_ISO_DATE = re.compile(r"^-?\d{1,4}(-\d{2}(-\d{2})?)?$")


class Sourced(BaseModel):
    sources: list[int] = Field(default_factory=list)


class TimelineEvent(Sourced):
    date: str
    iso_date: str
    title: str
    description: str = ""

    @field_validator("iso_date")
    @classmethod
    def _iso(cls, v: str) -> str:
        v = v.strip()
        if not _ISO_DATE.match(v):
            raise ValueError("iso_date must look like 1902, 1902-03, or 1902-03-14")
        return v


class CastMember(Sourced):
    name: str
    role: str = ""


class Timeline(BaseModel):
    events: list[TimelineEvent]
    cast: list[CastMember] = Field(default_factory=list)


class MindNode(Sourced):
    label: str
    children: list[MindNode] = Field(default_factory=list)

    @field_validator("label")
    @classmethod
    def _label(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("label must not be empty")
        return v.strip()


class MindMap(BaseModel):
    root: MindNode

    @field_validator("root")
    @classmethod
    def _has_branches(cls, v: MindNode) -> MindNode:
        if not v.children:
            raise ValueError("the root needs at least one child")
        return v


class Flashcard(Sourced):
    front: str
    back: str


class Flashcards(BaseModel):
    flashcards: list[Flashcard]

    @field_validator("flashcards")
    @classmethod
    def _enough(cls, v: list[Flashcard]) -> list[Flashcard]:
        if len(v) < 5:
            raise ValueError("write at least 5 flashcards")
        return v[:MAX_FLASHCARDS]


# A small notebook cannot support a full-size quiz, so the counts scale with the amount of
# material, up to the spec's 10 questions (FR-5.7). Owner-approved at M5.
def flashcard_target(tokens: int) -> int:
    return max(4, min(15, tokens // 60))


def quiz_count(tokens: int) -> int:
    return max(3, min(QUIZ_QUESTIONS, tokens // 150))


def make_flashcards_schema(tokens: int) -> type[BaseModel]:
    minimum = max(2, min(5, flashcard_target(tokens) - 2))

    class SizedFlashcards(BaseModel):
        flashcards: list[Flashcard]

        @field_validator("flashcards")
        @classmethod
        def _enough(cls, v: list[Flashcard]) -> list[Flashcard]:
            if len(v) < minimum:
                raise ValueError(f"write at least {minimum} flashcards")
            return v[:MAX_FLASHCARDS]

    return SizedFlashcards


class QuizQuestion(Sourced):
    question: str
    options: list[str]
    correct_index: int
    explanation: str = ""

    @field_validator("options")
    @classmethod
    def _four(cls, v: list[str]) -> list[str]:
        if len(v) != 4 or not all(o.strip() for o in v):
            raise ValueError("each question needs exactly 4 non-empty options")
        return v

    @field_validator("correct_index")
    @classmethod
    def _index(cls, v: int) -> int:
        if not 0 <= v <= 3:
            raise ValueError("correct_index must be 0, 1, 2, or 3")
        return v


def make_quiz_schema(tokens: int) -> type[BaseModel]:
    count = quiz_count(tokens)

    class SizedQuiz(BaseModel):
        quiz: list[QuizQuestion]

        @field_validator("quiz")
        @classmethod
        def _exact(cls, v: list[QuizQuestion]) -> list[QuizQuestion]:
            if len(v) < count:
                raise ValueError(f"write exactly {count} questions")
            return v[:count]

    return SizedQuiz


MindNode.model_rebuild()


@dataclass(frozen=True)
class Part:
    prompt: str  # prompt file with the task
    make_schema: Callable[[int], type[BaseModel]]  # given the size of the material in tokens
    prompt_vars: Callable[[int], dict[str, str]] = lambda tokens: {}


# Each structured kind is built from one or more validated parts, merged into one document.
PARTS: dict[str, list[Part]] = {
    "timeline": [Part("artifact_timeline", lambda t: Timeline)],
    "mind_map": [Part("artifact_mind_map", lambda t: MindMap)],
    "flashcards": [
        Part(
            "artifact_flashcards",
            make_flashcards_schema,
            lambda t: {"count": str(flashcard_target(t))},
        ),
        Part("artifact_quiz", make_quiz_schema, lambda t: {"count": str(quiz_count(t))}),
    ],
}


# --- cleaning ------------------------------------------------------------------------------


def _keep(labels: list[int], valid: set[int]) -> list[int]:
    seen: list[int] = []
    for n in labels:
        if n in valid and n not in seen:
            seen.append(n)
    return seen


def _date_key(iso_date: str) -> tuple[int, int, int]:
    match = re.match(r"^(-?\d+)(?:-(\d{2}))?(?:-(\d{2}))?$", iso_date)
    assert match
    return int(match.group(1)), int(match.group(2) or 0), int(match.group(3) or 0)


def _prune_node(node: MindNode, valid: set[int], depth: int) -> dict:
    children = []
    if depth < MIND_MAP_MAX_DEPTH:
        children = [_prune_node(c, valid, depth + 1) for c in node.children[:MIND_MAP_MAX_CHILDREN]]
    return {"label": node.label, "sources": _keep(node.sources, valid), "children": children}


def _count(node: dict) -> int:
    return 1 + sum(_count(c) for c in node["children"])


def _trim_to_node_limit(root: dict) -> dict:
    """Keep the picture readable: drop the deepest level until the tree is small enough."""

    def deepest(node: dict, level: int = 1) -> int:
        return max([level] + [deepest(c, level + 1) for c in node["children"]])

    def cut(node: dict, level: int, limit: int) -> None:
        if level == limit - 1:
            node["children"] = []
        else:
            for child in node["children"]:
                cut(child, level + 1, limit)

    while _count(root) > MIND_MAP_MAX_NODES and deepest(root) > 2:
        cut(root, 1, deepest(root))
    return root


def clean(kind: str, parts: list[BaseModel], valid: set[int]) -> dict:
    """Drop citations to passages that were never supplied, drop items left without any support,
    sort the timeline, and cap the mind map's depth."""
    if kind == "timeline":
        tl = parts[0]
        assert isinstance(tl, Timeline)
        events = [
            {**e.model_dump(), "sources": _keep(e.sources, valid)}
            for e in sorted(tl.events, key=lambda e: _date_key(e.iso_date))
        ]
        cast = [{**m.model_dump(), "sources": _keep(m.sources, valid)} for m in tl.cast]
        return {
            "events": [e for e in events if e["sources"]],
            "cast": [m for m in cast if m["sources"]],
        }
    if kind == "mind_map":
        mm = parts[0]
        assert isinstance(mm, MindMap)
        return {"root": _trim_to_node_limit(_prune_node(mm.root, valid, 1))}
    if kind == "flashcards":
        cards, quiz = parts
        flash = [
            {**c.model_dump(), "sources": _keep(c.sources, valid)}
            for c in cards.flashcards  # type: ignore[attr-defined]
        ]
        questions = [
            {**q.model_dump(), "sources": _keep(q.sources, valid)}
            for q in quiz.quiz  # type: ignore[attr-defined]
        ]
        return {
            "flashcards": [c for c in flash if c["sources"]],
            "quiz": [q for q in questions if q["sources"]],
        }
    raise ValueError(kind)


def used_labels(data: object) -> set[int]:
    """Every passage number cited anywhere in a structured document."""
    found: set[int] = set()
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "sources" and isinstance(value, list):
                found.update(n for n in value if isinstance(n, int))
            else:
                found |= used_labels(value)
    elif isinstance(data, list):
        for item in data:
            found |= used_labels(item)
    return found


def is_empty(kind: str, data: dict) -> bool:
    """True if nothing usable is left. A timeline with no events is a valid result."""
    if kind == "timeline":
        return False
    if kind == "mind_map":
        return not data["root"]["children"]
    return not data["flashcards"] or not data["quiz"]


async def build_data(
    kind: str,
    llm: LLMClient,
    model: str,
    make_messages: Callable[[str, dict[str, str]], list[Message]],
    run: Callable[[Awaitable], Awaitable],
    valid: set[int],
    material_tokens: int,
) -> dict:
    """Generate each part (retrying invalid JSON, FR-5.10) and clean the merged result.
    `run` wraps every awaited call so the job can be cancelled between and during calls."""
    results: list[BaseModel] = []
    for part in PARTS[kind]:
        messages = make_messages(part.prompt, part.prompt_vars(material_tokens))
        schema = part.make_schema(material_tokens)
        results.append(await run(generate_json(llm, model, messages, schema)))
    return clean(kind, results, valid)
