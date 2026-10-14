from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    artifacts,
    chat,
    discover,
    health,
    notebooks,
    notes,
    search,
    settings,
    sources,
    speech,
)
from app.core import db, settings_store
from app.core.config import FRONTEND_DIST, MIGRATIONS_DIR, RuntimeConfig, load_runtime_config
from app.core.errors import AppError
from app.core.notebooks import NotebookStore, NotFound
from app.core.security import SecurityMiddleware, error_response, new_token
from app.ingest.services import Services
from app.jobs.runner import JobRunner
from app.llm.base import LLMClient
from app.llm.openai_compat import OpenAICompatClient
from app.speech.models import ModelDownloads, download_faster_whisper


def default_llm_factory(settings: dict) -> LLMClient:
    return OpenAICompatClient(settings["llm_base_url"], settings["llm_api_key"])


def create_app(
    config: RuntimeConfig | None = None,
    token: str | None = None,
    llm_factory: Callable[[dict], LLMClient] = default_llm_factory,
    frontend_dist: Path = FRONTEND_DIST,
    services: Services | None = None,
    model_downloader=download_faster_whisper,
) -> FastAPI:
    config = config or load_runtime_config()
    token = token or os.environ.get("LNB_TOKEN") or new_token()

    app_db_path = config.data_root / "app.db"
    db.migrate(app_db_path, MIGRATIONS_DIR / "app")
    store = NotebookStore(config.data_root)

    def load_settings() -> dict:
        conn = db.connect(app_db_path)
        try:
            return settings_store.get_all(conn, config.llm_base_url_override)
        finally:
            conn.close()

    services = services or Services(models_dir=config.data_root / "models")
    runner = JobRunner(store, llm_factory, load_settings, services=services)

    @asynccontextmanager
    async def lifespan(_app):
        await runner.start()
        yield
        await runner.stop()

    app = FastAPI(
        title="LocalNotebook",
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )
    app.state.config = config
    app.state.llm_factory = llm_factory
    app.state.app_db_path = app_db_path
    app.state.store = store
    app.state.runner = runner
    app.state.chat_stops = {}
    app.state.services = services
    app.state.model_downloads = ModelDownloads(services.models_dir, model_downloader)

    app.add_middleware(SecurityMiddleware, token=token, allowed_origins=config.allowed_origins)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request, exc: StarletteHTTPException):
        return error_response(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request, exc: RequestValidationError):
        return error_response(422, "validation_error", "The request was not valid.")

    @app.exception_handler(AppError)
    async def _app_error(_request, exc: AppError):
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(NotFound)
    async def _not_found(_request, _exc: NotFound):
        return error_response(404, "not_found", "That item no longer exists.")

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(settings.router, prefix="/api/v1")
    app.include_router(notebooks.router, prefix="/api/v1")
    app.include_router(sources.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(notes.router, prefix="/api/v1")
    app.include_router(artifacts.router, prefix="/api/v1")
    app.include_router(discover.router, prefix="/api/v1")
    app.include_router(speech.router, prefix="/api/v1")

    if (frontend_dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Not found.")
            candidate = (frontend_dist / path).resolve()
            if path and candidate.is_file() and frontend_dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(frontend_dist / "index.html")

    return app
