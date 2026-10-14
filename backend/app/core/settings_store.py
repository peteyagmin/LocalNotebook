"""Global settings stored in app.db (FR-8.1, FR-8.4). Values are JSON-encoded."""

from __future__ import annotations

import json
import sqlite3

from app.core.config import load_defaults

SETTING_KEYS = tuple(load_defaults().keys())


def get_all(conn: sqlite3.Connection, llm_base_url_override: str | None = None) -> dict:
    values = load_defaults()
    for row in conn.execute("SELECT key, value FROM settings"):
        if row["key"] in values:
            values[row["key"]] = json.loads(row["value"])
    if llm_base_url_override:
        values["llm_base_url"] = llm_base_url_override
    return values


def update(conn: sqlite3.Connection, changes: dict) -> None:
    unknown = set(changes) - set(SETTING_KEYS)
    if unknown:
        raise KeyError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
    with conn:  # one transaction (DR-6)
        for key, value in changes.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )


def load_defaults_for_eval() -> dict:
    """Defaults without touching a database (used by evals/run_eval.py)."""
    return load_defaults()
