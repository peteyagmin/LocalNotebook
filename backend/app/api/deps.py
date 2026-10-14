from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator, Iterator

from fastapi import Depends, Request

from app.core import db, settings_store
from app.llm.base import LLMClient


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    conn = db.connect(request.app.state.app_db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_settings(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return settings_store.get_all(conn, request.app.state.config.llm_base_url_override)


async def get_llm(
    request: Request, settings: dict = Depends(get_settings)
) -> AsyncIterator[LLMClient]:
    client = request.app.state.llm_factory(settings)
    try:
        yield client
    finally:
        close = getattr(client, "aclose", None)
        if close:
            await close()


def get_store(request: Request):
    return request.app.state.store


def get_runner(request: Request):
    return request.app.state.runner


def get_services(request: Request):
    return request.app.state.services
