"""Audio overview: outline -> script -> speech -> mix (FR-6.1 to FR-6.4)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field, field_validator

from app.chat.citations import strip_citations
from app.core.errors import AppError
from app.ingest.chunker import est_tokens
from app.llm.base import LLMClient
from app.llm.prompts import render_prompt
from app.llm.structured import generate_json
from app.retrieval.hybrid import Retrieved
from app.speech.tts import TTSUnavailable

LENGTHS = {"short": (5, 3), "default": (10, 5), "long": (20, 8)}  # minutes, sections
FORMATS = {"deep_dive": "Deep dive", "brief": "Brief", "debate": "Debate", "critique": "Critique"}
DEFAULT_OPTIONS = {"length": "default", "format": "deep_dive"}
WORDS_PER_MINUTE = 150
MAX_SECTIONS = 12
SAME_SPEAKER_PAUSE_S = 0.25
SPEAKER_CHANGE_PAUSE_S = 0.40
AFTER_QUESTION_PAUSE_S = 0.50
TAIL_SILENCE_S = 0.5
CONTEXT_TURNS = 4
FFMPEG_TIMEOUT_S = 900
MAX_SCRIPT_TURNS = 600
MAX_TURN_CHARS = 2000


OPENING_NOTE = "This is the opening: welcome the listener and say what the episode covers."
CLOSING_NOTE = (
    "This is the last section: finish by summing up the main takeaways and saying goodbye."
)
MIDDLE_NOTE = "Continue the conversation naturally; do not greet the listener again."


class Cancelled(Exception):
    pass


class AudioError(Exception):
    """A user-readable reason the audio could not be made."""


def normalize_options(options: dict | None) -> dict:
    merged = {**DEFAULT_OPTIONS, **(options or {})}
    if merged["length"] not in LENGTHS:
        raise AppError(422, "bad_option", "The length must be short, default, or long.")
    if merged["format"] not in FORMATS:
        raise AppError(
            422, "bad_option", "The format must be deep dive, brief, debate, or critique."
        )
    return {"length": merged["length"], "format": merged["format"]}


# --- script generation -----------------------------------------------------------------------


class OutlineSection(BaseModel):
    heading: str
    points: list[str] = Field(default_factory=list)
    sources: list[int] = Field(default_factory=list)


class Outline(BaseModel):
    title: str = ""
    sections: list[OutlineSection]

    @field_validator("sections")
    @classmethod
    def _some(cls, v: list[OutlineSection]) -> list[OutlineSection]:
        if not v:
            raise ValueError("the outline needs at least one section")
        return v[:MAX_SECTIONS]


def normalize_speaker(value: str) -> str:
    cleaned = str(value).strip().upper().replace("HOST", "").strip(" :")
    if cleaned not in ("A", "B"):
        raise ValueError('speaker must be "A" or "B"')
    return cleaned


class ScriptTurn(BaseModel):
    speaker: str
    text: str
    sources: list[int] = Field(default_factory=list)

    @field_validator("speaker")
    @classmethod
    def _speaker(cls, v: str) -> str:
        return normalize_speaker(v)


class SectionScript(BaseModel):
    turns: list[ScriptTurn]

    @field_validator("turns")
    @classmethod
    def _enough(cls, v: list[ScriptTurn]) -> list[ScriptTurn]:
        if len([t for t in v if t.text.strip()]) < 2:
            raise ValueError("write at least two turns of dialogue")
        return v


def spoken_text(text: str) -> str:
    """What will actually be said: no citation markers, no stray Markdown emphasis."""
    cleaned = strip_citations(text).replace("**", "").replace("__", "").replace("*", "")
    return " ".join(cleaned.split())


def targets(options: dict) -> tuple[int, int, int]:
    """(minutes, sections, total words) for the chosen length."""
    minutes, sections = LENGTHS[options["length"]]
    return minutes, sections, minutes * WORDS_PER_MINUTE


async def write_script(
    llm: LLMClient,
    model: str,
    options: dict,
    material_parts: list[str],
    condensed: bool,
    passages: list[Retrieved],
    texts: list[str],
    make_messages,
    run,
    stage: Callable[[str, float], None],
    check: Callable[[], None],
) -> tuple[str, list[dict]]:
    """The episode title and its turns: [{speaker, text, chunk_ids}]."""
    minutes, section_count, total_words = targets(options)
    format_name = FORMATS[options["format"]]
    format_instructions = render_prompt(f"audio_format_{options['format']}")

    stage("Writing the outline", 0.1)
    material = "\n\n".join(material_parts)
    outline = await run(
        generate_json(
            llm,
            model,
            make_messages(
                render_prompt(
                    "audio_outline",
                    minutes=str(minutes),
                    sections=str(section_count),
                    format_name=format_name,
                    format_instructions=format_instructions,
                ),
                material,
            ),
            Outline,
        )
    )
    check()

    valid = set(range(1, len(passages) + 1))
    sections = outline.sections
    per_section = max(60, total_words // len(sections))
    turns: list[dict] = []
    for index, section in enumerate(sections, start=1):
        check()
        stage(
            f"Writing the script ({index} of {len(sections)})",
            0.15 + 0.4 * (index - 1) / len(sections),
        )
        wanted = [n for n in section.sources if n in valid]
        if condensed or not wanted:
            section_material = material
        else:
            section_material = "\n\n".join(texts[n - 1] for n in dict.fromkeys(wanted))
        recent = " ".join(f"Host {t['speaker']}: {t['text']}" for t in turns[-CONTEXT_TURNS:])
        if index == 1:
            position = OPENING_NOTE
        elif index == len(sections):
            position = CLOSING_NOTE
        else:
            position = MIDDLE_NOTE
        task = render_prompt(
            "audio_script",
            format_name=format_name,
            format_instructions=format_instructions,
            heading=section.heading,
            number=str(index),
            total=str(len(sections)),
            points="\n".join(f"- {p}" for p in section.points) or "- (cover what matters most)",
            position_note=position,
            previous=f"The conversation so far ended with: {recent}" if recent else "",
            words=str(per_section),
        )
        script = await run(
            generate_json(llm, model, make_messages(task, section_material), SectionScript)
        )
        for turn in script.turns:
            text = spoken_text(turn.text)
            if not text:
                continue
            labels = list(dict.fromkeys(n for n in turn.sources if n in valid))
            turns.append(
                {
                    "speaker": turn.speaker,
                    "text": text[:MAX_TURN_CHARS],
                    "chunk_ids": [passages[n - 1].chunk_id for n in labels],
                }
            )
    if not turns:
        raise AudioError("The model did not write any dialogue. Try again.")
    return outline.title.strip() or "Audio overview", turns


# --- speech and mixing ----------------------------------------------------------------------


def pause_seconds(previous: dict, following: dict) -> float:
    """A short natural pause between turns, 250 to 500 ms (FR-6.1)."""
    if previous["text"].rstrip().endswith("?"):
        return AFTER_QUESTION_PAUSE_S
    return (
        SAME_SPEAKER_PAUSE_S
        if previous["speaker"] == following["speaker"]
        else SPEAKER_CHANGE_PAUSE_S
    )


def assemble(
    pieces: list[np.ndarray], turns: list[dict], sample_rate: int
) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """Join the spoken turns with pauses. Returns the samples and each turn's (start, end)."""
    parts: list[np.ndarray] = []
    times: list[tuple[float, float]] = []
    position = 0
    for i, piece in enumerate(pieces):
        start = position
        parts.append(piece)
        position += len(piece)
        times.append((start / sample_rate, position / sample_rate))
        if i < len(pieces) - 1:
            gap = np.zeros(
                int(pause_seconds(turns[i], turns[i + 1]) * sample_rate), dtype=np.float32
            )
            parts.append(gap)
            position += len(gap)
    parts.append(np.zeros(int(TAIL_SILENCE_S * sample_rate), dtype=np.float32))
    return np.concatenate(parts), times


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(pcm.tobytes())


async def encode_mp3(wav: Path, mp3: Path, sample_rate: int) -> None:
    """Normalize loudness and export MP3 with ffmpeg (FR-6.1)."""
    exe = shutil.which("ffmpeg")
    if exe is None:
        raise AudioError(
            "ffmpeg is not installed, so the MP3 cannot be made. Install it and retry."
        )
    process = await asyncio.create_subprocess_exec(
        exe, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(sample_rate), "-ac", "1",
        "-codec:a", "libmp3lame", "-q:a", "4", str(mp3),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )  # fmt: skip
    try:
        _, error = await asyncio.wait_for(process.communicate(), FFMPEG_TIMEOUT_S)
    except (asyncio.CancelledError, TimeoutError):
        process.kill()
        await process.wait()
        raise
    if process.returncode != 0:
        detail = error.decode(errors="replace").strip().splitlines()[-1:] or ["unknown error"]
        raise AudioError(f"ffmpeg could not make the MP3 ({detail[0]}).")


async def speak_and_mix(
    turns: list[dict],
    engine,
    voices: dict[str, str],
    folder: Path,
    stage: Callable[[str, float], None],
    check: Callable[[], None],
) -> tuple[list[dict], float]:
    """Speak every turn with its host's voice, join them, and write audio.mp3. Returns the
    turns with start/end times and the duration. The old audio stays until the new one is done."""
    pieces: list[np.ndarray] = []
    for i, turn in enumerate(turns, start=1):
        check()
        stage(f"Speaking ({i} of {len(turns)})", 0.55 + 0.35 * (i - 1) / len(turns))
        try:
            audio = await asyncio.to_thread(
                engine.synthesize, turn["text"], voices[turn["speaker"]]
            )
        except TTSUnavailable as e:
            raise AudioError(str(e)) from e
        pieces.append(audio)
    check()
    stage("Mixing the audio", 0.92)
    samples, times = assemble(pieces, turns, engine.sample_rate)
    if samples.size <= int(TAIL_SILENCE_S * engine.sample_rate):
        raise AudioError("The voices produced no sound. Check the text-to-speech setup.")
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder) as scratch:
        wav = Path(scratch) / "mix.wav"
        mp3 = Path(scratch) / "audio.mp3"
        await asyncio.to_thread(write_wav, wav, samples, engine.sample_rate)
        await encode_mp3(wav, mp3, engine.sample_rate)
        os.replace(mp3, folder / "audio.mp3")
    timed = [
        {**turn, "start": round(start, 3), "end": round(end, 3)}
        for turn, (start, end) in zip(turns, times, strict=True)
    ]
    return timed, round(len(samples) / engine.sample_rate, 3)


def read_transcript(folder: Path) -> dict | None:
    path = folder / "transcript.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write_transcript(folder: Path, transcript: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "transcript.json.tmp"
    tmp.write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, folder / "transcript.json")


def validate_turns(turns: list[dict]) -> list[dict]:
    """Check an edited script (FR-6.4) and return clean turns: {speaker, text, chunk_ids}."""
    if not turns:
        raise AppError(422, "empty_script", "The script needs at least one turn.")
    if len(turns) > MAX_SCRIPT_TURNS:
        raise AppError(
            422, "script_too_long", f"The script can have at most {MAX_SCRIPT_TURNS} turns."
        )
    clean = []
    for turn in turns:
        try:
            speaker = normalize_speaker(turn["speaker"])
        except (ValueError, KeyError):
            raise AppError(
                422, "bad_speaker", "Each turn needs a speaker, Host A or Host B."
            ) from None
        text = " ".join(str(turn.get("text", "")).split())
        if not text:
            raise AppError(422, "empty_turn", "A turn cannot be empty. Delete it instead.")
        if len(text) > MAX_TURN_CHARS:
            raise AppError(
                422, "turn_too_long", f"A turn can have at most {MAX_TURN_CHARS} characters."
            )
        chunk_ids = [c for c in turn.get("chunk_ids", []) if isinstance(c, str)]
        clean.append({"speaker": speaker, "text": text, "chunk_ids": chunk_ids})
    return clean


def material_tokens(texts: list[str]) -> int:
    return sum(est_tokens(len(t)) for t in texts)
