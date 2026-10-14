"""Prompt templates live as plain-text files in app/prompts/ (spec §1.3)."""

from __future__ import annotations

from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def render_prompt(name: str, **values: str) -> str:
    template = Template((PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8"))
    return template.safe_substitute(values)
