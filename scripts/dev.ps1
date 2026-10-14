$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
uv run python scripts/dev.py
