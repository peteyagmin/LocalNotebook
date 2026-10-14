import json

import httpx
import pytest

from app.llm.base import LLMError
from app.llm.fake import FakeLLMClient
from app.llm.openai_compat import OpenAICompatClient


def _client(handler, key=""):
    return OpenAICompatClient("http://llm.test/v1", key, transport=httpx.MockTransport(handler))


async def test_list_models_and_auth_header():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json={"data": [{"id": "a"}, {"id": "b"}]})

    assert await _client(handler, "k").list_models() == ["a", "b"]
    assert seen == {"url": "http://llm.test/v1/models", "auth": "Bearer k"}


async def test_unreachable_and_http_error():
    def boom(req):
        raise httpx.ConnectError("no")

    with pytest.raises(LLMError):
        await _client(boom).list_models()
    with pytest.raises(LLMError, match="500"):
        await _client(lambda r: httpx.Response(500)).list_models()


async def test_chat_embed_stream():
    def handler(req: httpx.Request):
        body = json.loads(req.content)
        if req.url.path.endswith("/embeddings"):
            return httpx.Response(
                200,
                json={"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]},
            )
        if body.get("stream"):
            sse = (
                'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
                "data: [DONE]\n\n"
            )
            return httpx.Response(200, text=sse)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    c = _client(handler)
    assert await c.chat("m", [{"role": "user", "content": "x"}]) == "hi"
    assert await c.embed("m", ["a", "b"]) == [[1.0], [2.0]]
    assert "".join([t async for t in c.stream_chat("m", [])]) == "Hello"


async def test_fake_client_scripted():
    f = FakeLLMClient(replies=["one", lambda m, msgs: f"echo:{msgs[-1]['content']}"])
    assert await f.chat("m", []) == "one"
    assert await f.chat("m", [{"role": "user", "content": "q"}]) == "echo:q"
    with pytest.raises(AssertionError):
        await f.chat("m", [])
    e1, e2 = await f.embed("m", ["a"]), await f.embed("m", ["a"])
    assert e1 == e2
