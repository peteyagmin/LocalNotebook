"""Scripted LLM client for tests (QA-2). Never talks to a network."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Callable

from app.llm.base import LLMError, Message

Reply = str | Callable[[str, list[Message]], str]


class FakeLLMClient:
    def __init__(
        self,
        replies: list[Reply] | None = None,
        models: list[str] | None = None,
        unreachable: bool = False,
        embed_dim: int = 8,
        default_reply: Reply | None = None,
    ):
        self._replies = list(replies or [])
        self._models = models or []
        self._unreachable = unreachable
        self._embed_dim = embed_dim
        self._default = default_reply
        self.calls: list[tuple[str, list[Message]]] = []

    def _check(self) -> None:
        if self._unreachable:
            raise LLMError("Could not reach the model server: ConnectError.")

    async def list_models(self) -> list[str]:
        self._check()
        return list(self._models)

    async def chat(self, model: str, messages: list[Message]) -> str:
        self._check()
        self.calls.append((model, messages))
        if self._replies:
            reply = self._replies.pop(0)
        elif self._default is not None:
            reply = self._default
        else:
            raise AssertionError("FakeLLMClient has no scripted reply left.")
        return reply(model, messages) if callable(reply) else reply

    async def stream_chat(self, model: str, messages: list[Message]) -> AsyncIterator[str]:
        text = await self.chat(model, messages)
        for word in text.split(" "):
            yield word + " "

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        """Deterministic pseudo-embeddings derived from a hash of each text."""
        self._check()
        out = []
        for t in texts:
            digest = hashlib.sha256(t.encode()).digest()
            out.append([b / 255 for b in digest[: self._embed_dim]])
        return out
