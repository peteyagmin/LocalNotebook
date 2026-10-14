"""Ask the model for JSON and validate it against a Pydantic schema, retrying with the
validation error included (FR-5.10: up to 2 retries)."""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.base import LLMClient, Message

T = TypeVar("T", bound=BaseModel)

MAX_RETRIES = 2


class StructuredOutputError(Exception):
    """The model did not return valid JSON for the schema. The message is user-readable."""


def _extract_json(reply: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", reply, re.DOTALL)
    candidate = fenced.group(1) if fenced else reply
    start, end = candidate.find("{"), candidate.rfind("}")
    return candidate[start : end + 1] if start != -1 and end > start else candidate


async def generate_json(llm: LLMClient, model: str, messages: list[Message], schema: type[T]) -> T:
    convo = list(messages)
    error = ""
    for _attempt in range(MAX_RETRIES + 1):
        reply = await llm.chat(model, convo)
        try:
            return schema.model_validate(json.loads(_extract_json(reply)))
        except (json.JSONDecodeError, ValidationError) as e:
            error = str(e)
            convo = [
                *messages,
                {"role": "assistant", "content": reply},
                {
                    "role": "user",
                    "content": f"That reply was not valid: {error}\n"
                    "Respond again with only the JSON object in the required shape.",
                },
            ]
    raise StructuredOutputError(
        "The model did not return a valid answer after several tries. Try again."
    )
