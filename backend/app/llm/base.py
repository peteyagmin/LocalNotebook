"""LLM client interface. Application code depends on this, never on a concrete runtime."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

Message = dict[str, str]  # {"role": "system"|"user"|"assistant", "content": "..."}


class LLMError(Exception):
    """Runtime unreachable or returned an error. The message is user-readable."""


class LLMClient(Protocol):
    async def list_models(self) -> list[str]: ...

    async def chat(self, model: str, messages: list[Message]) -> str: ...

    def stream_chat(self, model: str, messages: list[Message]) -> AsyncIterator[str]: ...

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]: ...
