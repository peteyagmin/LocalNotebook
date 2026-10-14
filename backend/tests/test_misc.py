import json

import pytest

from app.core.ids import new_id, now_iso
from app.ingest.pipeline import SourceGuide
from app.llm.fake import FakeLLMClient
from app.llm.structured import StructuredOutputError, generate_json


def test_ids_are_unique_uuid7_and_time_ordered():
    ids = [new_id() for _ in range(50)]
    assert len(set(ids)) == 50
    assert all(i[14] == "7" for i in ids)
    assert [i.replace("-", "")[:12] for i in ids] == sorted(i.replace("-", "")[:12] for i in ids)


def test_now_iso_format():
    assert now_iso().endswith("Z") and "T" in now_iso()


GOOD = json.dumps({"summary": "S.", "topics": ["a"]})


async def test_generate_json_accepts_fenced_json():
    llm = FakeLLMClient(replies=[f"Sure:\n```json\n{GOOD}\n```"])
    assert (await generate_json(llm, "m", [], SourceGuide)).summary == "S."


async def test_generate_json_retries_with_the_error_then_succeeds():
    llm = FakeLLMClient(replies=["nope", '{"summary": "", "topics": []}', GOOD])
    result = await generate_json(llm, "m", [{"role": "user", "content": "q"}], SourceGuide)
    assert result.topics == ["a"]
    assert len(llm.calls) == 3
    retry_messages = llm.calls[1][1]
    assert retry_messages[-1]["role"] == "user" and "not valid" in retry_messages[-1]["content"]


async def test_generate_json_gives_up_after_two_retries():
    llm = FakeLLMClient(replies=["x", "y", "z", GOOD])
    with pytest.raises(StructuredOutputError):
        await generate_json(llm, "m", [], SourceGuide)
    assert len(llm.calls) == 3


def test_guide_topics_capped_at_eight():
    g = SourceGuide(summary="s", topics=[str(i) for i in range(12)])
    assert len(g.topics) == 8
