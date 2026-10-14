"""Runtime configuration: defaults.toml + LNB_ environment overrides (spec §8)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

import platformdirs

APP_NAME = "LocalNotebook"
DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "config" / "defaults.toml"
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def load_defaults() -> dict:
    with DEFAULTS_PATH.open("rb") as f:
        return tomllib.load(f)


@dataclass(frozen=True)
class RuntimeConfig:
    data_root: Path
    host: str
    port: int
    llm_base_url_override: str | None
    allowed_origins: frozenset[str]


def load_runtime_config(env: dict[str, str] | None = None) -> RuntimeConfig:
    """Read LNB_DATA_ROOT, LNB_HOST_PORT, LNB_LLM_BASE_URL. Host is always 127.0.0.1 (SR-2)."""
    env = os.environ if env is None else env
    data_root = Path(env.get("LNB_DATA_ROOT") or platformdirs.user_data_dir(APP_NAME))
    port = int(env.get("LNB_HOST_PORT") or 8000)
    extra = {o.strip() for o in env.get("LNB_ALLOWED_ORIGINS", "").split(",") if o.strip()}
    origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"} | extra
    return RuntimeConfig(
        data_root=data_root,
        host="127.0.0.1",
        port=port,
        llm_base_url_override=env.get("LNB_LLM_BASE_URL") or None,
        allowed_origins=frozenset(origins),
    )
