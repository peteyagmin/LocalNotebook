#!/usr/bin/env sh
set -e
cd "$(dirname "$0")/.."
exec uv run python scripts/launcher.py
