"""Client for any OpenAI-compatible server, including Ollama's /v1 API (FR-8.4)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.llm.base import LLMError, Message


class OpenAICompatClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 120.0,
    ):
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers=headers,
            transport=transport,
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            resp = await self._http.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            raise LLMError(f"The model server returned HTTP {e.response.status_code}.") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Could not reach the model server: {e.__class__.__name__}.") from e

    async def list_models(self) -> list[str]:
        resp = await self._request("GET", "models")
        return [m["id"] for m in resp.json().get("data", [])]

    async def chat(self, model: str, messages: list[Message]) -> str:
        resp = await self._request(
            "POST", "chat/completions", json={"model": model, "messages": messages}
        )
        return resp.json()["choices"][0]["message"]["content"]

    async def stream_chat(self, model: str, messages: list[Message]) -> AsyncIterator[str]:
        payload = {"model": model, "messages": messages, "stream": True}
        try:
            async with self._http.stream("POST", "chat/completions", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
        except httpx.HTTPStatusError as e:
            raise LLMError(f"The model server returned HTTP {e.response.status_code}.") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Could not reach the model server: {e.__class__.__name__}.") from e

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        resp = await self._request("POST", "embeddings", json={"model": model, "input": texts})
        items = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in items]
