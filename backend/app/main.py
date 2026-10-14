from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import health, settings
from app.core import db
from app.core.config import FRONTEND_DIST, MIGRATIONS_DIR, RuntimeConfig, load_runtime_config
from app.core.security import SecurityMiddleware, error_response, new_token
from app.llm.base import LLMClient
from app.llm.openai_compat import OpenAICompatClient


def default_llm_factory(settings: dict) -> LLMClient:
    return OpenAICompatClient(settings["llm_base_url"], settings["llm_api_key"])


def create_app(
    config: RuntimeConfig | None = None,
    token: str | None = None,
    llm_factory: Callable[[dict], LLMClient] = default_llm_factory,
    frontend_dist: Path = FRONTEND_DIST,
) -> FastAPI:
    config = config or load_runtime_config()
    token = token or os.environ.get("LNB_TOKEN") or new_token()

    app = FastAPI(
        title="LocalNotebook", docs_url="/api/v1/docs", openapi_url="/api/v1/openapi.json"
    )
    app.state.config = config
    app.state.llm_factory = llm_factory
    app.state.app_db_path = config.data_root / "app.db"
    db.migrate(app.state.app_db_path, MIGRATIONS_DIR / "app")

    app.add_middleware(SecurityMiddleware, token=token, allowed_origins=config.allowed_origins)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request, exc: StarletteHTTPException):
        return error_response(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request, exc: RequestValidationError):
        return error_response(422, "validation_error", "The request was not valid.")

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(settings.router, prefix="/api/v1")

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
