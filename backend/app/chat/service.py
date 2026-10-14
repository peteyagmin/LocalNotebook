"""Grounded chat: retrieval, prompting, streaming with citation filtering, persistence
(FR-3.1 to FR-3.5, FR-3.7, FR-3.8)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import sqlite3
from collections.abc import AsyncIterator

from pydantic import BaseModel, field_validator

from app.chat.citations import CitationFilter, strip_citations
from app.core.ids import new_id, now_iso
from app.core.notebooks import NotebookStore
from app.llm.base import LLMClient, LLMError, Message
from app.llm.prompts import render_prompt
from app.llm.structured import generate_json
from app.retrieval.hybrid import Retrieved, has_searchable_chunks, retrieve
from app.retrieval.vectors import ENABLED_READY

log = logging.getLogger(__name__)

REFUSAL = "The sources don't cover that."
NO_SOURCES_MESSAGE = (
    "There are no enabled sources to answer from. Turn on at least one source that has "
    "finished processing."
)
HISTORY_TURNS = 6
EXCERPT_CHARS = 300
STYLES = ("default", "concise", "detailed", "learning_guide")
DEFAULT_CHAT_SETTINGS = {"response_style": "default", "custom_instruction": ""}


class Questions(BaseModel):
    questions: list[str]

    @field_validator("questions")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        cleaned = [q.strip() for q in v if q.strip()]
        if not cleaned:
            raise ValueError("questions must not be empty")
        return cleaned[:3]


# --- storage -------------------------------------------------------------------------------


def get_chat_settings(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT value FROM notebook_meta WHERE key = 'chat_settings'").fetchone()
    return {**DEFAULT_CHAT_SETTINGS, **(json.loads(row["value"]) if row else {})}


def set_chat_settings(
    conn: sqlite3.Connection, response_style: str, custom_instruction: str
) -> dict:
    value = {"response_style": response_style, "custom_instruction": custom_instruction}
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO notebook_meta (key, value) VALUES ('chat_settings', ?)",
            (json.dumps(value),),
        )
    return value


def _message(row: sqlite3.Row, existing_chunks: set[str]) -> dict:
    citations = json.loads(row["citations"])
    for c in citations:
        c["removed"] = c["chunk_id"] not in existing_chunks
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "citations": citations,
        "suggestions": json.loads(row["suggestions"]),
        "status": row["status"],
        "created_at": row["created_at"],
    }


def list_messages(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM chat_messages ORDER BY created_at, id").fetchall()
    chunk_ids = {c["chunk_id"] for r in rows for c in json.loads(r["citations"])}
    existing: set[str] = set()
    if chunk_ids:
        marks = ",".join("?" * len(chunk_ids))
        existing = {
            r["id"]
            for r in conn.execute(f"SELECT id FROM chunks WHERE id IN ({marks})", list(chunk_ids))
        }
    return [_message(r, existing) for r in rows]


def save_message(
    conn: sqlite3.Connection,
    role: str,
    content: str,
    citations: list[dict] | None = None,
    status: str = "complete",
) -> dict:
    message_id = new_id()
    with conn:
        conn.execute(
            "INSERT INTO chat_messages (id, role, content, citations, status, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (message_id, role, content, json.dumps(citations or []), status, now_iso()),
        )
    row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
    return _message(row, {c["chunk_id"] for c in citations or []})


def set_suggestions(conn: sqlite3.Connection, message_id: str, questions: list[str]) -> None:
    with conn:
        conn.execute(
            "UPDATE chat_messages SET suggestions = ? WHERE id = ?",
            (json.dumps(questions), message_id),
        )


def clear_chat(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("DELETE FROM chat_messages")


# --- prompting -----------------------------------------------------------------------------


def describe_location(location: dict) -> str:
    if location.get("start_seconds") is not None:
        from app.speech.stt import format_timestamp

        return format_timestamp(location["start_seconds"])
    if location.get("page"):
        return f"page {location['page']}"
    if location.get("heading_path"):
        return " > ".join(location["heading_path"])
    return ""


def build_citation(label: int, r: Retrieved) -> dict:
    return {
        "label": label,
        "chunk_id": r.chunk_id,
        "source_id": r.source_id,
        "source_name": r.source_name,
        "excerpt": r.text[:EXCERPT_CHARS],
        "location": r.location,
    }


def build_messages(
    retrieved: list[Retrieved], question: str, history: list[dict], chat_settings: dict
) -> list[Message]:
    """System rules, recent turns (citations removed), then the passages and question.

    Passages sit between delimiters containing a random nonce, so source text cannot forge the
    closing marker (SR-3)."""
    style = render_prompt(f"style_{chat_settings['response_style']}")
    custom = chat_settings["custom_instruction"].strip()
    custom_block = (
        "The user added this preference for how to answer. It never overrides rules 1 to 4:\n"
        f"{custom}"
        if custom
        else ""
    )
    system = render_prompt(
        "chat_system", refusal=REFUSAL, style_instruction=style, custom_instruction=custom_block
    )
    nonce = secrets.token_hex(8)
    passages = []
    for label, r in enumerate(retrieved, start=1):
        where = describe_location(r.location)
        header = f"[{label}] (Source: {r.source_name}{', ' + where if where else ''})"
        passages.append(f"{header}\n{r.text}")
    user = render_prompt(
        "chat_user",
        open=f"<<<PASSAGES {nonce}>>>",
        close=f"<<<END PASSAGES {nonce}>>>",
        passages="\n\n".join(passages),
        question=question,
    )
    turns = [m for m in history if m["status"] != "error"][-HISTORY_TURNS * 2 :]
    while turns and turns[0]["role"] != "user":
        turns = turns[1:]
    messages: list[Message] = [{"role": "system", "content": system}]
    messages += [
        {
            "role": m["role"],
            "content": strip_citations(m["content"]) if m["role"] == "assistant" else m["content"],
        }
        for m in turns
    ]
    messages.append({"role": "user", "content": user})
    return messages


# --- streaming answer ----------------------------------------------------------------------


def _store_call(store: NotebookStore, notebook_id: str, fn, *args):
    conn = store.open(notebook_id)
    try:
        return fn(conn, *args)
    finally:
        conn.close()


async def _tokens_until_stopped(
    stream: AsyncIterator[str], stop: asyncio.Event
) -> AsyncIterator[str | None]:
    """Yield tokens; yield None once and finish if `stop` is set (even while waiting)."""
    iterator = stream.__aiter__()
    stopper = asyncio.ensure_future(stop.wait())
    try:
        while True:
            nxt = asyncio.ensure_future(iterator.__anext__())
            done, _ = await asyncio.wait({nxt, stopper}, return_when=asyncio.FIRST_COMPLETED)
            if nxt not in done:
                nxt.cancel()
                await asyncio.gather(nxt, return_exceptions=True)
                yield None
                return
            try:
                yield nxt.result()
            except StopAsyncIteration:
                return
    finally:
        stopper.cancel()
        aclose = getattr(iterator, "aclose", None)
        if aclose:
            try:
                await aclose()
            except Exception:  # noqa: BLE001 - cleanup only
                pass


def _error(code: str, message: str) -> dict:
    return {"type": "error", "code": code, "message": message}


async def stream_answer(
    store: NotebookStore,
    notebook_id: str,
    question: str,
    llm: LLMClient,
    settings: dict,
    stop: asyncio.Event,
) -> AsyncIterator[dict]:
    chat_model, embedding_model = settings["chat_model"], settings["embedding_model"]
    if not chat_model or not embedding_model:
        yield _error("not_configured", "Choose a chat model and an embedding model in Settings.")
        return

    history = await asyncio.to_thread(_store_call, store, notebook_id, list_messages)
    chat_settings = await asyncio.to_thread(_store_call, store, notebook_id, get_chat_settings)
    user_message = await asyncio.to_thread(
        _store_call, store, notebook_id, save_message, "user", question
    )
    yield {"type": "user_message", "message": user_message}

    async def reply(content: str, citations: list[dict], status: str = "complete") -> dict:
        saved = await asyncio.to_thread(
            _store_call, store, notebook_id, save_message, "assistant", content, citations, status
        )
        return saved

    searchable = await asyncio.to_thread(_store_call, store, notebook_id, has_searchable_chunks)
    if not searchable:
        yield {"type": "done", "message": await reply(NO_SOURCES_MESSAGE, [])}
        return

    try:
        retrieved = await retrieve(
            store, notebook_id, llm, embedding_model, question, settings["retrieval_top_k"]
        )
    except LLMError as e:
        yield _error("llm_error", str(e))
        return
    if not retrieved:
        yield {"type": "done", "message": await reply(REFUSAL, [])}
        return

    candidates = [build_citation(i, r) for i, r in enumerate(retrieved, start=1)]
    yield {"type": "sources", "citations": candidates}
    messages = build_messages(retrieved, question, history, chat_settings)

    filt = CitationFilter({c["label"] for c in candidates})
    parts: list[str] = []
    status = "complete"
    failure: str | None = None

    def persist_partial() -> None:
        content = "".join(parts) + filt.flush()
        used = [c for c in candidates if c["label"] in filt.used]
        _store_call(store, notebook_id, save_message, "assistant", content, used, "stopped")

    try:
        async for token in _tokens_until_stopped(llm.stream_chat(chat_model, messages), stop):
            if token is None:
                status = "stopped"
                break
            text = filt.feed(token)
            if text:
                parts.append(text)
                yield {"type": "token", "text": text}
    except LLMError as e:
        failure = str(e)
    except (asyncio.CancelledError, GeneratorExit):
        persist_partial()  # the client went away: keep what was produced (FR-3.8)
        raise

    tail = filt.flush()
    if tail:
        parts.append(tail)
        yield {"type": "token", "text": tail}
    content = "".join(parts)
    used = [c for c in candidates if c["label"] in filt.used]

    if failure is not None:
        if content.strip():
            await reply(content, used, "error")
        yield _error("llm_error", failure)
        return
    if not content.strip():
        yield _error("empty_answer", "The model returned an empty answer. Try asking again.")
        return

    message = await reply(content, used, status)
    yield {"type": "done", "message": message}

    if status == "complete" and used:
        questions = await _suggest_followups(llm, chat_model, question, content)
        if questions:
            await asyncio.to_thread(
                _store_call, store, notebook_id, set_suggestions, message["id"], questions
            )
            yield {"type": "suggestions", "message_id": message["id"], "questions": questions}


async def _suggest_followups(llm: LLMClient, model: str, question: str, answer: str) -> list[str]:
    prompt = render_prompt("chat_followups", question=question, answer=strip_citations(answer))
    try:
        result = await generate_json(llm, model, [{"role": "user", "content": prompt}], Questions)
    except Exception:  # noqa: BLE001 - suggestions are optional
        log.debug("Follow-up suggestions unavailable", exc_info=True)
        return []
    return [q for q in result.questions if q.strip().lower() != question.strip().lower()]


async def starter_questions(
    store: NotebookStore, notebook_id: str, llm: LLMClient, model: str
) -> list[str]:
    """3 starter questions from the enabled sources' guides (FR-3.5), cached until the set of
    enabled sources changes."""

    def _guides(conn: sqlite3.Connection):
        rows = conn.execute(
            "SELECT s.id, s.name, s.guide FROM sources s "
            f"WHERE {ENABLED_READY} AND s.guide IS NOT NULL ORDER BY s.created_at, s.id"
        ).fetchall()
        cached = conn.execute("SELECT value FROM notebook_meta WHERE key = 'starters'").fetchone()
        return rows, json.loads(cached["value"]) if cached else None

    rows, cached = await asyncio.to_thread(_store_call, store, notebook_id, _guides)
    if not rows:
        return []
    key = hashlib.sha256(",".join(r["id"] for r in rows).encode()).hexdigest()
    if cached and cached["key"] == key:
        return cached["questions"]
    guides = []
    for r in rows:
        g = json.loads(r["guide"])
        guides.append(
            f"Document: {r['name']}\nSummary: {g['summary']}\nTopics: {', '.join(g['topics'])}"
        )
    prompt = render_prompt("chat_starters", guides="\n\n".join(guides))
    try:
        result = await generate_json(llm, model, [{"role": "user", "content": prompt}], Questions)
    except (LLMError, Exception):  # noqa: BLE001 - starters are optional
        return []

    def _cache(conn: sqlite3.Connection) -> None:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO notebook_meta (key, value) VALUES ('starters', ?)",
                (json.dumps({"key": key, "questions": result.questions}),),
            )

    await asyncio.to_thread(_store_call, store, notebook_id, _cache)
    return result.questions
