from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import get_services, get_settings, get_store
from app.core.errors import AppError
from app.core.notebooks import NotebookStore
from app.ingest.discover import discover
from app.ingest.safe_fetch import FetchError
from app.llm.base import LLMError
from app.llm.structured import StructuredOutputError

router = APIRouter()


class Topic(BaseModel):
    topic: str = Field(min_length=1, max_length=300)


@router.post("/notebooks/{notebook_id}/discover")
async def discover_sources(
    notebook_id: str,
    body: Topic,
    request: Request,
    store: NotebookStore = Depends(get_store),
    settings: dict = Depends(get_settings),
    services=Depends(get_services),
) -> dict:
    """Suggest sources for a topic (FR-2.11). Nothing is imported."""
    store.get(notebook_id)
    if not settings["allow_discover"]:
        raise AppError(403, "network_disabled", "Discover is turned off in Settings.")
    provider = services.search_provider(settings)
    if provider is None:
        raise AppError(
            400,
            "no_search_provider",
            "Discover needs a search provider. Add your SearXNG address in Settings.",
        )
    if not settings["chat_model"]:
        raise AppError(400, "not_configured", "Choose a chat model in Settings first.")
    topic = body.topic.strip()
    if not topic:
        raise AppError(400, "no_topic", "Enter a topic.")
    llm = request.app.state.llm_factory(settings)
    try:
        suggestions = await discover(topic, provider, services.fetch, llm, settings["chat_model"])
    except FetchError as e:
        raise AppError(502, "search_failed", str(e)) from e
    except (LLMError, StructuredOutputError) as e:
        raise AppError(502, "llm_error", str(e)) from e
    finally:
        close = getattr(llm, "aclose", None)
        if close:
            await close()
    return {"suggestions": suggestions}
