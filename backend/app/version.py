"""The app version: single source is `version` in pyproject.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path


def app_version() -> str:
    try:
        data = tomllib.loads(
            (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text("utf-8")
        )
        return str(data["project"]["version"])
    except (OSError, KeyError, ValueError):
        return "unknown"
