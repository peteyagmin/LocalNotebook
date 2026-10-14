"""Generate Markdown artifacts from the enabled sources (FR-5.1 to FR-5.4, FR-5.9, FR-5.12).

If every passage fits in the model's context window the artifact is written in one call.
Otherwise a map-reduce pass condenses groups of passages into notes that keep their [n]
citation labels, and the artifact is written from those notes (FR-5.9).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from app.chat.service import build_citation, describe_location
from app.core.ids import now_iso
from app.core.notebooks import NotebookStore, NotFound
from app.ingest.chunker import est_tokens
from app.ingest.services import Services
from app.llm.base import LLMClient, LLMError, Message
from app.llm.prompts import render_prompt
from app.llm.structured import StructuredOutputError
from app.notes.service import filter_to_valid
from app.retrieval.hybrid import Retrieved
from app.retrieval.vectors import ENABLED_READY
from app.speech.tts import TTSUnavailable
from app.studio import audio
from app.studio.structured import PARTS, build_data, is_empty, used_labels

log = logging.getLogger(__name__)
T = TypeVar("T")

KINDS = {
    "summary": "Notebook summary",
    "briefing": "Briefing document",
    "study_guide": "Study guide",
    "faq": "FAQ",
    "timeline": "Timeline",
    "mind_map": "Mind map",
    "flashcards": "Flashcards & quiz",
    "audio_overview": "Audio overview",
}
JSON_KINDS = frozenset(PARTS)
OUTPUT_RESERVE_TOKENS = 1500
# Structured answers are longer than most prose, so leave more room for them.
OUTPUT_RESERVE_BY_KIND = {
    "timeline": 2500,
    "mind_map": 2000,
    "flashcards": 3000,
    "audio_overview": 3000,
}
PROMPT_OVERHEAD_TOKENS = 700
MAX_CONDENSE_ROUNDS = 6
MAX_FOCUS_CHARS = 500


class GenerationError(Exception):
    """A user-readable reason the artifact could not be generated."""


class Cancelled(Exception):
    pass


def artifact_dir(store: NotebookStore, notebook_id: str, artifact_id: str) -> Path:
    return store.folder(notebook_id) / "artifacts" / artifact_id


def gather_passages(conn) -> list[Retrieved]:
    """Every chunk of every enabled, ready source, in reading order."""

    rows = conn.execute(
        "SELECT c.*, s.name AS source_name FROM chunks c JOIN sources s ON s.id = c.source_id "
        f"WHERE {ENABLED_READY} ORDER BY s.created_at, s.id, c.ordinal"
    ).fetchall()
    return [
        Retrieved(
            chunk_id=r["id"],
            source_id=r["source_id"],
            source_name=r["source_name"],
            text=r["text"],
            location=json.loads(r["location"]),
            char_start=r["char_start"],
            char_end=r["char_end"],
            score=0.0,
        )
        for r in rows
    ]


def passage_text(label: int, r: Retrieved) -> str:
    where = describe_location(r.location)
    return f"[{label}] (Source: {r.source_name}{', ' + where if where else ''})\n{r.text}"


def group_by_budget(texts: list[str], budget: int) -> list[list[int]]:
    """Indices of consecutive texts, grouped so each group fits the token budget."""
    groups: list[list[int]] = []
    current: list[int] = []
    used = 0
    for i, text in enumerate(texts):
        tokens = est_tokens(len(text))
        if current and used + tokens > budget:
            groups.append(current)
            current, used = [], 0
        current.append(i)
        used += tokens
    if current:
        groups.append(current)
    return groups


def build_messages(
    task: str, material: str, focus: str, system: str = "artifact_system"
) -> list[Message]:
    nonce = secrets.token_hex(8)
    focus_block = render_prompt("artifact_focus", focus=focus.strip()) if focus.strip() else ""
    user = render_prompt(
        "artifact_user",
        open=f"<<<MATERIAL {nonce}>>>",
        close=f"<<<END MATERIAL {nonce}>>>",
        material=material,
        task=task,
        focus_block=focus_block,
    )
    return [
        {"role": "system", "content": render_prompt(system)},
        {"role": "user", "content": user},
    ]


async def _race(coro: Awaitable[T], cancel: asyncio.Event) -> T:
    """Run an LLM call but give up promptly if the job is cancelled (FR-5.12)."""
    call = asyncio.ensure_future(coro)
    waiter = asyncio.ensure_future(cancel.wait())
    try:
        done, _ = await asyncio.wait({call, waiter}, return_when=asyncio.FIRST_COMPLETED)
        if call not in done:
            call.cancel()
            await asyncio.gather(call, return_exceptions=True)
            raise Cancelled
        return call.result()
    finally:
        waiter.cancel()


def _update(store: NotebookStore, notebook_id: str, artifact_id: str, **fields) -> None:
    fields["updated_at"] = now_iso()
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn = store.open(notebook_id)
    try:
        with conn:
            conn.execute(
                f"UPDATE artifacts SET {sets} WHERE id = ?", (*fields.values(), artifact_id)
            )
    finally:
        conn.close()


async def run_generation(
    store: NotebookStore,
    notebook_id: str,
    artifact_id: str,
    llm: LLMClient,
    settings: dict,
    cancel: asyncio.Event,
    services: Services | None = None,
) -> str | None:
    """Generate one artifact. Returns None on success, else the user-readable reason it failed."""

    def stage(name: str, progress: float) -> None:
        _update(store, notebook_id, artifact_id, stage=name, progress=progress)

    try:
        conn = store.open(notebook_id)
        try:
            row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
            if row is None:
                raise Cancelled
            kind, focus = row["kind"], row["focus"]
            options = json.loads(row["options"]) if row["options"] else None
            passages = gather_passages(conn)
        finally:
            conn.close()
        if not settings["chat_model"]:
            raise GenerationError("No chat model is configured. Choose one in Settings.")
        if not passages:
            raise GenerationError(
                "There are no enabled sources to use. Turn on at least one source that has "
                "finished processing."
            )
        if cancel.is_set():
            raise Cancelled

        _update(
            store,
            notebook_id,
            artifact_id,
            state="running",
            error=None,
            stage="Collecting passages",
            progress=0.05,
        )
        model = settings["chat_model"]
        reserve = OUTPUT_RESERVE_BY_KIND.get(kind, OUTPUT_RESERVE_TOKENS)
        budget = max(1000, settings["context_window_tokens"] - reserve - PROMPT_OVERHEAD_TOKENS)
        texts = [passage_text(i, r) for i, r in enumerate(passages, start=1)]
        task = (
            ""
            if kind in JSON_KINDS or kind == "audio_overview"
            else render_prompt(f"artifact_{kind}")
        )

        material_parts = texts
        if sum(est_tokens(len(t)) for t in texts) > budget:
            material_parts = await _condense_until_fits(
                llm, model, texts, budget, focus, cancel, stage
            )
        if kind == "audio_overview":
            services = services or Services(models_dir=store.data_root / "models")
            await _generate_audio(
                store, notebook_id, artifact_id, llm, settings, services, cancel, stage, options,
                focus, passages, texts, material_parts, condensed=material_parts is not texts,
            )  # fmt: skip
            return None
        stage("Writing", 0.8)
        citations = [build_citation(i, r) for i, r in enumerate(passages, start=1)]
        if kind in JSON_KINDS:
            material = "\n\n".join(material_parts)
            data = await build_data(
                kind,
                llm,
                model,
                lambda prompt, extra: build_messages(
                    render_prompt(prompt, **extra), material, focus, system="artifact_system_json"
                ),
                lambda awaitable: _race(awaitable, cancel),
                {c["label"] for c in citations},
                est_tokens(len(material)),
            )
            if is_empty(kind, data):
                raise GenerationError(
                    "The model's answer had nothing the sources support. Try again."
                )
            labels = used_labels(data)
            used = [c for c in citations if c["label"] in labels]
            content, filename = json.dumps(data, ensure_ascii=False), "content.json"
        else:
            reply = await _race(
                llm.chat(model, build_messages(task, "\n\n".join(material_parts), focus)), cancel
            )
            content, used = filter_to_valid(reply.strip(), citations)
            filename = "content.md"
            if not content.strip():
                raise GenerationError("The model returned an empty document. Try again.")

        folder = artifact_dir(store, notebook_id, artifact_id)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f"{filename}.tmp"
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, folder / filename)
        _update(
            store,
            notebook_id,
            artifact_id,
            state="ready",
            stage=None,
            progress=1.0,
            error=None,
            has_content=1,
            citations=json.dumps(used),
            source_ids=json.dumps(sorted({p.source_id for p in passages})),
        )
        return None
    except Cancelled:
        message = "Cancelled."
        cancelled = True
    except NotFound:
        return "Cancelled."
    except (
        GenerationError,
        LLMError,
        StructuredOutputError,
        audio.AudioError,
        TTSUnavailable,
    ) as e:
        message, cancelled = str(e), False
    except Exception as e:
        log.exception("Artifact generation failed for %s", artifact_id)
        message, cancelled = f"Unexpected error ({e.__class__.__name__}). See the app log.", False
    try:
        _record_failure(store, notebook_id, artifact_id, message, cancelled)
    except Exception:  # notebook or artifact deleted meanwhile
        log.debug("Could not record failure for %s", artifact_id)
    return message


def _record_failure(
    store: NotebookStore, notebook_id: str, artifact_id: str, message: str, cancelled: bool
) -> None:
    """A failed regeneration leaves the previous version readable (state stays ready)."""
    conn = store.open(notebook_id)
    try:
        row = conn.execute(
            "SELECT has_content FROM artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return
    if row["has_content"]:
        state = "ready"
    else:
        state = "cancelled" if cancelled else "failed"
    _update(store, notebook_id, artifact_id, state=state, stage=None, progress=0, error=message)


async def _condense_until_fits(
    llm: LLMClient,
    model: str,
    texts: list[str],
    budget: int,
    focus: str,
    cancel: asyncio.Event,
    stage: Callable[[str, float], None],
) -> list[str]:
    """Map step: turn groups of passages into notes that keep their [n] labels; repeat on the
    notes if they are still too large (FR-5.9)."""
    task = render_prompt("artifact_map")
    parts = texts
    for round_number in range(MAX_CONDENSE_ROUNDS):
        groups = group_by_budget(parts, budget)
        notes: list[str] = []
        for i, group in enumerate(groups):
            if cancel.is_set():
                raise Cancelled
            stage(
                f"Reading part {i + 1} of {len(groups)}",
                0.1 + 0.65 * (i / len(groups)) / (round_number + 1),
            )
            material = "\n\n".join(parts[j] for j in group)
            notes.append(
                await _race(llm.chat(model, build_messages(task, material, focus)), cancel)
            )
        parts = [f"Notes from part {i + 1}:\n{n.strip()}" for i, n in enumerate(notes)]
        if sum(est_tokens(len(p)) for p in parts) <= budget:
            return parts
    raise GenerationError(
        "The sources are too large for this model's context window. Increase the context "
        "window in Settings or turn off some sources."
    )


# --- audio overview (FR-6.1, FR-6.4) ----------------------------------------------------------


def _citation_snapshots(chunk_ids: list[str], known: dict[str, dict]) -> list[dict]:
    """Snapshots of the chunks a script cites, numbered by first appearance."""
    ordered = list(dict.fromkeys(c for c in chunk_ids if c in known))
    return [{**known[c], "label": i} for i, c in enumerate(ordered, start=1)]


def _voices(settings: dict) -> dict[str, str]:
    return {"A": settings["tts_voice_a"], "B": settings["tts_voice_b"]}


async def _generate_audio(
    store, notebook_id, artifact_id, llm, settings, services, cancel, stage, raw_options,
    focus, passages, texts, material_parts, condensed,
):  # fmt: skip
    options = audio.normalize_options(raw_options)

    def check() -> None:
        if cancel.is_set():
            raise Cancelled

    # Find out about missing speech setup before spending time on the script.
    stage("Preparing the voices", 0.07)
    engine = await asyncio.to_thread(services.tts, settings, services.models_dir)
    check()
    title, turns = await audio.write_script(
        llm,
        settings["chat_model"],
        options,
        material_parts,
        condensed,
        passages,
        texts,
        lambda task, material: build_messages(task, material, focus, system="audio_system"),
        lambda awaitable: _race(awaitable, cancel),
        stage,
        check,
    )
    folder = artifact_dir(store, notebook_id, artifact_id)
    timed, duration = await audio.speak_and_mix(
        turns, engine, _voices(settings), folder, stage, check
    )
    audio.write_transcript(
        folder,
        {
            "title": title,
            "options": options,
            "turns": timed,
            "duration": duration,
            "outdated": False,
        },
    )
    known = {r.chunk_id: build_citation(i, r) for i, r in enumerate(passages, start=1)}
    used = _citation_snapshots([c for t in turns for c in t["chunk_ids"]], known)
    _update(
        store, notebook_id, artifact_id,
        state="ready", stage=None, progress=1.0, error=None, has_content=1,
        citations=json.dumps(used),
        source_ids=json.dumps(sorted({p.source_id for p in passages})),
    )  # fmt: skip


async def run_resynthesis(
    store: NotebookStore,
    notebook_id: str,
    artifact_id: str,
    settings: dict,
    cancel: asyncio.Event,
    services: Services | None = None,
) -> str | None:
    """Rebuild the audio from the (possibly edited) script without writing a new one (FR-6.4)."""
    services = services or Services(models_dir=store.data_root / "models")

    def stage(name: str, progress: float) -> None:
        _update(store, notebook_id, artifact_id, stage=name, progress=progress)

    def check() -> None:
        if cancel.is_set():
            raise Cancelled

    try:
        folder = artifact_dir(store, notebook_id, artifact_id)
        transcript = audio.read_transcript(folder)
        conn = store.open(notebook_id)
        try:
            row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise Cancelled
        if transcript is None:
            raise GenerationError("There is no script to speak yet.")
        _update(
            store, notebook_id, artifact_id,
            state="running", error=None, stage="Preparing the voices", progress=0.05,
        )  # fmt: skip
        engine = await asyncio.to_thread(services.tts, settings, services.models_dir)
        turns = [
            {"speaker": t["speaker"], "text": t["text"], "chunk_ids": t.get("chunk_ids", [])}
            for t in transcript["turns"]
        ]
        timed, duration = await audio.speak_and_mix(
            turns, engine, _voices(settings), folder, stage, check
        )
        transcript.update(turns=timed, duration=duration, outdated=False)
        audio.write_transcript(folder, transcript)
        known = {c["chunk_id"]: c for c in json.loads(row["citations"])}
        used = _citation_snapshots([c for t in turns for c in t["chunk_ids"]], known)
        _update(
            store, notebook_id, artifact_id,
            state="ready", stage=None, progress=1.0, error=None, citations=json.dumps(used),
        )  # fmt: skip
        return None
    except Cancelled:
        message, cancelled = "Cancelled.", True
    except NotFound:
        return "Cancelled."
    except (GenerationError, audio.AudioError, TTSUnavailable) as e:
        message, cancelled = str(e), False
    except Exception as e:
        log.exception("Re-synthesis failed for %s", artifact_id)
        message, cancelled = f"Unexpected error ({e.__class__.__name__}). See the app log.", False
    try:
        _record_failure(store, notebook_id, artifact_id, message, cancelled)
    except Exception:  # deleted meanwhile
        log.debug("Could not record failure for %s", artifact_id)
    return message
