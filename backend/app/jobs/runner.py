"""In-process async worker pool. Job state lives in notebook.db (spec §3)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from app.core import db
from app.core.ids import new_id, now_iso
from app.core.notebooks import NotebookStore, NotFound
from app.ingest.pipeline import run_ingest
from app.llm.base import LLMClient

log = logging.getLogger(__name__)

INTERRUPTED_MESSAGE = "Interrupted: the app was closed while this source was being processed."


class JobRunner:
    def __init__(
        self,
        store: NotebookStore,
        llm_factory: Callable[[dict], LLMClient],
        get_settings: Callable[[], dict],
        workers: int = 2,
    ):
        self.store = store
        self._llm_factory = llm_factory
        self._get_settings = get_settings
        self._worker_count = workers
        self._queue: asyncio.Queue[tuple[str, str, str]] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self._cancelled_sources: set[str] = set()
        self._cancelled_notebooks: set[str] = set()

    # --- lifecycle ---------------------------------------------------------------------------

    def recover(self) -> None:
        """Mark work left unfinished by a crash or exit as interrupted (retryable)."""
        for notebook_id in self.store.ids():
            path = self.store.db_path(notebook_id)
            if not path.exists():
                continue
            conn = db.connect(path)
            try:
                with conn:
                    conn.execute(
                        "UPDATE jobs SET state='interrupted', updated_at=? "
                        "WHERE state IN ('queued','running')",
                        (now_iso(),),
                    )
                    conn.execute(
                        "UPDATE sources SET state='failed', stage=NULL, error=?, updated_at=? "
                        "WHERE state IN ('queued','processing')",
                        (INTERRUPTED_MESSAGE, now_iso()),
                    )
            finally:
                conn.close()

    async def start(self) -> None:
        self.recover()
        self._tasks = [asyncio.create_task(self._worker()) for _ in range(self._worker_count)]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    # --- submitting and cancelling -----------------------------------------------------------

    def submit_ingest(self, notebook_id: str, source_id: str) -> str:
        """Queue an ingestion job; the source shows as queued immediately."""
        job_id = new_id()
        now = now_iso()
        self._cancelled_sources.discard(source_id)
        conn = self.store.open(notebook_id)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO jobs (id, kind, source_id, state, created_at, updated_at) "
                    "VALUES (?, 'ingest', ?, 'queued', ?, ?)",
                    (job_id, source_id, now, now),
                )
                conn.execute(
                    "UPDATE sources SET state='queued', stage=NULL, progress=0, error=NULL, "
                    "updated_at=? WHERE id=?",
                    (now, source_id),
                )
        finally:
            conn.close()
        self._queue.put_nowait((notebook_id, job_id, source_id))
        return job_id

    def cancel_source(self, source_id: str) -> None:
        self._cancelled_sources.add(source_id)

    def cancel_notebook(self, notebook_id: str) -> None:
        self._cancelled_notebooks.add(notebook_id)

    # --- worker ------------------------------------------------------------------------------

    def _set_job(self, notebook_id: str, job_id: str, state: str, error: str | None = None) -> None:
        try:
            conn = self.store.open(notebook_id)
        except NotFound:
            return
        try:
            with conn:
                conn.execute(
                    "UPDATE jobs SET state=?, error=?, progress=?, updated_at=? WHERE id=?",
                    (state, error, 1.0 if state == "succeeded" else 0.0, now_iso(), job_id),
                )
        finally:
            conn.close()

    async def _worker(self) -> None:
        while True:
            notebook_id, job_id, source_id = await self._queue.get()
            try:
                await self._run(notebook_id, job_id, source_id)
            except Exception:
                log.exception("Worker error on job %s", job_id)
            finally:
                self._queue.task_done()

    async def _run(self, notebook_id: str, job_id: str, source_id: str) -> None:
        if notebook_id in self._cancelled_notebooks or source_id in self._cancelled_sources:
            return
        self._set_job(notebook_id, job_id, "running")
        settings = self._get_settings()
        llm = self._llm_factory(settings)
        try:
            error = await run_ingest(
                self.store,
                notebook_id,
                source_id,
                llm,
                settings,
                is_cancelled=lambda: (
                    source_id in self._cancelled_sources or notebook_id in self._cancelled_notebooks
                ),
            )
        finally:
            close = getattr(llm, "aclose", None)
            if close:
                await close()
        self._set_job(notebook_id, job_id, "failed" if error else "succeeded", error)

    async def join(self) -> None:
        """Wait until the queue is drained (used by tests)."""
        await self._queue.join()
