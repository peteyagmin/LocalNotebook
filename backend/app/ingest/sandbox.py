"""Run a parser in a separate process with a timeout and a memory limit (SR-3).

A parser crash, hang, or memory blow-up fails only that source.
"""

from __future__ import annotations

import multiprocessing
import sys
from dataclasses import asdict
from multiprocessing.connection import Connection
from pathlib import Path

from app.ingest.parsers import Block, ParseError, ParseResult, parse

DEFAULT_TIMEOUT_S = 120
# OCR and transcription are slow by nature, so those formats get far longer.
TIMEOUTS_S = {"pdf": 1800, "image": 600, "epub": 300, "audio": 4 * 3600}
MEMORY_LIMIT_BYTES = 2 * 1024**3
NO_MEMORY_LIMIT = {"audio"}  # speech models need more than the cap


def _child(
    conn: Connection, path: str, source_type: str, memory_limit: int | None, options: dict
) -> None:
    try:
        if memory_limit and sys.platform.startswith("linux"):  # not reliable on macOS/Windows
            import resource

            resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
        result = parse(Path(path), source_type, options)
        conn.send(("ok", [asdict(b) for b in result.blocks], result.page_count, result.title))
    except ParseError as e:
        conn.send(("error", str(e)))
    except MemoryError:
        conn.send(("error", "This file is too large to read."))
    except Exception as e:
        conn.send(("error", f"Could not read this file ({e.__class__.__name__})."))
    finally:
        conn.close()


def run_parse(
    path: Path,
    source_type: str,
    timeout: float | None = None,
    memory_limit: int | None = MEMORY_LIMIT_BYTES,
    options: dict | None = None,
) -> ParseResult:
    if timeout is None:
        timeout = TIMEOUTS_S.get(source_type, DEFAULT_TIMEOUT_S)
    if source_type in NO_MEMORY_LIMIT:
        memory_limit = None
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_child,
        args=(child, str(path), source_type, memory_limit, options or {}),
        daemon=True,
    )
    proc.start()
    child.close()
    try:
        if not parent.poll(timeout):
            raise ParseError("Reading this file took too long.")
        try:
            message = parent.recv()
        except EOFError:
            raise ParseError("Reading this file failed. It may be too large or damaged.") from None
    finally:
        parent.close()
        if proc.is_alive():
            proc.kill()
        proc.join(5)
    if message[0] == "error":
        raise ParseError(message[1])
    _, blocks, page_count, title = message
    return ParseResult([Block(**b) for b in blocks], page_count, title)
